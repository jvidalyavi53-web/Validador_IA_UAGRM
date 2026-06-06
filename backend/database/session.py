import os
import time
import logging
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from backend.database.models import Base
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("UAGRM_Session")

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./uagrm_enterprise.db")

if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

if "sqlite" in SQLALCHEMY_DATABASE_URL:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(max_retries: int = 3, base_delay: float = 1.0) -> bool:
    """
    Inicializa el esquema con reintentos. Retorna True si tuvo éxito.
    No aborta el arranque del worker: si la DB está caída, los endpoints
    devolverán 503 y Render no se quedará en bucle.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            with engine.connect() as conn:
                conn.execute(sqlalchemy_text("SELECT 1"))
            logger.info("Base de datos inicializada y operativa.")
            return True
        except OperationalError as exc:
            last_error = exc
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                f"DB no disponible (intento {attempt}/{max_retries}): {exc}. "
                f"Reintentando en {delay}s..."
            )
            time.sleep(delay)
        except Exception as exc:
            last_error = exc
            logger.error(f"Error inesperado inicializando la DB: {exc}")
            break

    logger.error(
        f"No se pudo inicializar la base de datos tras {max_retries} intentos: {last_error}"
    )
    return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def sqlalchemy_text(sql: str):
    """Helper para mantener el import dentro del módulo y evitar dependencias circulares."""
    from sqlalchemy import text
    return text(sql)

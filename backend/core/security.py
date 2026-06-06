import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
import bcrypt
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("UAGRM_Security")

_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", str(60 * 24)))

_INSECURE_FALLBACKS = {
    "",
    "uagrm_super_secret_key_2026_enterprise_x99",
    "changeme",
    "secret",
    "default",
}


def _validate_secret_key() -> None:
    if not SECRET_KEY or SECRET_KEY in _INSECURE_FALLBACKS:
        if _ENVIRONMENT == "production":
            raise RuntimeError(
                "SECRET_KEY no está definida o usa un valor de fallback inseguro. "
                "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        logger.warning(
            "SECRET_KEY no definida o insegura. Funcionando en modo %s. "
            "NO uses esta configuración en producción.",
            _ENVIRONMENT,
        )


_validate_secret_key()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica la contraseña usando bcrypt nativo."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError) as exc:
        logger.error(f"Error al verificar contraseña: {exc}")
        return False


def get_password_hash(password: str) -> str:
    """Genera un hash seguro con bcrypt nativo."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    data: dict, expires_delta: Optional[timedelta] = None
) -> str:
    to_encode = data.copy()
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decodifica un JWT. Lanza jose.JWTError si es inválido o expiró."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

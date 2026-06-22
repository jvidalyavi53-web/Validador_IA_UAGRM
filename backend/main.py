import sys
import os
import uuid
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
import shutil
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.append(str(PROJECT_ROOT))

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    HTTPException,
    Depends,
    Form,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text as sa_text
from jose import JWTError

from backend.database.vector_db import VectorDB
from backend.services.document_processor import DocumentProcessor
from backend.services.text_chunker import TextChunker
from backend.services.rag_engine import RAGEngine

from backend.database.session import init_db, get_db, engine, SessionLocal
from backend.database import models
from backend.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("UAGRM_CoreAPI")


# CONFIGURACIÓN

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8501,http://127.0.0.1:8501",
    ).split(",")
    if o.strip()
]

MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_REQUEST_SECONDS = int(os.getenv("MAX_REQUEST_SECONDS", "50"))

# CORPUS GLOBAL (compartido por todos los usuarios autenticados)
global_vdb: VectorDB = VectorDB()
global_engine: RAGEngine = RAGEngine(vdb_instance=global_vdb, provider="groq")
corpus_lock = asyncio.Lock()  # serializa add_documents (TF-IDF no es thread-safe)


def load_corpus_from_db() -> int:
    """
    Reconstruye el índice TF-IDF desde la tabla `chunks` de PostgreSQL.
    Llamada al startup. Devuelve el número de chunks cargados.
    """
    from backend.database.session import SessionLocal
    session = SessionLocal()
    try:
        rows = session.query(models.Chunk).all()
        global_vdb.rebuild_from_rows(rows)
        return len(rows)
    except Exception as exc:
        logger.error(f"No se pudo reconstruir el corpus desde la DB: {exc}")
        return 0
    finally:
        session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / Shutdown hooks. NO aborta el arranque si la DB está caída."""
    logger.info("Inicializando Validador IA UAGRM...")
    db_ok = init_db()
    if not db_ok:
        logger.warning(
            "La base de datos no respondió. La API levantará igual; "
            "los endpoints que requieran DB devolverán HTTP 503."
        )
    else:
        n = load_corpus_from_db()
        logger.info(f"Corpus institucional cargado: {n} chunks en memoria.")
    yield
    logger.info("Apagando Validador IA UAGRM...")


app = FastAPI(
    title="Validador IA UAGRM",
    version="7.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

processor = DocumentProcessor(
    tesseract_cmd_path=os.getenv("TESSERACT_CMD") or None,
)
chunker = TextChunker()

# ==============================================================================
# AUTENTICACIÓN (RBAC)
# ==============================================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Usuario:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o sesión expirada.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
    except JWTError:
        raise creds_exc

    username = payload.get("sub")
    rol = payload.get("rol")
    if not username or not rol:
        raise creds_exc

    user = (
        db.query(models.Usuario)
        .filter(models.Usuario.username == username)
        .first()
    )
    if user is None:
        raise creds_exc
    return user


def require_admin(user: models.Usuario = Depends(get_current_user)) -> models.Usuario:
    if user.rol != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado: privilegios de Administrador requeridos.",
        )
    return user


def require_self_or_admin(
    target_username: str,
    user: models.Usuario = Depends(get_current_user),
) -> models.Usuario:
    if user.rol == "admin":
        return user
    if user.username != target_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes operar sobre la cuenta de otro usuario.",
        )
    return user


# ==============================================================================
# ESQUEMAS PYDANTIC
# ==============================================================================
class ChatQuery(BaseModel):
    query: str
    provider: str = "groq"


class ClearRequest(BaseModel):
    pass


class ChatResponse(BaseModel):
    response: str
    status: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=6)
    rol: str = "visitante"
    admin_secret: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    rol: str


class LoginRequest(BaseModel):
    username: str
    password: str


# ==============================================================================
# ENDPOINTS DE SALUD
# ==============================================================================
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {
        "status": "ok",
        "service": "Validador IA UAGRM",
        "version": app.version,
    }


@app.api_route("/api/v1/healthz", methods=["GET", "HEAD"])
def healthz(db: Session = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(sa_text("SELECT 1"))
    except Exception as exc:
        logger.error(f"DB no responde en healthcheck: {exc}")
        db_status = "down"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "db": db_status},
        )
    return {"status": "ok", "db": db_status}


# ==============================================================================
# ENDPOINTS DE AUTENTICACIÓN
# ==============================================================================
@app.post("/api/v1/auth/register", response_model=dict)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    ADMIN_SECRET = os.getenv("ADMIN_SECRET", "FICCT2026")
    try:
        if user.rol == "admin" and user.admin_secret != ADMIN_SECRET:
            raise HTTPException(
                status_code=403,
                detail="Código de Autorización Institucional incorrecto.",
            )

        # FIX: Eliminamos los espacios en blanco que los teclados móviles añaden
        clean_username = user.username.strip()
        clean_password = user.password.strip()

        if (
            db.query(models.Usuario)
            .filter(models.Usuario.username == clean_username)
            .first()
        ):
            raise HTTPException(
                status_code=400, detail="El nombre de usuario ya está ocupado."
            )

        hashed_password = get_password_hash(clean_password)
        nuevo_usuario = models.Usuario(
            username=clean_username,
            password_hash=hashed_password,
            rol=user.rol,
        )
        db.add(nuevo_usuario)
        db.commit()
        db.refresh(nuevo_usuario)
        return {"mensaje": "Usuario creado", "username": nuevo_usuario.username}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error registrando usuario")
        raise HTTPException(status_code=500, detail="Fallo interno al crear la cuenta.")


@app.post("/api/v1/auth/login", response_model=Token)
def login_for_access_token(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    # FIX: Limpiamos los espacios antes de verificar en la base de datos
    clean_username = payload.username.strip()
    clean_password = payload.password.strip()

    user = (
        db.query(models.Usuario)
        .filter(models.Usuario.username == clean_username)
        .first()
    )
    if not user or not verify_password(clean_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
        )
    access_token = create_access_token(
        data={"sub": user.username, "rol": user.rol}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "rol": user.rol,
        "username": user.username,
    }


@app.get("/api/v1/auth/me")
def me(user: models.Usuario = Depends(get_current_user)):
    return {"username": user.username, "rol": user.rol}


# ENDPOINTS RAG / DOCUMENTOS

@app.post("/api/v1/documents/upload", status_code=200)
async def upload_document(
    file: UploadFile = File(...),
    current_user: models.Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se admiten PDFs.")

    contents = await file.read()
    if len(contents) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (> {MAX_UPLOAD_MB} MB).",
        )

    temp_dir = Path("data/runtime_temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / f"{uuid.uuid4()}_{file.filename}"

    try:
        with open(temp_file_path, "wb") as buffer:
            buffer.write(contents)

        logger.info(f"Procesando PDF: {file.filename} ({len(contents)} bytes)")
        texto = processor.process_pdf(str(temp_file_path))

        if not texto or len(texto.strip()) < 10:
            raise ValueError(
                "No se pudo extraer texto del PDF. "
                "Puede ser una imagen ilegible o un PDF protegido."
            )

        chunks = chunker.split_text(texto, document_name=file.filename)
        if not chunks:
            raise ValueError("El PDF no generó fragmentos procesables.")

        # 1) Persistir el documento y sus chunks en la DB (sobrevive a restarts)
        nuevo_doc = models.Documento(
            nombre_archivo=file.filename,
            tamaño_bytes=len(contents),
            usuario_id=current_user.id,
        )
        db.add(nuevo_doc)
        db.flush()  # para obtener nuevo_doc.id

        chunk_rows = [
            models.Chunk(
                documento_id=nuevo_doc.id,
                chunk_index=i,
                content=ch.page_content,
                source=ch.metadata.get("source", file.filename),
            )
            for i, ch in enumerate(chunks)
        ]
        db.bulk_save_objects(chunk_rows)
        db.commit()

        # 2) Reentrenar el TF-IDF global con los nuevos chunks (lock por concurrencia)
        async with corpus_lock:
            global_vdb.add_documents(chunks)

        logger.info(
            f"PDF ingestado: {file.filename} · {len(chunks)} chunks · "
            f"corpus total={global_vdb._doc_matrix.shape[0] if global_vdb._doc_matrix is not None else 0}"
        )

    except ValueError as ve:
        logger.warning(f"PDF inválido: {ve}")
        db.rollback()
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception("Fallo en procesamiento")
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Error procesando documento: {exc}"
        )
    finally:
        if temp_file_path.exists():
            try:
                os.remove(temp_file_path)
            except OSError:
                pass

    return {
        "message": "Documento blindado e ingestado en el Corpus Institucional.",
        "status": "success",
        "filename": file.filename,
        "chunks_ingested": len(chunks),
    }


@app.get("/api/v1/documents", response_model=dict)
def list_documents(
    current_user: models.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista los PDFs del corpus institucional (visible para cualquier usuario autenticado)."""
    docs = (
        db.query(models.Documento)
        .order_by(models.Documento.fecha_subida.desc())
        .all()
    )
    
    documentos_formateados = []
    for d in docs:
        documentos_formateados.append({
            "id": d.id,
            "nombre_archivo": d.nombre_archivo,
            "tamaño_bytes": d.tamaño_bytes,
            "fecha_subida": d.fecha_subida.isoformat() if d.fecha_subida else None,
            "subido_por": d.subido_por.username if d.subido_por else "Desconocido",
        })

    return {
        "total": len(docs),
        "corpus_chunks": (
            global_vdb._doc_matrix.shape[0]
            if global_vdb._doc_matrix is not None else 0
        ),
        "documentos": documentos_formateados,
    }


@app.post("/api/v1/chat/ask", response_model=ChatResponse)
async def ask_knowledge_base(
    payload: ChatQuery,
    current_user: models.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    global_engine.set_provider(payload.provider)

    try:
        respuesta = await asyncio.wait_for(
            asyncio.to_thread(global_engine.ask, payload.query),
            timeout=MAX_REQUEST_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            f"Timeout en chat para {current_user.username} tras {MAX_REQUEST_SECONDS}s"
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                f"El proveedor de IA no respondió en {MAX_REQUEST_SECONDS} segundos. "
                "Reintenta o cambia el modo (Groq / Ollama) en la barra lateral."
            ),
        )
    except RuntimeError as re:
        logger.error(f"Fallo RAG: {re}")
        raise HTTPException(status_code=500, detail=str(re))

    try:
        nueva_conversacion = models.Conversacion(
            consulta_usuario=payload.query,
            respuesta_ia=respuesta,
            proveedor_ia=payload.provider,
            usuario_id=current_user.id,
        )
        db.add(nueva_conversacion)
        db.commit()
    except Exception as exc:
        logger.error(f"No se pudo persistir la conversación: {exc}")
        db.rollback()

    return ChatResponse(response=respuesta, status="success")


@app.get("/api/v1/chat/history")
def get_chat_history(
    current_user: models.Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversaciones = (
        db.query(models.Conversacion)
        .filter(models.Conversacion.usuario_id == current_user.id)
        .order_by(models.Conversacion.fecha_interaccion.asc())
        .all()
    )
    historial = []
    for conv in conversaciones:
        historial.append({"rol": "user", "contenido": conv.consulta_usuario})
        historial.append({"rol": "assistant", "contenido": conv.respuesta_ia})
    return {"historial": historial}


@app.post("/api/v1/database/clear")
async def clear_vector_ram(
    current_user: models.Usuario = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        # 1) Limpiar la DB (chunks se borran en cascada por el FK)
        deleted_chunks = db.query(models.Chunk).delete()
        deleted_docs = db.query(models.Documento).delete()
        db.query(models.Conversacion).delete()
        db.commit()

        # 2) Resetear el índice TF-IDF global
        async with corpus_lock:
            global_vdb.reset()

        logger.info(
            f"Corpus purgado: {deleted_docs} documentos, {deleted_chunks} chunks, "
            f"conversaciones eliminadas."
        )
        return {
            "status": "cleared",
            "message": "Amnesia total exitosa. Corpus institucional vacío.",
            "documentos_eliminados": deleted_docs,
            "chunks_eliminados": deleted_chunks,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Fallo purgando base")
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=bool(int(os.getenv("RELOAD", "0"))),
    )
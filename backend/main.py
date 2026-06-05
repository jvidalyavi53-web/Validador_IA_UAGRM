import sys
import os
import uuid
from pathlib import Path
import shutil
import logging
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
sys.path.append(str(PROJECT_ROOT))

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from backend.database.vector_db import VectorDB
from backend.services.document_processor import DocumentProcessor
from backend.services.text_chunker import TextChunker
from backend.services.rag_engine import RAGEngine

from backend.database.session import init_db, get_db
from backend.database import models
from backend.core.security import get_password_hash, verify_password, create_access_token, SECRET_KEY, ALGORITHM

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("UAGRM_CoreAPI")

app = FastAPI(title="Validador IA UAGRM", version="5.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# ==============================================================================
# AISLAMIENTO MULTI-TENANT
# ==============================================================================
active_clusters = {}

processor = DocumentProcessor(tesseract_cmd_path=r'C:\Program Files\Tesseract-OCR\tesseract.exe')
chunker = TextChunker()

def get_user_cluster(username: str, provider: str = "groq"):
    if username not in active_clusters:
        logger.info(f"Creando partición RAM exclusiva para: {username}")
        new_vdb = VectorDB()
        new_engine = RAGEngine(vdb_instance=new_vdb, provider=provider)
        active_clusters[username] = {"vdb": new_vdb, "engine": new_engine}
    return active_clusters[username]

# ==============================================================================
# EL GUARDIA DE SEGURIDAD (RBAC)
# ==============================================================================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

def get_current_user_role(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        rol: str = payload.get("rol")
        if rol is None:
            raise HTTPException(status_code=401, detail="Token inválido")
        return rol
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

def require_admin(rol: str = Depends(get_current_user_role)):
    if rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado: Privilegios de Administrador requeridos.")

# ==============================================================================
# ESQUEMAS PYDANTIC
# ==============================================================================
class ChatQuery(BaseModel):
    query: str
    provider: str = "groq"
    username: str

class ClearRequest(BaseModel):
    username: str

class ChatResponse(BaseModel):
    response: str
    status: str

class UserCreate(BaseModel):
    username: str = Field(..., min_length=4, max_length=20, description="Usuario de 4 a 20 caracteres")
    password: str = Field(..., min_length=6, description="Mínimo 6 caracteres")
    rol: str = "visitante"
    admin_secret: str = None  

class Token(BaseModel):
    access_token: str
    token_type: str
    rol: str

# ==============================================================================
# ENDPOINTS REST: AUTENTICACIÓN Y SEGURIDAD
# ==============================================================================
@app.post("/api/v1/auth/register", response_model=dict)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    try:
        if user.rol == "admin" and user.admin_secret != "FICCT2026":
            raise HTTPException(status_code=403, detail="Código de Autorización Institucional incorrecto. No puedes crear un Admin.")

        db_user = db.query(models.Usuario).filter(models.Usuario.username == user.username).first()
        if db_user:
            raise HTTPException(status_code=400, detail="El nombre de usuario ya está ocupado.")
        
        hashed_password = get_password_hash(user.password)
        nuevo_usuario = models.Usuario(username=user.username, password_hash=hashed_password, rol=user.rol)
        db.add(nuevo_usuario)
        db.commit()
        return {"mensaje": "Usuario creado", "username": nuevo_usuario.username}
    except HTTPException as he:
        raise he 
    except Exception as e:
        logger.error(f"Error registrando usuario: {str(e)}")
        raise HTTPException(status_code=500, detail="Fallo interno al crear la cuenta.")

@app.post("/api/v1/auth/login", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    access_token = create_access_token(data={"sub": user.username, "rol": user.rol})
    return {"access_token": access_token, "token_type": "bearer", "rol": user.rol}

# ==============================================================================
# ENDPOINTS REST: RAG (AHORA SÍNCRONO PARA EVITAR FALSOS POSITIVOS)
# ==============================================================================
@app.post("/api/v1/documents/upload", status_code=200)
async def upload_document(
    username: str = Form(...), 
    file: UploadFile = File(...),
    _guardia: str = Depends(require_admin)
):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo se admiten PDFs.")
    
    cluster = get_user_cluster(username)
    temp_dir = Path("data/runtime_temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file_path = temp_dir / f"{uuid.uuid4()}_{file.filename}"
    
    try:
        # 1. Guardar temporalmente
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2.  PROCESAMIENTO SÍNCRONO ESTRICTO (Espera hasta que termine)
        logger.info(f"Iniciando vectorización síncrona: {file.filename}")
        texto = processor.process_pdf(str(temp_file_path))
        
        if not texto or len(texto.strip()) < 10:
            raise ValueError("No se pudo extraer texto del PDF. Puede ser una imagen ilegible.")
            
        chunks = chunker.split_text(texto, document_name=file.filename)
        cluster["vdb"].add_documents(chunks)
        logger.info(f"Vectorización completada exitosamente: {file.filename}")
        
    except Exception as e:
        logger.error(f"Fallo en procesamiento: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error procesando documento: {str(e)}")
    finally:
        if temp_file_path.exists(): os.remove(temp_file_path)
    
    return {"message": "Documento blindado e ingestadon", "status": "success"}

@app.post("/api/v1/chat/ask", response_model=ChatResponse)
async def ask_knowledge_base(payload: ChatQuery, db: Session = Depends(get_db)):
    try:
        cluster = get_user_cluster(payload.username, provider=payload.provider)
        engine = cluster["engine"]
        
        if engine.provider != payload.provider:
            engine.provider = payload.provider
            engine.llm = engine._initialize_llm()
            
        respuesta = engine.ask(payload.query)
        
        user = db.query(models.Usuario).filter(models.Usuario.username == payload.username).first()
        if user:
            nueva_conversacion = models.Conversacion(
                consulta_usuario=payload.query,
                respuesta_ia=respuesta,
                proveedor_ia=payload.provider,
                usuario_id=user.id
            )
            db.add(nueva_conversacion)
            db.commit()

        return ChatResponse(response=respuesta, status="success")
    except Exception as e:
        logger.error(f"Error en chat: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Fallo RAG: {str(e)}")

@app.get("/api/v1/chat/history/{username}")
def get_chat_history(username: str, db: Session = Depends(get_db)):
    user = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    conversaciones = db.query(models.Conversacion).filter(models.Conversacion.usuario_id == user.id).order_by(models.Conversacion.fecha_interaccion.asc()).all()
    
    historial = []
    for conv in conversaciones:
        historial.append({"rol": "user", "contenido": conv.consulta_usuario})
        historial.append({"rol": "assistant", "contenido": conv.respuesta_ia})
        
    return {"historial": historial}

@app.post("/api/v1/database/clear")
async def clear_vector_ram(
    payload: ClearRequest, 
    db: Session = Depends(get_db),
    _guardia: str = Depends(require_admin)
):
    try:
        if payload.username in active_clusters:
            provider = active_clusters[payload.username]["engine"].provider
            active_clusters[payload.username]["vdb"] = VectorDB()
            active_clusters[payload.username]["engine"] = RAGEngine(
                vdb_instance=active_clusters[payload.username]["vdb"], 
                provider=provider
            )
            
        user = db.query(models.Usuario).filter(models.Usuario.username == payload.username).first()
        if user:
            db.query(models.Conversacion).filter(models.Conversacion.usuario_id == user.id).delete()
            db.commit()

        return {"status": "cleared", "message": "Amnesia total exitosa."}
    except Exception as e:
        db.rollback() 
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
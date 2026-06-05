from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

# Clase base de la que heredarán todas nuestras tablas
Base = declarative_base()

class Usuario(Base):
    """Tabla para gestionar los accesos al sistema."""
    __tablename__ = 'usuarios'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    rol = Column(String(20), default="visitante")  # Roles: admin, guardia, visitante
    fecha_creacion = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones con otras tablas
    documentos = relationship("Documento", back_populates="subido_por")
    conversaciones = relationship("Conversacion", back_populates="usuario")

class Documento(Base):
    """Tabla de auditoría para los PDFs normativos ingresados."""
    __tablename__ = 'documentos'
    
    id = Column(Integer, primary_key=True, index=True)
    nombre_archivo = Column(String(255), index=True, nullable=False)
    tamaño_bytes = Column(Integer)
    fecha_subida = Column(DateTime, default=datetime.utcnow)
    
    # Llave foránea que conecta con el Usuario que subió el PDF
    usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    subido_por = relationship("Usuario", back_populates="documentos")

class Conversacion(Base):
    """Tabla para almacenar el historial de los chats RAG."""
    __tablename__ = 'conversaciones'
    
    id = Column(Integer, primary_key=True, index=True)
    consulta_usuario = Column(Text, nullable=False)
    respuesta_ia = Column(Text, nullable=False)
    proveedor_ia = Column(String(20)) # Para saber si se usó Groq u Ollama
    fecha_interaccion = Column(DateTime, default=datetime.utcnow)
    
    # Llave foránea que conecta con el Usuario que hizo la pregunta
    usuario_id = Column(Integer, ForeignKey('usuarios.id'))
    usuario = relationship("Usuario", back_populates="conversaciones")
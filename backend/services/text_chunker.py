# VERSION DEFINITIVA RAG ACTIVADA
from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

class TextChunker:
    def __init__(self):
        # FIX CRÍTICO: Reducimos el tamaño a 600 caracteres con 150 de solapamiento.
        # Esto asegura que los fragmentos sean párrafos precisos y densos en palabras clave,
        # mejorando drásticamente la puntería del motor TF-IDF.
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=600,
            chunk_overlap=150,
            separators=["\n\nArtículo", "\n\nARTÍCULO", "\n\nCAPÍTULO", "\n\n", "\n", ".", " ", ""]
        )
        
    def split_text(self, text: str, document_name: str):
        if not text:
            logger.warning("Se recibió un texto vacío.")
            return []
            
        # Genera fragmentos inyectando el nombre del documento original
        chunks = self.splitter.create_documents([text], metadatas=[{"source": document_name}])
        logger.info(f"Documento dividido exitosamente en {len(chunks)} fragmentos hiper-precisos.")
        return chunks
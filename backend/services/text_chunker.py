from langchain_text_splitters import RecursiveCharacterTextSplitter
import logging

logger = logging.getLogger(__name__)

class TextChunker:
    def __init__(self):
        # Cortes enormes para no partir Artículos por la mitad
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=300,
            separators=["\n\nArtículo", "\n\nARTÍCULO", "\n\nCAPÍTULO", "\n\n", "\n", " ", ""]
        )
        
    def split_text(self, text: str, document_name: str):
        if not text:
            logger.warning("Se recibió un texto vacío.")
            return []
            
        # Genera fragmentos inyectando el nombre del documento original
        chunks = self.splitter.create_documents([text], metadatas=[{"source": document_name}])
        logger.info(f"Documento dividido exitosamente en {len(chunks)} fragmentos.")
        return chunks
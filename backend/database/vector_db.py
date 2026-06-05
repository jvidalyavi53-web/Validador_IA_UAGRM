import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import logging

logger = logging.getLogger("VectorDB")

class VectorDB:
    def __init__(self):
        logger.info("Inicializando Base de Datos Vectorial (Modo RAM Pura)...")
        
        try:
            # FORZAMOS MODO EFÍMERO (RAM) CON TELEMETRÍA APAGADA
            # Esto evita el error de SQLite "no such table: tenants"
            self.client = chromadb.EphemeralClient(
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            # Reseteamos por si quedó basura en RAM de ejecuciones anteriores
            self.client.reset()
        except Exception as e:
            logger.error(f"Error crítico al inicializar ChromaDB en RAM: {e}")
            raise e
        
        # Inicializamos el modelo de Embeddings
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        # Creación de la Colección Limpia
        self.collection = self.client.create_collection(
            name="normativas_uagrm",
            embedding_function=self.embedding_fn
        )
        logger.info("Base Vectorial lista y operativa en RAM.")

    def add_documents(self, chunks):
        """Vectoriza e ingresa fragmentos de texto a la base de datos."""
        if not chunks:
            return
            
        #  CORRECCIÓN DEL ERROR "Document object is not subscriptable" 
        # Langchain devuelve objetos Document. Extraemos el texto usando .page_content 
        # y los metadatos usando .metadata
        documents = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        
        # Extraemos el nombre del archivo del metadato para crear el ID único
        ids = [f"{chunk.metadata.get('source', 'documento')}_{i}" for i, chunk in enumerate(chunks)]
        
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        logger.info(f"Se inyectaron {len(chunks)} vectores en la DB.")

    def search(self, query, n_results=5):
        """Busca los fragmentos más relevantes por similitud semántica."""
        return self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
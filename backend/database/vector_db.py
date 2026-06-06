import os
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger("VectorDB")

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "huggingface_api").lower()
HF_API_KEY = os.getenv("HF_API_KEY", "").strip()
HF_EMBEDDING_MODEL = os.getenv(
    "HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
COLLECTION_NAME = "normativas_uagrm"


class VectorDB:
    """
    Wrapper ligero sobre ChromaDB.

    - No instancia el cliente ni los embeddings hasta que realmente se necesitan
      (lazy init). Esto evita que un 'Hola' dispare la carga del modelo.
    - Si no hay documentos, is_ready() devuelve False y ask() responde en modo
      conversacional sin tocar Chroma.
    """

    def __init__(self) -> None:
        self._client = None
        self._embedding_fn = None
        self._collection = None
        self._initialized = False
        self._has_documents = False

    @property
    def collection_name(self) -> str:
        return COLLECTION_NAME

    def _build_embedding_fn(self):
        if EMBEDDING_PROVIDER == "huggingface_api":
            if not HF_API_KEY:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=huggingface_api requiere HF_API_KEY. "
                    "Genera una en https://huggingface.co/settings/tokens"
                )
            logger.info(
                f"Embeddings remotos: HuggingFace API · modelo={HF_EMBEDDING_MODEL}"
            )
            return embedding_functions.HuggingFaceEmbeddingFunction(
                api_key=HF_API_KEY,
                model_name=HF_EMBEDDING_MODEL,
            )

        if EMBEDDING_PROVIDER == "local_st":
            try:
                from sentence_transformers import SentenceTransformer  # noqa: F401
            except ImportError as exc:
                raise RuntimeError(
                    "EMBEDDING_PROVIDER=local_st requiere 'sentence-transformers'. "
                    "Instálalo o cambia a EMBEDDING_PROVIDER=huggingface_api."
                ) from exc
            logger.info("Embeddings locales: SentenceTransformer · all-MiniLM-L6-v2")
            return embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )

        raise ValueError(
            f"EMBEDDING_PROVIDER no soportado: {EMBEDDING_PROVIDER!r}. "
            "Usa 'huggingface_api' o 'local_st'."
        )

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        logger.info(
            f"Inicializando ChromaDB (modo RAM) · provider={EMBEDDING_PROVIDER}"
        )
        self._client = chromadb.EphemeralClient(
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )
        self._embedding_fn = self._build_embedding_fn()
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )
        self._initialized = True
        self._has_documents = self._collection.count() > 0
        logger.info(
            f"ChromaDB lista · collection='{COLLECTION_NAME}' · docs={self._collection.count()}"
        )

    def is_ready(self) -> bool:
        """True si ya hay al menos un documento vectorizado."""
        if not self._initialized:
            return False
        return self._has_documents

    def add_documents(self, chunks) -> None:
        if not chunks:
            return
        self._ensure_initialized()

        documents = [chunk.page_content for chunk in chunks]
        metadatas = [chunk.metadata for chunk in chunks]
        ids = [
            f"{chunk.metadata.get('source', 'documento')}_{i}"
            for i, chunk in enumerate(chunks)
        ]

        self._collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        self._has_documents = self._collection.count() > 0
        logger.info(
            f"Inyectados {len(chunks)} vectores · total={self._collection.count()}"
        )

    def search(self, query: str, n_results: int = 5):
        if not self.is_ready():
            return {"documents": [[]], "metadatas": [[]]}
        self._ensure_initialized()
        return self._collection.query(
            query_texts=[query],
            n_results=n_results,
        )

    def reset(self) -> None:
        """Purgar todos los vectores del cluster actual."""
        self._ensure_initialized()
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=self._embedding_fn,
        )
        self._has_documents = False
        logger.info(f"VectorDB purgada para cluster actual.")

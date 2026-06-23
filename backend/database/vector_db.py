"""
Motor de búsqueda vectorial 100% local basado en TF-IDF + similitud coseno.

Ventajas vs ChromaDB + embeddings remotos:
  - Cero llamadas externas (no DNS, no rate-limits, no API keys)
  - RAM mínima (~5-20 MB para corpus típicos)
  - Sin modelos que descargar
  - Funciona en cualquier entorno Python (Render Free, local, offline)
  - Suficiente para retrieval de palabras clave en documentos normativos
"""
import logging
from typing import List, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger("VectorDB")

COLLECTION_NAME = "normativas_uagrm"


class VectorDB:
    """
    Wrapper ligero. Compatible con la interfaz anterior.
    Internamente: TF-IDFVectorizer + matriz sparse de documentos.
    """

    def __init__(self) -> None:
        self._vectorizer: TfidfVectorizer | None = None
        self._doc_matrix = None  # sparse matrix (n_docs, n_features)
        self._documents: List[str] = []
        self._metadatas: List[dict] = []
        self._ids: List[str] = []
        self._has_documents: bool = False
        logger.info(
            "Inicializando motor vectorial local (TF-IDF + cosine) · "
            "sin dependencias externas"
        )

    @property
    def collection_name(self) -> str:
        return COLLECTION_NAME

    def is_ready(self) -> bool:
        """True si hay al menos un documento indexado."""
        return self._has_documents

    def _ensure_vectorizer(self) -> TfidfVectorizer:
        if self._vectorizer is None:
            self._vectorizer = TfidfVectorizer(
                lowercase=True,
                strip_accents="unicode",
                analyzer="word",
                # FIX CRÍTICO: Permite buscar códigos como "187-6", "INF-110", "Z4" sin destruirlos
                token_pattern=r"(?u)\b[\w-]+\b",
                # FIX: Aumentado a (1, 3) para capturar frases clave de hasta 3 palabras juntas
                ngram_range=(1, 3),
                max_features=50000,
                sublinear_tf=True,
            )
        return self._vectorizer

    def add_documents(self, chunks) -> None:
        """Vectoriza e ingresa fragmentos de texto."""
        if not chunks:
            return

        new_docs = [chunk.page_content for chunk in chunks]
        new_metas = [chunk.metadata for chunk in chunks]
        new_ids = [
            f"{chunk.metadata.get('source', 'documento')}_{i}__{len(self._documents) + i}"
            for i, chunk in enumerate(chunks)
        ]

        self._documents.extend(new_docs)
        self._metadatas.extend(new_metas)
        self._ids.extend(new_ids)

        vectorizer = self._ensure_vectorizer()
        self._doc_matrix = vectorizer.fit_transform(self._documents)
        self._has_documents = self._doc_matrix.shape[0] > 0

        logger.info(
            f"Inyectados {len(chunks)} chunks · "
            f"total={self._doc_matrix.shape[0]} · "
            f"vocab={len(vectorizer.vocabulary_)}"
        )

    def rebuild_from_rows(self, rows) -> None:
        """Reconstruye el índice desde filas de la tabla `chunks`."""
        self._documents = [r.content for r in rows]
        self._metadatas = [{"source": r.source} for r in rows]
        self._ids = [f"{r.source}_{i}__{i}" for i, r in enumerate(rows)]
        self._vectorizer = None
        self._doc_matrix = None

        if not self._documents:
            self._has_documents = False
            logger.info("Reconstrucción: no hay chunks en la DB. Corpus vacío.")
            return

        vectorizer = self._ensure_vectorizer()
        self._doc_matrix = vectorizer.fit_transform(self._documents)
        self._has_documents = True
        logger.info(
            f"Reconstrucción: {len(self._documents)} chunks cargados desde DB · "
            f"vocab={len(vectorizer.vocabulary_)}"
        )

    # FIX: Aumentado el default a 15 resultados para permitir cruce de documentos múltiples
    def search(self, query: str, n_results: int = 15) -> dict:
        """Devuelve los n_results más similares por coseno."""
        if not self.is_ready():
            return {"documents": [[]], "metadatas": [[]]}

        vectorizer = self._ensure_vectorizer()
        query_vec = vectorizer.transform([query])

        sims = cosine_similarity(query_vec, self._doc_matrix).ravel()
        if sims.size == 0:
            return {"documents": [[]], "metadatas": [[]]}

        top_n = min(n_results, sims.size)
        top_idx = np.argsort(-sims)[:top_n]

        top_docs = [self._documents[i] for i in top_idx]
        top_metas = [self._metadatas[i] for i in top_idx]
        return {
            "documents": [top_docs],
            "metadatas": [top_metas],
        }

    def reset(self) -> None:
        """Purgar todos los documentos del cluster."""
        self._vectorizer = None
        self._doc_matrix = None
        self._documents = []
        self._metadatas = []
        self._ids = []
        self._has_documents = False
        logger.info("VectorDB purgada.")
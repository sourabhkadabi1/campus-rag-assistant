"""
Local embedding service using sentence-transformers (bge-small-en-v1.5).
No API cost — runs entirely on the local machine.
Dimension: 384.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded global model reference
_model: Optional[object] = None


def load_model():
    """
    Load the sentence-transformers model into memory.
    Called once at application startup.
    """
    global _model
    if _model is not None:
        return _model

    from sentence_transformers import SentenceTransformer

    name = settings.embedding_model_name
    logger.info("Loading embedding model: %s …", name)
    _model = SentenceTransformer(name)
    dim = _model.get_sentence_embedding_dimension()
    logger.info("Embedding model ready  (dimension=%d)", dim)
    return _model


def get_embedding(text: str) -> list[float]:
    """Return the normalised embedding vector for *text*."""
    model = load_model()
    vec = model.encode(text, normalize_embeddings=True)
    return vec.tolist()


def get_embeddings_batch(
    texts: list[str], batch_size: int = 32
) -> list[list[float]]:
    """Return normalised embeddings for a list of texts."""
    model = load_model()
    vecs = model.encode(texts, batch_size=batch_size, normalize_embeddings=True)
    return [v.tolist() for v in vecs]


def get_dimension() -> int:
    """Return the embedding dimension (384 for bge-small)."""
    model = load_model()
    return model.get_sentence_embedding_dimension()

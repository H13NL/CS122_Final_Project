"""
Sentence embeddings for keyword analysis.

The encoder is loaded lazily so Django startup and ordinary collection runs
never import torch. Vectors are stored in SQLite as raw float32 blobs, which
keeps the database self-contained and avoids a separate vector service.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_BATCH_SIZE = 64


def model_name() -> str:
    """Return the configured sentence-transformers model."""
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL_NAME)


@lru_cache(maxsize=2)
def get_encoder(name: str | None = None):
    """Load and cache one SentenceTransformer instance."""
    name = name or model_name()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Run: uv sync"
        ) from exc

    logger.info("Loading sentence-embedding model %s", name)
    return SentenceTransformer(name)


def embedding_dim(name: str | None = None) -> int:
    """Return the vector width of the configured model."""
    encoder = get_encoder(name)

    get_dimension = getattr(encoder, "get_embedding_dimension", None)
    if get_dimension is None:
        get_dimension = encoder.get_sentence_embedding_dimension

    return int(get_dimension())


def encode(
    texts: Sequence[str],
    batch_size: int = DEFAULT_BATCH_SIZE,
    name: str | None = None,
) -> np.ndarray:
    """Encode texts into L2-normalized float32 vectors."""
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    vectors = get_encoder(name).encode(
        list(texts),
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    return np.asarray(vectors, dtype=np.float32)


def to_blob(vector: np.ndarray) -> bytes:
    """Serialize one vector as little-endian float32 bytes."""
    return np.ascontiguousarray(vector, dtype=np.float32).tobytes()


def from_blob(blob: bytes, dim: int) -> np.ndarray:
    """Deserialize a float32 blob, checking its declared width."""
    vector = np.frombuffer(blob, dtype=np.float32)

    if vector.size != dim:
        raise ValueError(
            f"Embedding blob holds {vector.size} values, expected {dim}"
        )

    return vector


def vector_norm(vector: np.ndarray) -> float:
    """Return the L2 norm of one vector."""
    return float(np.linalg.norm(vector))


def cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine similarity, treating zero vectors as unrelated."""
    denominator = vector_norm(left) * vector_norm(right)

    if denominator == 0:
        return 0.0

    return float(np.dot(left, right) / denominator)

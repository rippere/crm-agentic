"""
Sentence-embedding service using all-MiniLM-L6-v2 (384 dims, ~80 MB).
Model is loaded once at first call and reused.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer  # deferred — heavy import

    return SentenceTransformer(MODEL_NAME)


def embed_text(text: str) -> list[float]:
    """Return a 384-dim unit-norm embedding for *text*."""
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()


def contact_text(name: str | None, company: str | None, role: str | None, email: str | None) -> str:
    """Build a short document that represents a contact for embedding."""
    parts = [p for p in (name, role, company, email) if p]
    return " | ".join(parts) if parts else "unknown contact"

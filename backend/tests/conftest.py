"""Shared test setup: an in-memory Qdrant and a FAKE embedder.

The fake embedder turns words into a small vector by hashing, so tests run in
milliseconds and need no model download. It only tests our plumbing, not the
quality of a real model (that is what app/evaluate.py is for).
"""
import hashlib
import re

import pytest

from app import embedder, jobs, search, store
from app.config import settings

DIM = 64


def fake_vector(text: str) -> list[float]:
    vector = [0.0] * DIM
    for word in re.findall(r"[a-z]+", text.lower()):
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = sum(x * x for x in vector) ** 0.5 or 1.0
    return [x / norm for x in vector]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "qdrant_path", ":memory:")
    monkeypatch.setattr(settings, "sources_path", str(tmp_path / "sources"))
    monkeypatch.setattr(
        embedder,
        "embed_chunks",
        lambda chunks: [fake_vector(embedder.embedding_text(c)) for c in chunks],
    )
    monkeypatch.setattr(embedder, "embed_query", fake_vector)
    store.reset_client()
    search._keyword_cache.clear()
    jobs.STATUS.clear()
    yield
    store.reset_client()

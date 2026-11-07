"""Qdrant storage: one collection, every point labelled with its repo."""
import re
import threading
import uuid
from typing import Callable

from qdrant_client import QdrantClient, models

from . import embedder
from .chunker import Chunk
from .config import settings

# The local Qdrant client is used from the web server AND from the indexing
# thread, so every call to it happens while holding this lock.
_lock = threading.RLock()
_client: QdrantClient | None = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.qdrant_path == ":memory:":
            _client = QdrantClient(":memory:")
        else:
            _client = QdrantClient(path=settings.qdrant_path)
    return _client


def reset_client() -> None:
    """Close and forget the client (used by tests)."""
    global _client
    with _lock:
        if _client is not None:
            _client.close()
        _client = None


def collection_name() -> str:
    # One collection per embedding model: vectors from different models have
    # different sizes and can never be mixed.
    slug = re.sub(r"[^a-z0-9]+", "_", settings.embedding_model.lower()).strip("_")
    return f"code_{slug}"


def point_id(repo: str, chunk: Chunk) -> str:
    """A stable UUID from repo + path + lines. Re-indexing gives the same ids,
    so old points are replaced instead of duplicated."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{repo}:{chunk.citation}"))


def _repo_filter(repo: str) -> models.Filter:
    return models.Filter(
        must=[models.FieldCondition(key="repo", match=models.MatchValue(value=repo))]
    )


def _to_chunk(payload: dict) -> Chunk:
    return Chunk(**{key: value for key, value in payload.items() if key != "repo"})


def index_chunks(
    repo: str,
    chunks: list[Chunk],
    on_progress: Callable[[int, int], None] | None = None,
) -> None:
    """Embed the chunks (in batches) and store them, replacing the repo's old chunks."""
    client = _get_client()
    total = len(chunks)
    step = settings.embed_batch_size * 2
    done = 0
    for i in range(0, total, step):
        part = chunks[i : i + step]
        vectors = embedder.embed_chunks(part)  # slow part: done OUTSIDE the lock
        points = [
            models.PointStruct(
                id=point_id(repo, chunk),
                vector=vector,
                payload={**chunk.model_dump(), "repo": repo},
            )
            for chunk, vector in zip(part, vectors)
        ]
        with _lock:
            if i == 0:
                name = collection_name()
                if not client.collection_exists(name):
                    client.create_collection(
                        name,
                        vectors_config=models.VectorParams(
                            size=len(vectors[0]), distance=models.Distance.COSINE
                        ),
                    )
                client.delete(
                    name, points_selector=models.FilterSelector(filter=_repo_filter(repo))
                )
            client.upsert(collection_name(), points=points)
        done += len(part)
        if on_progress:
            on_progress(done, total)


def search_vector(repo: str, question: str, limit: int) -> list[Chunk]:
    """The `limit` chunks of this repo closest in meaning to the question."""
    vector = embedder.embed_query(question)
    client = _get_client()
    with _lock:
        if not client.collection_exists(collection_name()):
            return []
        result = client.query_points(
            collection_name(),
            query=vector,
            query_filter=_repo_filter(repo),
            limit=limit,
            with_payload=True,
        )
    return [_to_chunk(point.payload) for point in result.points]


def load_chunks(repo: str) -> list[Chunk]:
    """All stored chunks of a repo (used to build the keyword index)."""
    client = _get_client()
    chunks: list[Chunk] = []
    offset = None
    with _lock:
        if not client.collection_exists(collection_name()):
            return []
        while True:
            points, offset = client.scroll(
                collection_name(),
                scroll_filter=_repo_filter(repo),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            chunks.extend(_to_chunk(point.payload) for point in points)
            if offset is None:
                break
    return sorted(chunks, key=lambda c: (c.path, c.start_line))
"""Hybrid search: vector search + keyword search, merged with Reciprocal Rank Fusion."""
from typing import Literal

from pydantic import BaseModel

from . import store
from .chunker import Chunk
from .config import settings
from .keyword import KeywordIndex

Mode = Literal["hybrid", "vector", "keyword"]


class Hit(BaseModel):
    chunk: Chunk
    score: float
    vector_rank: int | None = None   # position in the vector list (None = not found there)
    keyword_rank: int | None = None  # position in the keyword list


# The BM25 index lives in memory. It is rebuilt from Qdrant when needed,
# so it also works after a server restart.
_keyword_cache: dict[str, KeywordIndex] = {}


def forget(repo: str) -> None:
    _keyword_cache.pop(repo, None)


def _keyword_index(repo: str) -> KeywordIndex:
    if repo not in _keyword_cache:
        _keyword_cache[repo] = KeywordIndex(store.load_chunks(repo))
    return _keyword_cache[repo]


def rrf(rankings: list[list[str]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion: every list gives 1 / (k + rank) to each item in it."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    return scores


def search(repo: str, question: str, limit: int = 8, mode: Mode = "hybrid") -> list[Hit]:
    n = settings.candidate_k
    vector_list = store.search_vector(repo, question, n) if mode != "keyword" else []
    keyword_list = _keyword_index(repo).search(question, n) if mode != "vector" else []

    by_key = {c.citation: c for c in vector_list + keyword_list}
    vector_rank = {c.citation: i for i, c in enumerate(vector_list, start=1)}
    keyword_rank = {c.citation: i for i, c in enumerate(keyword_list, start=1)}

    scores = rrf(
        [[c.citation for c in vector_list], [c.citation for c in keyword_list]],
        settings.rrf_k,
    )
    best = sorted(scores, key=lambda key: scores[key], reverse=True)[:limit]
    return [
        Hit(
            chunk=by_key[key],
            score=round(scores[key], 5),
            vector_rank=vector_rank.get(key),
            keyword_rank=keyword_rank.get(key),
        )
        for key in best
    ]
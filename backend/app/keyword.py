"""Keyword search with BM25, made code-friendly by splitting identifiers.

BM25 gives each chunk a score for a question, from three simple ideas:
  1. a RARE word counts more than a common one          (idf)
  2. a word repeated many times helps, but less and less (saturation, k1)
  3. a very long chunk is slightly penalised             (length, b)
"""
import math
import re
from collections import Counter

from .chunker import Chunk

STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "of", "in", "on", "at",
    "to", "and", "or", "for", "from", "with", "by", "as", "it", "this", "that",
    "which", "what", "where", "when", "how", "does", "do", "i",
}

_WORDS = re.compile(r"[A-Za-z0-9_]+")
# pieces of an identifier: HTTP | Server | Error | 2 | snake | case
_PARTS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")

K1 = 1.5   # how fast repeated words stop helping
B = 0.75   # how much long chunks are penalised


def tokenize(text: str) -> list[str]:
    """Words of the text, where each identifier gives the whole name AND its parts.

        make_pass_decorator -> make_pass_decorator, make, pass, decorator
        HTTPServerError     -> httpservererror, http, server, error
    """
    tokens: list[str] = []
    for word in _WORDS.findall(text):
        parts = [p.lower() for p in _PARTS.findall(word)]
        if len(parts) > 1:
            tokens.append(word.lower())  # keep the whole identifier too
        tokens.extend(parts)
    return [t for t in tokens if t not in STOPWORDS]


def _document(chunk: Chunk) -> list[str]:
    # path and symbol are included: a function's name is the best clue about it
    return tokenize(f"{chunk.path} {chunk.symbol} {chunk.text}")


class KeywordIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self.counts = [Counter(_document(c)) for c in chunks]
        self.lengths = [sum(c.values()) for c in self.counts]
        self.avg_length = (sum(self.lengths) / len(chunks)) if chunks else 0.0

        # postings: word -> which chunks contain it
        self.postings: dict[str, list[int]] = {}
        for i, counts in enumerate(self.counts):
            for word in counts:
                self.postings.setdefault(word, []).append(i)

        n = len(chunks)
        # always positive, even in a tiny repository
        self.idf = {
            word: math.log(1 + (n - len(docs) + 0.5) / (len(docs) + 0.5))
            for word, docs in self.postings.items()
        }

    def _score(self, i: int, words: set[str]) -> float:
        counts, length = self.counts[i], self.lengths[i]
        norm = K1 * (1 - B + B * length / self.avg_length)
        return sum(
            self.idf[w] * counts[w] * (K1 + 1) / (counts[w] + norm)
            for w in words
            if w in counts
        )

    def search(self, question: str, limit: int) -> list[Chunk]:
        """The best-matching chunks, best first. Chunks with no match are left out."""
        words = {w for w in tokenize(question) if w in self.postings}
        candidates = {i for w in words for i in self.postings[w]}
        scored = sorted(
            ((self._score(i, words), i) for i in candidates), reverse=True
        )
        return [self.chunks[i] for _, i in scored[:limit]]
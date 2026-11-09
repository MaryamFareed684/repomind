"""Indexing jobs: download -> read files -> chunk -> embed -> store.

A job runs in the background. Its progress lives in STATUS, which the frontend polls.
"""
import asyncio
import logging
from collections import Counter
from typing import Literal

import httpx
from pydantic import BaseModel

from . import search, sources, store
from .chunker import chunk_repo
from .github import RepoError, download_zip, extract_files

logger = logging.getLogger("repomind")


class FileSummary(BaseModel):
    path: str
    language: str
    size: int


class IndexStatus(BaseModel):
    repo: str                                   # "owner/name", lower case
    branch: str
    state: Literal["queued", "indexing", "ready", "failed"] = "queued"
    done: int = 0                               # chunks embedded so far
    total: int = 0                              # chunks to embed
    file_count: int = 0
    chunk_count: int = 0
    languages: dict[str, int] = {}
    files: list[FileSummary] = []
    error: str | None = None


STATUS: dict[str, IndexStatus] = {}


def get_status(repo: str) -> IndexStatus | None:
    return STATUS.get(repo)


def start(repo: str, branch: str) -> IndexStatus:
    STATUS[repo] = IndexStatus(repo=repo, branch=branch)
    return STATUS[repo]


def process_zip(repo: str, zip_bytes: bytes) -> None:
    """The slow, CPU-heavy part. Runs in a worker thread."""
    status = STATUS[repo]
    files = extract_files(zip_bytes)
    if not files:
        raise RepoError("No indexable source files found.", 422)
    chunks = chunk_repo(files)
    sources.save(repo, files)  # the code viewer reads these later

    status.files = [FileSummary(path=f.path, language=f.language, size=f.size) for f in files]
    status.file_count = len(files)
    status.languages = dict(Counter(f.language for f in files))
    status.total = len(chunks)

    def on_progress(done: int, total: int) -> None:
        status.done = done

    store.index_chunks(repo, chunks, on_progress)
    search.forget(repo)  # the keyword index must be rebuilt from the new chunks
    status.chunk_count = len(chunks)
    status.state = "ready"


def _fail(status: IndexStatus, message: str) -> None:
    status.state = "failed"
    status.error = message


async def run_index(owner: str, name: str, branch: str) -> None:
    repo = f"{owner}/{name}".lower()
    status = STATUS[repo]
    try:
        status.state = "indexing"
        async with httpx.AsyncClient(timeout=30) as client:
            zip_bytes = await download_zip(client, owner, name, branch)
        # embedding is CPU work: run it in a thread so the server keeps answering
        await asyncio.to_thread(process_zip, repo, zip_bytes)
    except RepoError as err:
        _fail(status, err.message)
    except httpx.HTTPError:
        _fail(status, "Could not reach GitHub.")
    except Exception:
        logger.exception("Indexing %s failed", repo)  # details go to the log only
        _fail(status, "Indexing failed unexpectedly.")

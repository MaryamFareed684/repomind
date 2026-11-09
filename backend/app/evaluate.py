"""Measure retrieval quality on YOUR questions.

    python -m app.evaluate https://github.com/MaryamFareed684/researchpilot ../eval/eval_set.json

It indexes the repo with the CURRENT embedding model (EMBEDDING_MODEL in .env), then,
for every question, checks where the expected file shows up in the results of
vector search, keyword search and hybrid search. The numbers are saved next to
the question file as retrieval_<model>.json.
"""
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

from . import jobs, search, store
from .config import settings
from .github import download_zip, get_repo_info, parse_repo_url

MODES = ("vector", "keyword", "hybrid")


def ranked_files(hits: list[search.Hit]) -> list[str]:
    """The files of the hits, best first, each file listed once."""
    files: list[str] = []
    for hit in hits:
        if hit.chunk.path not in files:
            files.append(hit.chunk.path)
    return files


def first_rank(files: list[str], expected: list[str]) -> int | None:
    """Position (1 = first) of the first expected file, or None if it is missing."""
    for position, path in enumerate(files, start=1):
        if path in expected:
            return position
    return None


def summarize(ranks: list[int | None]) -> dict[str, float]:
    n = len(ranks) or 1

    def hit_at(k: int) -> float:
        return round(sum(1 for r in ranks if r is not None and r <= k) / n, 3)

    mrr = round(sum(1 / r for r in ranks if r is not None) / n, 3)
    return {"hit@1": hit_at(1), "hit@3": hit_at(3), "hit@5": hit_at(5), "mrr": mrr}


async def main(url: str, questions_path: str) -> None:
    path = Path(questions_path)
    questions = json.loads(path.read_text(encoding="utf-8"))

    owner, name = parse_repo_url(url)
    repo = f"{owner}/{name}".lower()
    async with httpx.AsyncClient(timeout=30) as client:
        info = await get_repo_info(client, owner, name)
        branch = info.get("default_branch", "main")
        zip_bytes = await download_zip(client, owner, name, branch)

    print(f"Model: {settings.embedding_model}")
    print("Indexing ... (the first run downloads the model; do NOT press Ctrl+C, big models take minutes)")
    status = jobs.start(repo, branch)
    started = time.perf_counter()
    task = asyncio.create_task(asyncio.to_thread(jobs.process_zip, repo, zip_bytes))
    while not task.done():
        await asyncio.sleep(2)
        print(f"\r  embedded {status.done}/{status.total} chunks", end="", flush=True)
    await task  # raises here if indexing failed
    print()
    index_seconds = round(time.perf_counter() - started, 1)
    print(f"{status.file_count} files, {status.chunk_count} chunks, {index_seconds}s\n")

    ranks: dict[str, list[int | None]] = {mode: [] for mode in MODES}
    details = []
    for q in questions:
        row = {"id": q["id"], "question": q["question"], "expected": q["expected_files"]}
        for mode in MODES:
            files = ranked_files(search.search(repo, q["question"], limit=20, mode=mode))
            rank = first_rank(files, q["expected_files"])
            ranks[mode].append(rank)
            row[mode] = {"rank": rank, "top3": files[:3]}
        details.append(row)

    summary = {mode: summarize(ranks[mode]) for mode in MODES}
    print(f"{'mode':<9}{'hit@1':>7}{'hit@3':>7}{'hit@5':>7}{'mrr':>7}")
    for mode in MODES:
        s = summary[mode]
        print(f"{mode:<9}{s['hit@1']:>7}{s['hit@3']:>7}{s['hit@5']:>7}{s['mrr']:>7}")

    misses = [d for d in details if d["hybrid"]["rank"] is None or d["hybrid"]["rank"] > 3]
    if misses:
        print("\nHybrid did not put the expected file in the top 3 for:")
        for d in misses:
            print(f"  {d['id']} {d['question']}")
            print(f"     expected {d['expected']}, got {d['hybrid']['top3']}")

    slug = re.sub(r"[^a-z0-9]+", "_", settings.embedding_model.lower()).strip("_")
    out = path.parent / f"retrieval_{slug}.json"
    out.write_text(
        json.dumps(
            {
                "model": settings.embedding_model,
                "repo": repo,
                "chunks": status.chunk_count,
                "index_seconds": index_seconds,
                "questions": len(questions),
                "summary": summary,
                "details": details,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved {out}")
    store.reset_client()  # close Qdrant cleanly


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python -m app.evaluate <github-url> <eval_set.json>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))

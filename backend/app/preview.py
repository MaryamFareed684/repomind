"""Developer tool: see how a real repo gets chunked.

    python -m app.preview https://github.com/pallets/click
    python -m app.preview https://github.com/pallets/click core.py
The optional second argument shows every chunk of files whose path contains it.
"""
import asyncio
import sys
from collections import Counter

import httpx

from .chunker import chunk_repo
from .github import download_zip, extract_files, get_repo_info, parse_repo_url


async def main(url: str, only: str | None) -> None:
    owner, repo = parse_repo_url(url)
    async with httpx.AsyncClient(timeout=30) as client:
        info = await get_repo_info(client, owner, repo)
        zip_bytes = await download_zip(
            client, owner, repo, info.get("default_branch", "main")
        )
    files = extract_files(zip_bytes)
    chunks = chunk_repo(files)

    print(f"{len(files)} files -> {len(chunks)} chunks")
    print("by kind:", dict(Counter(c.kind for c in chunks)))
    print()

    shown = [c for c in chunks if only in c.path] if only else chunks[:25]
    for c in shown:
        first_line = c.text.split("\n")[0].strip()[:60]
        print(f"{c.citation:<45} {c.kind:<9} {c.symbol:<28} | {first_line}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m app.preview <github-url> [path-part]")
    asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))

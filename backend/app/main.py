from collections import Counter

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .github import (
    RepoError,
    download_zip,
    extract_files,
    get_repo_info,
    parse_repo_url,
)

app = FastAPI(title="RepoMind")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


class RepoRequest(BaseModel):
    url: str


class FileSummary(BaseModel):
    path: str
    language: str
    size: int


class RepoResponse(BaseModel):
    repo: str
    branch: str
    file_count: int
    languages: dict[str, int]
    files: list[FileSummary]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/repos", response_model=RepoResponse)
async def add_repo(req: RepoRequest):
    try:
        owner, repo = parse_repo_url(req.url)
        async with httpx.AsyncClient(timeout=30) as client:
            info = await get_repo_info(client, owner, repo)
            branch = info.get("default_branch", "main")
            zip_bytes = await download_zip(client, owner, repo, branch)
        files = extract_files(zip_bytes)
    except RepoError as err:
        raise HTTPException(status_code=err.status_code, detail=err.message)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub.")

    if not files:
        raise HTTPException(status_code=422, detail="No indexable source files found.")

    return RepoResponse(
        repo=f"{owner}/{repo}",
        branch=branch,
        file_count=len(files),
        languages=dict(Counter(f.language for f in files)),
        files=[FileSummary(path=f.path, language=f.language, size=f.size) for f in files],
    )
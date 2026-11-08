from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import ask as ask_module
from . import jobs, llm, store
from . import search as search_module
from .github import RepoError, get_repo_info, parse_repo_url
from .jobs import IndexStatus
from .search import Hit

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    store.reset_client()  # close the local Qdrant database cleanly on shutdown


app = FastAPI(title="RepoMind", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)


class RepoRequest(BaseModel):
    url: str
    refresh: bool = False  # true = index again even if it is already indexed


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/repos", response_model=IndexStatus, status_code=202)
async def add_repo(req: RepoRequest, background: BackgroundTasks):
    """Check the repo quickly, then index it in the background."""
    try:
        owner, name = parse_repo_url(req.url)
        repo = f"{owner}/{name}".lower()

        existing = jobs.get_status(repo)
        if existing and existing.state in ("queued", "indexing"):
            return existing
        if existing and existing.state == "ready" and not req.refresh:
            return existing

        async with httpx.AsyncClient(timeout=30) as client:
            info = await get_repo_info(client, owner, name)
    except RepoError as err:
        raise HTTPException(status_code=err.status_code, detail=err.message)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Could not reach GitHub.")

    branch = info.get("default_branch", "main")
    status = jobs.start(repo, branch)
    background.add_task(jobs.run_index, owner, name, branch)
    return status.model_copy()


@app.get("/repos/{owner}/{name}", response_model=IndexStatus)
def repo_status(owner: str, name: str):
    status = jobs.get_status(f"{owner}/{name}".lower())
    if status is None:
        raise HTTPException(status_code=404, detail="Repository has not been indexed.")
    return status


@app.get("/repos/{owner}/{name}/search", response_model=list[Hit])
def search_repo(
    owner: str,
    name: str,
    q: str = Query(min_length=1, max_length=500),
    mode: Literal["hybrid", "vector", "keyword"] = "hybrid",
    limit: int = Query(8, ge=1, le=20),
):
    repo = f"{owner}/{name}".lower()
    status = jobs.get_status(repo)
    if status is None:
        raise HTTPException(status_code=404, detail="Repository has not been indexed.")
    if status.state != "ready":
        raise HTTPException(status_code=409, detail=f"Repository is {status.state}.")
    return search_module.search(repo, q, limit=limit, mode=mode)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@app.post("/repos/{owner}/{name}/ask", response_model=ask_module.AskResponse)
async def ask_repo(owner: str, name: str, req: AskRequest):
    repo = f"{owner}/{name}".lower()
    status = jobs.get_status(repo)
    if status is None:
        raise HTTPException(status_code=404, detail="Repository has not been indexed.")
    if status.state != "ready":
        raise HTTPException(status_code=409, detail=f"Repository is {status.state}.")
    try:
        return await ask_module.ask(repo, req.question.strip())
    except llm.LLMError as err:
        raise HTTPException(status_code=err.status_code, detail=err.message)

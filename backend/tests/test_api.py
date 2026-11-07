import pytest
from fastapi.testclient import TestClient

from app import jobs, main
from app.github import RepoError
from app.main import app
from tests.test_ingestion import make_zip

client = TestClient(app)

REPO_FILES = {
    "src/auth.py": b"def verify_password(user, password):\n    return True\n",
    "README.md": b"# Demo project",
    ".env": b"SECRET=1",
}


@pytest.fixture
def fake_github(monkeypatch):
    calls = {"info": 0}

    async def fake_info(client, owner, repo):
        calls["info"] += 1
        return {"default_branch": "main"}

    async def fake_zip(client, owner, repo, branch):
        return make_zip(REPO_FILES)

    monkeypatch.setattr(main, "get_repo_info", fake_info)
    monkeypatch.setattr(jobs, "download_zip", fake_zip)
    return calls


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_bad_url_gives_400():
    resp = client.post("/repos", json={"url": "nonsense"})
    assert resp.status_code == 400
    assert "github.com/owner/repo" in resp.json()["detail"]


def test_index_happy_path(fake_github):
    resp = client.post("/repos", json={"url": "https://github.com/Owner/Repo"})
    assert resp.status_code == 202
    assert resp.json()["state"] == "queued"
    assert resp.json()["repo"] == "owner/repo"          # lower-cased

    status = client.get("/repos/Owner/Repo").json()     # background job has finished
    assert status["state"] == "ready"
    assert status["file_count"] == 2
    assert status["chunk_count"] >= 2
    assert status["done"] == status["total"] == status["chunk_count"]
    assert all(f["path"] != ".env" for f in status["files"])


def test_second_post_does_not_index_again(fake_github):
    client.post("/repos", json={"url": "https://github.com/o/r"})
    client.post("/repos", json={"url": "https://github.com/o/r"})
    assert fake_github["info"] == 1
    client.post("/repos", json={"url": "https://github.com/o/r", "refresh": True})
    assert fake_github["info"] == 2


def test_search_endpoint(fake_github):
    client.post("/repos", json={"url": "https://github.com/o/r"})
    resp = client.get("/repos/o/r/search", params={"q": "verify password"})
    assert resp.status_code == 200
    hits = resp.json()
    assert hits[0]["chunk"]["path"] == "src/auth.py"
    assert hits[0]["chunk"]["symbol"] == "verify_password"
    assert set(hits[0]) == {"chunk", "score", "vector_rank", "keyword_rank"}


def test_search_validation_and_states(fake_github):
    assert client.get("/repos/o/none/search", params={"q": "x"}).status_code == 404
    assert client.get("/repos/o/none").status_code == 404

    jobs.STATUS["o/busy"] = jobs.IndexStatus(repo="o/busy", branch="main", state="indexing")
    assert client.get("/repos/o/busy/search", params={"q": "x"}).status_code == 409

    client.post("/repos", json={"url": "https://github.com/o/r"})
    assert client.get("/repos/o/r/search", params={"q": ""}).status_code == 422
    assert client.get("/repos/o/r/search", params={"q": "x", "limit": 99}).status_code == 422
    assert client.get("/repos/o/r/search", params={"q": "x", "mode": "bad"}).status_code == 422


def test_failed_download_is_reported_in_status(monkeypatch):
    async def fake_info(client, owner, repo):
        return {"default_branch": "main"}

    async def broken_zip(client, owner, repo, branch):
        raise RepoError("Repository download is too large.", 413)

    monkeypatch.setattr(main, "get_repo_info", fake_info)
    monkeypatch.setattr(jobs, "download_zip", broken_zip)

    client.post("/repos", json={"url": "https://github.com/o/r"})
    status = client.get("/repos/o/r").json()
    assert status["state"] == "failed"
    assert status["error"] == "Repository download is too large."
    assert client.get("/repos/o/r/search", params={"q": "x"}).status_code == 409


def test_unexpected_error_does_not_leak_details(monkeypatch, fake_github):
    def boom(repo, zip_bytes):
        raise RuntimeError("secret internal path /srv/x")

    monkeypatch.setattr(jobs, "process_zip", boom)
    client.post("/repos", json={"url": "https://github.com/o/r"})
    status = client.get("/repos/o/r").json()
    assert status["state"] == "failed"
    assert "secret" not in status["error"]


def test_repo_with_no_source_files_fails_cleanly(monkeypatch):
    async def fake_info(client, owner, repo):
        return {"default_branch": "main"}

    async def fake_zip(client, owner, repo, branch):
        return make_zip({"logo.png": b"\x89PNG\x00", ".env": b"K=1"})

    monkeypatch.setattr(main, "get_repo_info", fake_info)
    monkeypatch.setattr(jobs, "download_zip", fake_zip)
    client.post("/repos", json={"url": "https://github.com/o/r"})
    status = client.get("/repos/o/r").json()
    assert status["state"] == "failed"
    assert "No indexable" in status["error"]

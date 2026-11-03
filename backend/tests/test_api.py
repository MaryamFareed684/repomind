from fastapi.testclient import TestClient

from app import main
from app.main import app
from tests.test_ingestion import make_zip

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_bad_url_gives_400():
    resp = client.post("/repos", json={"url": "nonsense"})
    assert resp.status_code == 400
    assert "github.com/owner/repo" in resp.json()["detail"]


def test_repos_happy_path(monkeypatch):
    async def fake_info(client, owner, repo):
        return {"default_branch": "main"}

    async def fake_zip(client, owner, repo, branch):
        return make_zip({"src/app.py": b"x = 1\n", "README.md": b"# hi", ".env": b"K=1"})

    monkeypatch.setattr(main, "get_repo_info", fake_info)
    monkeypatch.setattr(main, "download_zip", fake_zip)

    resp = client.post("/repos", json={"url": "https://github.com/a/b"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["repo"] == "a/b"
    assert body["file_count"] == 2
    assert body["languages"] == {"markdown": 1, "python": 1}
    assert all(".env" != f["path"] for f in body["files"])

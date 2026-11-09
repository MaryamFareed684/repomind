import io
import stat
import zipfile

import httpx
import pytest

from app import github
from app.filters import is_secret_file, should_index
from app.github import RepoError, extract_files, parse_repo_url


# ---------- URL validation ----------
@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/pallets/flask", ("pallets", "flask")),
        ("https://github.com/pallets/flask/", ("pallets", "flask")),
        ("https://github.com/pallets/flask.git", ("pallets", "flask")),
        ("http://www.github.com/a/b.c", ("a", "b.c")),
    ],
)
def test_parse_good_urls(url, expected):
    assert parse_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "https://gitlab.com/a/b",
        "https://github.com/onlyowner",
        "https://github.com/a/b/tree/main",
        "https://github.com/../..",
        "https://evil.com/?u=https://github.com/a/b",
    ],
)
def test_parse_bad_urls(url):
    with pytest.raises(RepoError):
        parse_repo_url(url)


# ---------- file filtering ----------
def test_should_index_rules():
    assert should_index("src/app.py", 100)
    assert should_index("README.md", 100)
    assert not should_index("node_modules/x/index.js", 100)  # skipped folder
    assert not should_index("package-lock.json", 100)         # lock file
    assert not should_index(".env", 10)                       # secret
    assert not is_secret_file(".env.example")                 # placeholders only
    assert not should_index("keys/server.pem", 10)            # secret
    assert not should_index("logo.png", 100)                  # not allowed type
    assert not should_index("static/app.min.js", 100)         # minified
    assert not should_index("big.py", 10_000_000)             # too large
    assert not should_index("empty.py", 0)
    assert not should_index("../evil.py", 10)                 # path trick
    assert not should_index("eval/results.json", 16_000)      # big json = data, not code
    assert should_index("package.json", 700)                  # small json = config


# ---------- zip extraction ----------
def make_zip(entries: dict[str, bytes], symlinks: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(f"repo-main/{name}", content)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(f"repo-main/{name}")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, target)
    return buf.getvalue()


def test_extract_keeps_only_good_files():
    data = make_zip(
        {
            "src/app.py": b"def hi():\n    return 1\n",
            "README.md": b"# Hello",
            ".env": b"SECRET=abc",
            "package-lock.json": b"{}",
            "node_modules/a/b.js": b"x",
            "logo.png": b"\x89PNG\x00\x00",
            "data.py": b"\x00\x01\x02binary-looking",
            "bundle.js": b"a" * 5000,  # one giant line = minified
        },
        symlinks={"link.py": "../../etc/passwd"},
    )
    files = extract_files(data)
    assert [f.path for f in files] == ["README.md", "src/app.py"]
    assert files[1].language == "python"


def test_extract_rejects_bad_zip():
    with pytest.raises(RepoError):
        extract_files(b"this is not a zip")


def test_extract_rejects_too_many_files(monkeypatch):
    monkeypatch.setattr(github.settings, "max_files", 2)
    data = make_zip({f"f{i}.py": b"x = 1\n" for i in range(5)})
    with pytest.raises(RepoError) as err:
        extract_files(data)
    assert err.value.status_code == 413


# ---------- GitHub calls (faked with MockTransport, no internet needed) ----------
def client_with(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_get_repo_info_not_found():
    client = client_with(lambda req: httpx.Response(404))
    with pytest.raises(RepoError) as err:
        await github.get_repo_info(client, "a", "b")
    assert err.value.status_code == 404


@pytest.mark.asyncio
async def test_get_repo_info_rate_limited():
    client = client_with(lambda req: httpx.Response(403))
    with pytest.raises(RepoError) as err:
        await github.get_repo_info(client, "a", "b")
    assert err.value.status_code == 429


@pytest.mark.asyncio
async def test_get_repo_info_too_big_and_private():
    big = client_with(lambda req: httpx.Response(200, json={"size": 10**9, "private": False}))
    with pytest.raises(RepoError):
        await github.get_repo_info(big, "a", "b")
    priv = client_with(lambda req: httpx.Response(200, json={"size": 1, "private": True}))
    with pytest.raises(RepoError):
        await github.get_repo_info(priv, "a", "b")


@pytest.mark.asyncio
async def test_download_stops_when_too_large(monkeypatch):
    monkeypatch.setattr(github.settings, "max_zip_bytes", 100)
    client = client_with(lambda req: httpx.Response(200, content=b"x" * 1000))
    with pytest.raises(RepoError) as err:
        await github.download_zip(client, "a", "b", "main")
    assert err.value.status_code == 413


@pytest.mark.asyncio
async def test_token_is_never_sent_to_codeload(monkeypatch):
    monkeypatch.setattr(github.settings, "github_token", "SECRET_TOKEN")
    seen = {}

    def handler(req: httpx.Request):
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, content=make_zip({"a.py": b"x = 1\n"}))

    await github.download_zip(client_with(handler), "a", "b", "main")
    assert seen["auth"] is None

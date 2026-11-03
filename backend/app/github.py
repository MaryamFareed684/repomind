"""Fetch a public GitHub repo safely: validate URL, check size, download zip,
read files in memory. Nothing from the repo is ever executed or written to disk.
"""
import io
import re
import stat
import zipfile
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from .config import settings
from .filters import is_probably_text, language_of, looks_minified, should_index

GITHUB_URL_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)


class RepoError(Exception):
    """An error we are happy to show to the user."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class RepoFile(BaseModel):
    path: str
    language: str
    size: int
    text: str


def parse_repo_url(url: str) -> tuple[str, str]:
    match = GITHUB_URL_RE.match(url.strip())
    if not match:
        raise RepoError("Enter a URL like https://github.com/owner/repo")
    owner, repo = match.groups()
    if owner.strip(".") == "" or repo.strip(".") == "":
        raise RepoError("Enter a URL like https://github.com/owner/repo")
    return owner, repo


def _api_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "repomind"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


async def get_repo_info(client: httpx.AsyncClient, owner: str, repo: str) -> dict:
    """One small API call: does it exist, is it public, default branch, size."""
    resp = await client.get(
        f"https://api.github.com/repos/{owner}/{repo}", headers=_api_headers()
    )
    if resp.status_code == 404:
        raise RepoError("Repository not found, or it is private.", 404)
    if resp.status_code in (403, 429):
        raise RepoError("GitHub rate limit reached. Please try again later.", 429)
    if resp.status_code != 200:
        raise RepoError("GitHub returned an unexpected error.", 502)

    info = resp.json()
    if info.get("private"):
        raise RepoError("Private repositories are not supported.", 403)
    if info.get("size", 0) > settings.max_repo_kb:
        raise RepoError("Repository is too large for this demo.", 413)
    return info


async def download_zip(
    client: httpx.AsyncClient, owner: str, repo: str, branch: str
) -> bytes:
    """Download the whole repo as one zip, stopping if it gets too big.

    We do NOT send the GitHub token here: public repos don't need it.
    """
    url = (
        f"https://codeload.github.com/{owner}/{repo}"
        f"/zip/refs/heads/{quote(branch, safe='/')}"
    )
    data = bytearray()
    async with client.stream("GET", url, follow_redirects=True) as resp:
        if resp.status_code != 200:
            raise RepoError("Could not download the repository.", 502)
        async for chunk in resp.aiter_bytes():
            data.extend(chunk)
            if len(data) > settings.max_zip_bytes:
                raise RepoError("Repository download is too large.", 413)
    return bytes(data)


def extract_files(zip_bytes: bytes) -> list[RepoFile]:
    """Read eligible text files from the zip, in memory."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise RepoError("Downloaded file was not a valid zip.", 502)

    files: list[RepoFile] = []
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if sum(i.file_size for i in infos) > settings.max_uncompressed_bytes:
            raise RepoError("Repository is too large when unpacked.", 413)

        for info in infos:
            # Zip entries look like "repo-main/src/app.py": drop the top folder.
            _, _, path = info.filename.partition("/")
            if not path:
                continue
            # Skip symlinks: their "content" is just a target path.
            if stat.S_ISLNK(info.external_attr >> 16):
                continue
            if not should_index(path, info.file_size):
                continue

            raw = zf.read(info)
            if not is_probably_text(raw):
                continue
            text = raw.decode("utf-8", errors="replace")
            if looks_minified(text):
                continue

            files.append(
                RepoFile(
                    path=path,
                    language=language_of(path) or "text",
                    size=len(raw),
                    text=text,
                )
            )
            if len(files) > settings.max_files:
                raise RepoError(
                    f"Repository has more than {settings.max_files} indexable files.", 413
                )

    files.sort(key=lambda f: f.path)
    return files
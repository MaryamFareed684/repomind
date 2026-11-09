"""Keep the full text of indexed files on disk so the code viewer can show them.

Chunks are only pieces. To show a cited line in context we need the whole file.
Files live on disk (not in memory) so a big repo does not use up RAM.
"""
import shutil
from pathlib import Path

from .config import settings
from .github import RepoFile


def _folder(repo: str) -> Path:
    return Path(settings.sources_path) / repo.replace("/", "__")


def _safe(folder: Path, path: str) -> Path | None:
    """The file's place inside `folder`, or None if the path tries to escape it."""
    target = (folder / path).resolve()
    if folder.resolve() not in target.parents:
        return None
    return target


def save(repo: str, files: list[RepoFile]) -> None:
    folder = _folder(repo)
    shutil.rmtree(folder, ignore_errors=True)  # a refresh replaces the old copy
    for file in files:
        target = _safe(folder, file.path)
        if target is None:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file.text, encoding="utf-8", newline="")


def read(repo: str, path: str) -> str | None:
    target = _safe(_folder(repo), path)
    if target is None or not target.is_file():
        return None
    return target.read_text(encoding="utf-8", newline="")

"""Decide which files in a repository are worth indexing.

We use an ALLOW-list of extensions (safer than trying to block every binary
type) plus a SKIP-list of folders, lock files and secret-looking files.
"""
from pathlib import PurePosixPath

from .config import settings

SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", "__pycache__", "dist",
    "build", ".next", ".idea", ".vscode", "site-packages", "vendor",
    "target", ".tox", ".pytest_cache", ".mypy_cache", "coverage",
}

SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "composer.lock", "Cargo.lock", "uv.lock", ".DS_Store",
}

SECRET_EXTENSIONS = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"}
SECRET_NAMES = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials"}
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template")

LANGUAGES = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java", ".go": "go",
    ".rs": "rust", ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp",
    ".rb": "ruby", ".php": "php", ".sh": "shell", ".sql": "sql",
    ".html": "html", ".css": "css",
    ".md": "markdown", ".rst": "text", ".txt": "text",
    ".toml": "config", ".yaml": "config", ".yml": "config",
    ".json": "config", ".ini": "config", ".cfg": "config",
}
# Files with no extension that are still useful
KNOWN_NAMES = {"Dockerfile": "docker", "Makefile": "make"}


def is_secret_file(name: str) -> bool:
    lower = name.lower()
    if lower.startswith(".env"):
        return not lower.endswith(SAFE_ENV_SUFFIXES)
    return lower in SECRET_NAMES or PurePosixPath(lower).suffix in SECRET_EXTENSIONS


def language_of(path: str) -> str | None:
    p = PurePosixPath(path)
    return KNOWN_NAMES.get(p.name) or LANGUAGES.get(p.suffix.lower())


def should_index(path: str, size: int) -> bool:
    """Cheap checks using only the path and size (before reading the file)."""
    p = PurePosixPath(path)
    parts = p.parts
    if not parts or p.is_absolute() or ".." in parts:
        return False
    if any(part in SKIP_DIRS for part in parts[:-1]):
        return False
    name = p.name
    if name in SKIP_FILENAMES or is_secret_file(name) or ".min." in name:
        return False
    if language_of(path) is None:
        return False
    if p.suffix.lower() == ".json" and size > settings.max_json_bytes:
        return False  # result dumps, fixtures, datasets: noise for code questions
    return 0 < size <= settings.max_file_bytes


def is_probably_text(raw: bytes) -> bool:
    """Binary files almost always contain NUL bytes near the start."""
    return b"\x00" not in raw[:8000]


def looks_minified(text: str) -> bool:
    """Generated/minified files are one giant line: useless for search."""
    lines = text.splitlines()
    return len(text) > 2000 and bool(lines) and len(text) / len(lines) > 300

"""Cut files into chunks. Every chunk carries its own path, symbol and line range,
so later we can cite "path:start-end" exactly.

Python files are split with the `ast` module (one function/method = one chunk).
Everything else, and Python files that fail to parse, is split into line windows.
"""
import ast
import warnings
from typing import Iterator, Literal

from pydantic import BaseModel

from .config import settings
from .github import RepoFile

Kind = Literal["module", "class", "function", "method", "text"]


class Chunk(BaseModel):
    path: str
    language: str
    kind: Kind
    symbol: str      # "greet", "Bot", "Bot.run", "<module>", or "" for plain text
    start_line: int  # 1-based, inclusive
    end_line: int    # 1-based, inclusive
    text: str

    @property
    def citation(self) -> str:
        return f"{self.path}:{self.start_line}-{self.end_line}"


# ---------- small helpers ----------
def _split_lines(source: str) -> list[str]:
    # `ast` counts "\r\n", "\r" and "\n" as line breaks, so we do the same.
    # Otherwise our line numbers could drift away from Python's.
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _windows(start: int, end: int, size: int, overlap: int) -> Iterator[tuple[int, int]]:
    """Yield (start, end) line ranges of `size` lines, repeating `overlap` lines."""
    step = max(size - overlap, 1)
    s = start
    while True:
        e = min(s + size - 1, end)
        yield s, e
        if e >= end:
            return
        s += step


def _start_line(node: ast.AST) -> int:
    """First line of a def/class, including its @decorators."""
    decorators = getattr(node, "decorator_list", [])
    return min([node.lineno] + [d.lineno for d in decorators])


def _def_start(node: ast.AST, lines: list[str], last_end: int) -> int:
    """Start of a def/class, pulling in the comment lines written right above it.

    `last_end` is the last line already used by the previous chunk, so we never
    steal lines from it. A blank line stops the search: a comment separated from
    the function by an empty line is probably not about it.
    """
    start = _start_line(node)
    while start - 1 > last_end and lines[start - 2].lstrip().startswith("#"):
        start -= 1
    return start


def _make(
    file: RepoFile, lines: list[str], kind: Kind, symbol: str, start: int, end: int
) -> list[Chunk]:
    """Make one chunk for lines start..end, or several if it is too long."""
    if end - start + 1 <= settings.chunk_max_lines:
        ranges = [(start, end)]
    else:
        ranges = list(
            _windows(start, end, settings.chunk_window_lines, settings.chunk_overlap_lines)
        )
    chunks = []
    for s, e in ranges:
        text = "\n".join(lines[s - 1 : e])
        if text.strip():
            chunks.append(
                Chunk(
                    path=file.path,
                    language=file.language,
                    kind=kind,
                    symbol=symbol,
                    start_line=s,
                    end_line=e,
                    text=text,
                )
            )
    return chunks


# ---------- Python: use the AST ----------
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _walk(
    file: RepoFile,
    lines: list[str],
    body: list[ast.stmt],
    prefix: str,
    class_header: tuple[int, int] | None = None,
) -> list[Chunk]:
    """Turn a list of statements into chunks.

    - each function/method           -> its own chunk
    - each class                     -> its header chunk + a chunk per method
    - everything else (imports, constants, `if __name__ ...`) is grouped
      into "module" chunks (or "class" chunks inside a class)
    """
    in_class = class_header is not None
    group_kind: Kind = "class" if in_class else "module"
    group_symbol = prefix[:-1] if in_class else "<module>"

    chunks: list[Chunk] = []
    g_start: int | None = None
    g_end: int | None = None
    last_end = 0  # last line used by the previous statement
    if class_header:
        g_start, g_end = class_header
        last_end = g_end

    def flush() -> None:
        nonlocal g_start, g_end
        if g_start is not None and g_end is not None and g_end >= g_start:
            chunks.extend(_make(file, lines, group_kind, group_symbol, g_start, g_end))
        g_start = g_end = None

    for stmt in body:
        if isinstance(stmt, _FUNCTIONS):
            flush()
            kind: Kind = "method" if in_class else "function"
            start = _def_start(stmt, lines, last_end)
            chunks.extend(_make(file, lines, kind, prefix + stmt.name, start, stmt.end_lineno))
        elif isinstance(stmt, ast.ClassDef):
            flush()
            start = _def_start(stmt, lines, last_end)
            header_end = max(stmt.lineno, _start_line(stmt.body[0]) - 1)
            chunks.extend(
                _walk(
                    file,
                    lines,
                    stmt.body,
                    f"{prefix}{stmt.name}.",
                    class_header=(start, header_end),
                )
            )
        else:
            if g_start is None:
                g_start = stmt.lineno
            g_end = stmt.end_lineno
        last_end = stmt.end_lineno
    flush()
    return chunks


def _chunk_python(file: RepoFile) -> list[Chunk]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # old code often triggers harmless warnings
        tree = ast.parse(file.text)
    lines = _split_lines(file.text)
    return _walk(file, lines, tree.body, prefix="")


# ---------- Fallback: plain line windows ----------
def _chunk_lines(file: RepoFile) -> list[Chunk]:
    lines = _split_lines(file.text)
    if not lines:
        return []
    chunks = []
    for s, e in _windows(
        1, len(lines), settings.chunk_window_lines, settings.chunk_overlap_lines
    ):
        text = "\n".join(lines[s - 1 : e])
        if text.strip():
            chunks.append(
                Chunk(
                    path=file.path,
                    language=file.language,
                    kind="text",
                    symbol="",
                    start_line=s,
                    end_line=e,
                    text=text,
                )
            )
    return chunks


# ---------- Public API ----------
def chunk_file(file: RepoFile) -> list[Chunk]:
    if file.language == "python":
        try:
            return _chunk_python(file)
        except (SyntaxError, ValueError, RecursionError):
            pass  # not valid Python (or too deeply nested): use the fallback
    return _chunk_lines(file)


def chunk_repo(files: list[RepoFile]) -> list[Chunk]:
    return [chunk for file in files for chunk in chunk_file(file)]

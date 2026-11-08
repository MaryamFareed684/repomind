"""Evidence: the numbered pieces of the repository we show to the language model.

The model may only cite these numbers, so it cannot invent a file or a line range.
"""
import re
from collections import defaultdict
from posixpath import dirname, basename

from pydantic import BaseModel

from . import store
from .config import settings
from .search import Hit


class Evidence(BaseModel):
    n: int                 # the number the model cites, like [1]
    path: str
    kind: str              # function, method, class, module, text, or tree
    symbol: str
    start_line: int
    end_line: int
    text: str

    @property
    def label(self) -> str:
        if self.kind == "tree":
            return "file tree (every indexed file, grouped by folder)"
        name = f"{self.kind} {self.symbol}".strip()
        return f"{self.path} | lines {self.start_line}-{self.end_line} | {name}"


def _shorten(text: str) -> str:
    if len(text) <= settings.evidence_chunk_chars:
        return text
    return text[: settings.evidence_chunk_chars].rstrip() + "\n... (truncated)"


def from_hits(hits: list[Hit]) -> list[Evidence]:
    """Number the search results, stopping when the evidence gets too big."""
    evidence: list[Evidence] = []
    used = 0
    for hit in hits:
        chunk = hit.chunk
        text = _shorten(chunk.text)
        if evidence and used + len(text) > settings.evidence_max_chars:
            break
        evidence.append(
            Evidence(
                n=len(evidence) + 1,
                path=chunk.path,
                kind=chunk.kind,
                symbol=chunk.symbol,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                text=text,
            )
        )
        used += len(text)
    return evidence


# ---------- overview questions ("how is this project organized?") ----------
OVERVIEW = re.compile(
    r"\b(organi[sz]ed|structure|overview|architecture|layout"
    r"|what (does|is) (this|the) (project|repo|repository|app|code)"
    r"|(explain|summari[sz]e|describe) (this|the) (project|repo|repository))\b",
    re.IGNORECASE,
)


def is_overview(question: str) -> bool:
    return bool(OVERVIEW.search(question))


def format_tree(paths: list[str], max_lines: int) -> str:
    """Folders with their file names, one line per folder, so it stays short."""
    folders: dict[str, list[str]] = defaultdict(list)
    for path in sorted(paths):
        folders[dirname(path) or "."].append(basename(path))
    lines = []
    for folder, names in sorted(folders.items()):
        shown = ", ".join(names[:12]) + (", ..." if len(names) > 12 else "")
        lines.append(f"{folder}/ ({len(names)} files): {shown}")
    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + [f"... ({hidden} more folders not shown)"]
    return "\n".join(lines)


def overview_evidence(repo: str, paths: list[str]) -> list[Evidence]:
    """File tree + the start of the shallowest README."""
    evidence = [
        Evidence(
            n=1, path="(file tree)", kind="tree", symbol="", start_line=0, end_line=0,
            text=format_tree(paths, settings.tree_max_lines),
        )
    ]
    readmes = [c for c in store.load_chunks(repo) if c.path.lower().endswith("readme.md")]
    if readmes:
        top = min(c.path.count("/") for c in readmes)
        first = sorted(
            (c for c in readmes if c.path.count("/") == top), key=lambda c: c.start_line
        )[:2]
        for chunk in first:
            evidence.append(
                Evidence(
                    n=len(evidence) + 1, path=chunk.path, kind=chunk.kind, symbol=chunk.symbol,
                    start_line=chunk.start_line, end_line=chunk.end_line,
                    text=_shorten(chunk.text),
                )
            )
    return evidence

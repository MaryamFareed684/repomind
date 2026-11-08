"""Check the model's answer against the real indexed source.

We never trust the model's citations. We check that:
  1. every [n] points to a piece of evidence we really sent,
  2. every `path:start-end` it wrote exists in the repo (file there, lines inside the file),
  3. every file name it mentions exists in the repo.
An answer with no valid citation is marked "unverified" (unless it is NOT_FOUND).
"""
import re

from pydantic import BaseModel

from .chunker import Chunk
from .evidence import Evidence

NUMBER_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
LINE_CITE = re.compile(r"([\w./\\-]+\.\w{1,6}):(\d+)(?:\s*[-–]\s*(\d+))?")
FILE_WORD = re.compile(r"[\w./-]+\.\w{1,5}\b")
NOT_FOUND = re.compile(r"^\s*NOT[_ ]FOUND\b[:\s-]*", re.IGNORECASE)


class Citation(BaseModel):
    n: int
    path: str
    kind: str
    symbol: str
    start_line: int
    end_line: int


class Verified(BaseModel):
    status: str                 # answered, not_found, or unverified
    answer: str
    citations: list[Citation]
    problems: list[str]


FANCY_CITE = re.compile(r"[【［\[]\s*(\d+(?:\s*[,，]\s*\d+)*)\s*[】］\]]")


def normalize_brackets(answer: str) -> str:
    """Some models write citations as 【1】 or ［1］. Turn them into plain [1]."""
    return FANCY_CITE.sub(lambda m: "[" + m.group(1).replace("，", ",") + "]", answer)


def cited_numbers(answer: str) -> list[int]:
    seen: list[int] = []
    for match in NUMBER_CITE.finditer(answer):
        for part in match.group(1).split(","):
            n = int(part)
            if n not in seen:
                seen.append(n)
    return seen


def is_not_found(answer: str) -> bool:
    return bool(NOT_FOUND.match(answer))


def verify(answer: str, evidence: list[Evidence], chunks: list[Chunk]) -> Verified:
    answer = normalize_brackets(answer)
    if is_not_found(answer):
        message = NOT_FOUND.sub("", answer, count=1).strip() or "The repository does not say."
        return Verified(
            status="not_found",
            answer=f"I could not find this in the repository. {message}",
            citations=[],
            problems=[],
        )

    by_number = {item.n: item for item in evidence}
    problems: list[str] = []
    citations: list[Citation] = []

    for n in cited_numbers(answer):
        item = by_number.get(n)
        if item is None:
            problems.append(f"[{n}] is not one of the evidence pieces.")
        elif item.kind != "tree":
            citations.append(
                Citation(
                    n=n, path=item.path, kind=item.kind, symbol=item.symbol,
                    start_line=item.start_line, end_line=item.end_line,
                )
            )

    last_line: dict[str, int] = {}
    for chunk in chunks:
        last_line[chunk.path] = max(last_line.get(chunk.path, 0), chunk.end_line)

    for match in LINE_CITE.finditer(answer):
        path, start, end = match.group(1), int(match.group(2)), int(match.group(3) or match.group(2))
        path = path.replace("\\", "/")
        if path not in last_line:
            problems.append(f"{path} is not in the repository.")
        elif start < 1 or end < start or end > last_line[path]:
            problems.append(f"{path}:{start}-{end} is outside the file ({last_line[path]} lines).")

    extensions = {p.rsplit(".", 1)[-1].lower() for p in last_line if "." in p}
    for word in set(FILE_WORD.findall(answer)):
        word = word.strip("./")
        if "." not in word or word.rsplit(".", 1)[-1].lower() not in extensions:
            continue
        if not any(p == word or p.endswith("/" + word) for p in last_line):
            problems.append(f"{word} is not in the repository.")

    numbers = cited_numbers(answer)
    used_tree = any(item.kind == "tree" and item.n in numbers for item in evidence)
    if not citations and not used_tree:
        problems.append("The answer has no valid citation.")

    problems = list(dict.fromkeys(problems))
    status = "unverified" if problems else "answered"
    return Verified(status=status, answer=answer.strip(), citations=citations, problems=problems)

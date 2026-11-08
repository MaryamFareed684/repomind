"""Question in, grounded answer out: retrieve -> evidence -> prompt -> Groq -> verify."""
import httpx
from pydantic import BaseModel

from . import evidence as ev
from . import jobs, llm, search, store
from .config import settings
from .prompts import build_messages
from .verify import Citation, verify


class AskResponse(BaseModel):
    question: str
    status: str                       # answered, not_found, or unverified
    answer: str
    citations: list[Citation]
    problems: list[str]
    evidence: list[ev.Evidence]


NOTHING = "Nothing in the indexed code matches this question."


async def ask(repo: str, question: str, client: httpx.AsyncClient | None = None) -> AskResponse:
    chunks = store.load_chunks(repo)
    status = jobs.get_status(repo)
    paths = [f.path for f in status.files] if status and status.files else sorted({c.path for c in chunks})

    if ev.is_overview(question):
        evidence = ev.overview_evidence(repo, paths)
    else:
        evidence = ev.from_hits(search.search(repo, question, limit=settings.evidence_chunks))

    if not evidence:
        return AskResponse(
            question=question, status="not_found", answer=f"I could not find this in the repository. {NOTHING}",
            citations=[], problems=[], evidence=[],
        )

    answer = await llm.chat(build_messages(question, evidence), client=client)
    result = verify(answer, evidence, chunks)
    return AskResponse(
        question=question, status=result.status, answer=result.answer,
        citations=result.citations, problems=result.problems, evidence=evidence,
    )

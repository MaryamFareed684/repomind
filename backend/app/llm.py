"""Talk to Groq's chat API (it is OpenAI-compatible) with httpx.

Every failure becomes an LLMError with a message that is safe to show to the user:
it never contains the API key or internal details.
"""
import asyncio

import httpx

from .config import settings


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _retry_delay(resp: httpx.Response) -> float:
    """How long to wait before retrying: Groq's `retry-after` header, with a cap."""
    try:
        wait = float(resp.headers.get("retry-after", 2))
    except ValueError:
        wait = 2.0
    return min(max(wait, 0.0), settings.llm_max_wait_seconds)


def _error_for(resp: httpx.Response) -> LLMError:
    code = resp.status_code
    if code == 429:
        wait = int(_retry_delay(resp)) or 1
        return LLMError(f"The language model is busy (rate limit). Try again in about {wait} seconds.", 429)
    if code in (401, 403):
        return LLMError("The language model rejected our API key.", 502)
    if code == 413:
        return LLMError("The request was too large for the language model.", 502)
    return LLMError(f"The language model returned an error (status {code}).", 502)


def _content(resp: httpx.Response) -> str:
    try:
        choice = resp.json()["choices"][0]
        text = (choice["message"].get("content") or "").strip()
        finish = choice.get("finish_reason")
    except (KeyError, IndexError, ValueError, AttributeError):
        raise LLMError("The language model returned an unreadable answer.")
    if not text:
        raise LLMError("The language model returned an empty answer. Please try again.")
    if finish == "length":
        text += "\n\n(The answer was cut off because it reached the length limit.)"
    return text


async def chat(messages: list[dict], client: httpx.AsyncClient | None = None) -> str:
    if not settings.groq_api_key:
        raise LLMError("The language model is not configured (GROQ_API_KEY is missing).", 503)

    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}
    payload = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": 0.1,
        "max_completion_tokens": settings.answer_max_tokens,
    }
    send_effort = bool(settings.llm_reasoning_effort)

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
    try:
        retries = 0
        while True:
            body = dict(payload)
            if send_effort:
                body["reasoning_effort"] = settings.llm_reasoning_effort
            try:
                resp = await client.post(settings.groq_url, json=body, headers=headers)
            except httpx.TimeoutException:
                raise LLMError("The language model took too long to answer.", 504)
            except httpx.HTTPError:
                raise LLMError("Could not reach the language model.", 502)

            if resp.status_code == 200:
                return _content(resp)
            # If the API does not know the reasoning setting, try again without it.
            if resp.status_code == 400 and send_effort and "reasoning" in resp.text.lower():
                send_effort = False
                continue
            if resp.status_code in (429, 500, 502, 503) and retries < settings.llm_max_retries:
                retries += 1
                await asyncio.sleep(_retry_delay(resp))
                continue
            raise _error_for(resp)
    finally:
        if own_client:
            await client.aclose()

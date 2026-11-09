"""Turn text into vectors with fastembed (ONNX runtime: no PyTorch, small memory)."""
from functools import lru_cache

from fastembed import TextEmbedding

from .chunker import Chunk
from .config import settings


@lru_cache(maxsize=1)
def _model(name: str) -> TextEmbedding:
    return TextEmbedding(model_name=name)  # downloads the model the first time


def embedding_text(chunk: Chunk) -> str:
    """The text we embed: a label (path | symbol) on top of the chunk's code.

    The label tells the model which file and function a piece belongs to, even
    when a long function was split and the piece has no `def` line.
    """
    label = f"# {chunk.path}" + (f" | {chunk.symbol}" if chunk.symbol else "")
    return f"{label}\n{chunk.text}"


def embed_chunks(chunks: list[Chunk]) -> list[list[float]]:
    texts = [embedding_text(c) for c in chunks]
    model = _model(settings.embedding_model)
    vectors = model.passage_embed(texts, batch_size=settings.embed_batch_size)
    return [v.tolist() for v in vectors]


def embed_query(question: str) -> list[float]:
    model = _model(settings.embedding_model)
    return next(iter(model.query_embed(question))).tolist()

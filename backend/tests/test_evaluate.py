import pytest

from app.chunker import Chunk
from app.evaluate import first_rank, ranked_files, summarize
from app.search import Hit


def hit(path):
    chunk = Chunk(path=path, language="python", kind="function", symbol="f",
                  start_line=1, end_line=2, text="x")
    return Hit(chunk=chunk, score=1.0)


def test_ranked_files_lists_each_file_once_in_order():
    hits = [hit("a.py"), hit("b.py"), hit("a.py"), hit("c.py")]
    assert ranked_files(hits) == ["a.py", "b.py", "c.py"]


def test_first_rank():
    assert first_rank(["a.py", "b.py", "c.py"], ["b.py"]) == 2
    assert first_rank(["a.py", "b.py"], ["x.py", "a.py"]) == 1
    assert first_rank(["a.py"], ["z.py"]) is None
    assert first_rank([], ["z.py"]) is None


def test_summarize():
    # ranks: found 1st, found 3rd, found 6th, not found
    result = summarize([1, 3, 6, None])
    assert result["hit@1"] == 0.25
    assert result["hit@3"] == 0.5
    assert result["hit@5"] == 0.5
    assert result["mrr"] == pytest.approx((1 + 1 / 3 + 1 / 6) / 4, abs=0.001)


def test_summarize_empty_does_not_crash():
    assert summarize([])["hit@1"] == 0.0

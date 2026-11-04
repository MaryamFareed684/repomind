from app.chunker import Chunk, chunk_file, chunk_repo
from app.github import RepoFile

SAMPLE = '''"""Demo module."""
import os

LIMIT = 10

@decorator
def greet(name):
    return "hi " + name

class Bot:
    """A bot."""
    kind = "bot"

    def run(self):
        def inner():
            pass
        return inner

    async def stop(self):
        pass

if __name__ == "__main__":
    greet("x")
'''


def make_file(text: str, path: str = "app.py", language: str = "python") -> RepoFile:
    return RepoFile(path=path, language=language, size=len(text), text=text)


def summary(chunks: list[Chunk]):
    return [(c.kind, c.symbol, c.start_line, c.end_line) for c in chunks]


def test_python_file_is_split_by_structure():
    chunks = chunk_file(make_file(SAMPLE))
    assert summary(chunks) == [
        ("module", "<module>", 1, 4),     # docstring, import, LIMIT
        ("function", "greet", 6, 8),      # includes the @decorator line
        ("class", "Bot", 10, 12),         # header, docstring, class attribute
        ("method", "Bot.run", 14, 17),    # inner() stays inside its parent
        ("method", "Bot.stop", 19, 20),   # async def works too
        ("module", "<module>", 22, 23),   # code after the class
    ]


def test_chunk_text_matches_the_real_lines():
    file = make_file(SAMPLE)
    lines = SAMPLE.split("\n")
    for c in chunk_file(file):
        assert c.text == "\n".join(lines[c.start_line - 1 : c.end_line])
    greet = chunk_file(file)[1]
    assert greet.text.startswith("@decorator\ndef greet")
    assert greet.citation == "app.py:6-8"


def test_windows_line_endings_give_same_line_numbers():
    unix = summary(chunk_file(make_file(SAMPLE)))
    windows = summary(chunk_file(make_file(SAMPLE.replace("\n", "\r\n"))))
    assert unix == windows


def test_syntax_error_falls_back_to_line_windows():
    chunks = chunk_file(make_file("def broken(:\n    pass\n"))
    assert len(chunks) == 1
    assert chunks[0].kind == "text"
    assert (chunks[0].start_line, chunks[0].end_line) == (1, 2)


def test_long_function_is_split_but_keeps_its_name():
    body = "\n".join(f"    x{i} = {i}" for i in range(199))
    source = "def big():\n" + body + "\n"          # 200 lines
    chunks = chunk_file(make_file(source))
    assert len(chunks) > 1
    assert all(c.symbol == "big" and c.kind == "function" for c in chunks)
    assert chunks[0].start_line == 1
    assert chunks[-1].end_line == 200
    for prev, nxt in zip(chunks, chunks[1:]):
        assert prev.end_line - nxt.start_line + 1 == 8   # 8 lines of overlap


def test_non_python_file_uses_overlapping_windows():
    text = "\n".join(f"line {i}" for i in range(1, 131))   # 130 lines
    chunks = chunk_file(make_file(text, path="README.md", language="markdown"))
    assert [(c.start_line, c.end_line) for c in chunks] == [(1, 60), (53, 112), (105, 130)]
    assert all(c.kind == "text" for c in chunks)


def test_empty_and_blank_files_give_no_chunks():
    assert chunk_file(make_file("")) == []
    assert chunk_file(make_file("\n\n\n")) == []
    assert chunk_file(make_file("   \n", path="a.md", language="markdown")) == []


def test_class_without_methods_is_one_chunk():
    chunks = chunk_file(make_file("class Config:\n    a = 1\n    b = 2\n"))
    assert summary(chunks) == [("class", "Config", 1, 3)]


def test_one_line_class_and_nested_class():
    source = "class A: pass\n\nclass Outer:\n    class Inner:\n        def f(self):\n            pass\n"
    chunks = chunk_file(make_file(source))
    assert summary(chunks) == [
        ("class", "A", 1, 1),
        ("class", "Outer", 3, 3),
        ("class", "Outer.Inner", 4, 4),
        ("method", "Outer.Inner.f", 5, 6),
    ]


def test_chunk_repo_combines_files():
    files = [make_file(SAMPLE, path="a.py"), make_file("hello", path="b.md", language="markdown")]
    chunks = chunk_repo(files)
    assert {c.path for c in chunks} == {"a.py", "b.md"}


def test_comment_lines_right_above_a_function_are_included():
    source = "import os\n\n# Greets a user.\n# Second line.\ndef greet():\n    pass\n"
    chunks = chunk_file(make_file(source))
    assert summary(chunks) == [
        ("module", "<module>", 1, 1),
        ("function", "greet", 3, 6),
    ]


def test_comment_separated_by_blank_line_is_not_included():
    source = "# just a note\n\ndef f():\n    pass\n"
    chunks = chunk_file(make_file(source))
    assert summary(chunks) == [("function", "f", 3, 4)]


def test_comments_between_methods_go_to_the_next_method():
    source = "class A:\n    def a(self):\n        pass\n    # about b\n    def b(self):\n        pass\n"
    chunks = chunk_file(make_file(source))
    assert summary(chunks) == [
        ("class", "A", 1, 1),
        ("method", "A.a", 2, 3),
        ("method", "A.b", 4, 6),
    ]

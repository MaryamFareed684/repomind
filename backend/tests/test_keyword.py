from app.chunker import Chunk
from app.keyword import KeywordIndex, tokenize


def chunk(path, symbol, text, start=1):
    return Chunk(
        path=path, language="python", kind="function", symbol=symbol,
        start_line=start, end_line=start + text.count("\n"), text=text,
    )


def test_snake_case_identifier_gives_whole_name_and_parts():
    assert tokenize("make_pass_decorator") == [
        "make_pass_decorator", "make", "pass", "decorator",
    ]


def test_camel_case_and_acronyms_are_split():
    assert tokenize("getUser") == ["getuser", "get", "user"]
    assert tokenize("HTTPServerError") == ["httpservererror", "http", "server", "error"]


def test_plain_words_and_digits_and_stopwords():
    assert tokenize("Where is the login?") == ["login"]
    assert tokenize("utf8 decode") == ["utf8", "utf", "8", "decode"]


def test_exact_function_name_is_found_first():
    chunks = [
        chunk("a.py", "pass_obj", "def pass_obj(f):\n    return f"),
        chunk("b.py", "make_pass_decorator", "def make_pass_decorator(t):\n    return t"),
        chunk("c.py", "other", "def other():\n    pass"),
    ]
    hits = KeywordIndex(chunks).search("what does make_pass_decorator do?", 3)
    assert hits[0].symbol == "make_pass_decorator"


def test_parts_of_a_name_match_a_description():
    chunks = [
        chunk("a.py", "verify_password", "def verify_password(user):\n    ...", 1),
        chunk("b.py", "render_page", "def render_page():\n    ...", 1),
    ]
    hits = KeywordIndex(chunks).search("where do we verify the password", 5)
    assert [h.symbol for h in hits] == ["verify_password"]


def test_no_match_and_empty_index_give_nothing():
    index = KeywordIndex([chunk("a.py", "f", "def f():\n    pass")])
    assert index.search("zebra giraffe", 5) == []
    assert index.search("the of and", 5) == []   # only stopwords
    assert KeywordIndex([]).search("anything", 5) == []

import pytest

from app import search, store
from app.chunker import chunk_repo
from app.github import RepoFile

AUTH = '''def verify_password(user, password):
    """Check that the password matches the stored hash."""
    return hash(password) == user.hash
'''
PAGES = '''def render_page(name):
    """Build the html page for a name."""
    return "<html>" + name + "</html>"
'''
DB = '''def connect_database(url):
    """Open a connection to the database."""
    return url
'''


def make_chunks(prefix=""):
    files = [
        RepoFile(path=f"{prefix}auth.py", language="python", size=1, text=AUTH),
        RepoFile(path=f"{prefix}pages.py", language="python", size=1, text=PAGES),
        RepoFile(path=f"{prefix}db.py", language="python", size=1, text=DB),
    ]
    return chunk_repo(files)


def test_rrf_matches_the_table_from_the_lesson():
    scores = search.rrf([["A", "B"], ["C", "x", "y", "z", "A"]], k=60)
    assert scores["A"] == pytest.approx(1 / 61 + 1 / 65)   # 0.0318
    assert scores["B"] == pytest.approx(1 / 62)
    assert scores["C"] == pytest.approx(1 / 61)
    assert scores["A"] > scores["C"] > scores["B"]


def test_index_then_search_each_mode():
    store.index_chunks("o/r", make_chunks())
    for mode in ("hybrid", "vector", "keyword"):
        hits = search.search("o/r", "verify the password", limit=3, mode=mode)
        assert hits[0].chunk.path == "auth.py", mode


def test_hybrid_hit_shows_both_ranks():
    store.index_chunks("o/r", make_chunks())
    hit = search.search("o/r", "verify_password", limit=3)[0]
    assert hit.chunk.symbol == "verify_password"
    assert hit.vector_rank is not None and hit.keyword_rank is not None


def test_search_only_sees_its_own_repo():
    store.index_chunks("o/one", make_chunks("one/"))
    store.index_chunks("o/two", make_chunks("two/"))
    paths = {h.chunk.path for h in search.search("o/one", "database", limit=20)}
    assert paths and all(p.startswith("one/") for p in paths)
    assert search.search("o/missing", "database") == []


def test_reindexing_replaces_instead_of_duplicating():
    store.index_chunks("o/r", make_chunks())
    first = len(store.load_chunks("o/r"))
    store.index_chunks("o/r", make_chunks())
    assert len(store.load_chunks("o/r")) == first == 3


def test_reindexing_removes_chunks_that_no_longer_exist():
    store.index_chunks("o/r", make_chunks())
    store.index_chunks("o/r", make_chunks()[:1])
    assert [c.path for c in store.load_chunks("o/r")] == ["auth.py"]


def test_point_ids_are_stable_and_unique():
    chunks = make_chunks()
    ids = [store.point_id("o/r", c) for c in chunks]
    assert len(set(ids)) == 3
    assert ids == [store.point_id("o/r", c) for c in chunks]
    assert store.point_id("o/r", chunks[0]) != store.point_id("o/other", chunks[0])


def test_keyword_index_is_rebuilt_from_qdrant_after_restart():
    store.index_chunks("o/r", make_chunks())
    search._keyword_cache.clear()   # pretend the server restarted
    hits = search.search("o/r", "connect_database", mode="keyword")
    assert hits[0].chunk.path == "db.py"


def test_progress_is_reported():
    seen = []
    store.index_chunks("o/r", make_chunks(), on_progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (3, 3)

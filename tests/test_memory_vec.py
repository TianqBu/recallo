"""Semantic recall via sqlite-vec, driven by a deterministic stub embedder."""

from pathlib import Path

import pytest

from recallo.embed import StubEmbedder
from recallo.memory import Fact, MemoryLane


@pytest.fixture
def mem(tmp_path: Path) -> MemoryLane:
    m = MemoryLane(db_path=tmp_path / "vec.db", embedder=StubEmbedder())
    yield m
    m.close()


def test_vec_extension_loads(mem: MemoryLane) -> None:
    assert mem.vec_available


def test_insert_fact_writes_to_vec_table(mem: MemoryLane) -> None:
    ep = mem.start_episode("seed")
    fact_id = mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="abc"))
    cnt = mem.conn.execute("SELECT COUNT(*) FROM fact_vec WHERE rowid=?", (fact_id,)).fetchone()[0]
    assert cnt == 1


def test_semantic_search_returns_self_first(mem: MemoryLane) -> None:
    ep = mem.start_episode("rag")
    contents = [
        "Self-RAG: retrieval augmented generation with self-reflection",
        "Attention is all you need: transformers from scratch",
        "Atlas: a pretrained retriever for open-domain QA",
        "Diffusion models for image synthesis",
    ]
    for c in contents:
        mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content=c))

    # Querying with the exact same string should put that fact at distance 0
    target = contents[0]
    hits = mem.search_facts_semantic(target, limit=4)
    assert len(hits) == 4
    assert hits[0]["content"] == target
    assert hits[0]["distance"] == pytest.approx(0.0, abs=1e-6)
    # Distances should be non-decreasing
    distances = [r["distance"] for r in hits]
    assert distances == sorted(distances)


def test_semantic_search_empty_without_embedder(tmp_path: Path) -> None:
    m = MemoryLane(db_path=tmp_path / "noemb.db")  # no embedder
    try:
        ep = m.start_episode("x")
        m.insert_fact(Fact(episode_id=ep.id, kind="paper", content="abc"))
        assert m.search_facts_semantic("anything") == []
        # Fact still landed in the regular table
        cnt = m.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        assert cnt == 1
    finally:
        m.close()


def test_fts_keyword_recall_still_works_alongside_vec(mem: MemoryLane) -> None:
    ep = mem.start_episode("k")
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="Self-RAG retrieval"))
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="Atlas pretrained retriever"))
    hits = mem.search_facts("retrieval")
    assert any("Self-RAG" in r["content"] for r in hits)


def test_dimension_mismatch_raises(tmp_path: Path) -> None:
    bad = StubEmbedder(dim=64)
    m = MemoryLane(db_path=tmp_path / "bad.db", embedder=bad)
    try:
        ep = m.start_episode("dim")
        with pytest.raises(ValueError, match="dim="):
            m.insert_fact(Fact(episode_id=ep.id, kind="paper", content="x"))
    finally:
        m.close()

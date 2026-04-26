from pathlib import Path

import pytest

from recallo.memory import Episode, Fact, MemoryLane, Trace


@pytest.fixture
def mem(tmp_path: Path) -> MemoryLane:
    m = MemoryLane(db_path=tmp_path / "m.db")
    yield m
    m.close()


def test_init_creates_db_file(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    assert not db.exists()
    m = MemoryLane(db_path=db)
    try:
        assert db.exists()
    finally:
        m.close()


def test_episode_lifecycle(mem: MemoryLane) -> None:
    ep = mem.start_episode("read self-rag paper")
    assert isinstance(ep, Episode)
    assert ep.status == "running"
    mem.finish_episode(ep.id, status="ok", summary="finished")
    rows = mem.list_episodes()
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
    assert rows[0]["summary"] == "finished"
    assert rows[0]["ended_at"] is not None


def test_trace_unique_per_episode_seq(mem: MemoryLane) -> None:
    ep = mem.start_episode("t")
    mem.insert_trace(Trace(episode_id=ep.id, seq=0, action_type="navigate", ts=1))
    with pytest.raises(Exception):
        mem.insert_trace(Trace(episode_id=ep.id, seq=0, action_type="click", ts=2))


def test_trace_text_excerpt_and_thinking_persisted(mem: MemoryLane) -> None:
    ep = mem.start_episode("t")
    mem.insert_trace(
        Trace(
            episode_id=ep.id,
            seq=0,
            action_type="navigate",
            ts=1,
            url="https://arxiv.org/abs/2310.11511",
            selector=None,
            text_excerpt="Self-RAG title",
            thinking="should open the paper",
        )
    )
    row = mem.conn.execute(
        "SELECT action_type, url, text_excerpt, thinking FROM traces WHERE episode_id=?",
        (ep.id,),
    ).fetchone()
    assert row["action_type"] == "navigate"
    assert row["text_excerpt"] == "Self-RAG title"
    assert row["thinking"] == "should open the paper"


def test_facts_fts_search_round_trip(mem: MemoryLane) -> None:
    ep = mem.start_episode("rag survey")
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="Self-RAG retrieval-augmented generation"))
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="Atlas pretrained retriever"))
    hits = mem.search_facts("retrieval")
    assert len(hits) >= 1
    assert any("Self-RAG" in r["content"] for r in hits)
    none_hits = mem.search_facts("zzznotpresent")
    assert none_hits == []


def test_cascade_delete_removes_traces_and_facts(mem: MemoryLane) -> None:
    ep = mem.start_episode("t")
    mem.insert_trace(Trace(episode_id=ep.id, seq=0, action_type="navigate", ts=1))
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="abc"))
    mem.conn.execute("DELETE FROM episodes WHERE id=?", (ep.id,))
    assert mem.conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 0
    assert mem.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == 0

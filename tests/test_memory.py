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


def test_search_facts_handles_fts5_operator_chars(mem: MemoryLane) -> None:
    """Inputs with `-`, `:`, `"` used to crash with `fts5: syntax error`."""
    ep = mem.start_episode("operators")
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="Self-RAG paper"))
    # All of these would have raised before the _fts5_escape fix.
    assert mem.search_facts("self-rag") != []
    assert mem.search_facts('"self rag"') != []
    assert mem.search_facts("foo:bar") == []  # unrelated, but must not raise


def test_resolve_episode_id_escapes_like_wildcards(mem: MemoryLane) -> None:
    """A bare `%` would otherwise match every episode."""
    mem.start_episode("alpha")
    mem.start_episode("beta")
    # `%` should NOT be a wildcard now that we escape it.
    assert mem.resolve_episode_id("%") == []
    # A real prefix still resolves
    real = mem.list_episodes()[0]["id"]
    assert mem.resolve_episode_id(real[:8]) == [real]


def test_insert_facts_batch_round_trip(mem: MemoryLane) -> None:
    ep = mem.start_episode("batch")
    facts = [
        Fact(episode_id=ep.id, kind="paper", content=f"fact #{i}")
        for i in range(5)
    ]
    ids = mem.insert_facts_batch(facts)
    assert len(ids) == 5
    rows = list(
        mem.conn.execute(
            "SELECT content FROM facts WHERE episode_id=? ORDER BY id",
            (ep.id,),
        )
    )
    assert [r["content"] for r in rows] == [f"fact #{i}" for i in range(5)]


def test_insert_facts_batch_empty_is_noop(mem: MemoryLane) -> None:
    assert mem.insert_facts_batch([]) == []


def test_user_version_set_on_init(mem: MemoryLane) -> None:
    """Schema versioning scaffolding — fresh DBs should be tagged."""
    from recallo.memory import _SCHEMA_VERSION
    cur = mem.conn.execute("PRAGMA user_version")
    assert cur.fetchone()[0] == _SCHEMA_VERSION


def test_init_rejects_future_schema_version(tmp_path: Path) -> None:
    """A db tagged with a higher version must refuse to open."""
    import sqlite3 as stdlib_sqlite3
    db = tmp_path / "future.db"
    conn = stdlib_sqlite3.connect(db, isolation_level=None)
    conn.execute("PRAGMA user_version = 9999")
    conn.close()

    with pytest.raises(RuntimeError, match="newer than this build"):
        MemoryLane(db_path=db)

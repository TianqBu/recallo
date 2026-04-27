"""Tests for the replay-related MemoryLane methods + the CLI subcommand."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from recallo.cli import main as cli
from recallo.memory import Fact, MemoryLane, Trace


@pytest.fixture
def mem(tmp_path: Path, monkeypatch) -> MemoryLane:
    db = tmp_path / "replay.db"
    # Make `MemoryLane()` (no args) point at our temp db so the CLI uses it
    monkeypatch.setattr(
        "recallo.memory.default_db_path", lambda: db, raising=True
    )
    m = MemoryLane(db_path=db)
    yield m
    m.close()


def test_get_episode_and_resolve_prefix(mem: MemoryLane) -> None:
    ep = mem.start_episode("hello")
    got = mem.get_episode(ep.id)
    assert got is not None
    assert got["intent"] == "hello"
    # full id resolves
    assert mem.resolve_episode_id(ep.id) == [ep.id]
    # 8-char prefix resolves
    assert mem.resolve_episode_id(ep.id[:8]) == [ep.id]
    # bogus prefix is empty
    assert mem.resolve_episode_id("zzzz") == []
    # missing exact id returns None
    assert mem.get_episode("00000000-0000-0000-0000-000000000000") is None


def test_list_traces_and_facts_in_order(mem: MemoryLane) -> None:
    ep = mem.start_episode("ordered")
    mem.insert_trace(Trace(episode_id=ep.id, seq=1, action_type="click", ts=1))
    mem.insert_trace(Trace(episode_id=ep.id, seq=0, action_type="navigate", ts=0))
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="A"))
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="B"))

    traces = mem.list_traces(ep.id)
    assert [t["seq"] for t in traces] == [0, 1]
    assert traces[0]["action_type"] == "navigate"

    facts = mem.list_facts(ep.id)
    assert [f["content"] for f in facts] == ["A", "B"]


def test_cli_replay_no_args_lists_episodes(mem: MemoryLane) -> None:
    mem.start_episode("first task")
    mem.start_episode("second task")
    runner = CliRunner()
    result = runner.invoke(cli, ["replay"])
    assert result.exit_code == 0, result.output
    assert "first task" in result.output
    assert "second task" in result.output
    assert "id" in result.output and "status" in result.output


def test_cli_replay_with_prefix_shows_detail(mem: MemoryLane) -> None:
    ep = mem.start_episode("read self-rag")
    mem.insert_trace(
        Trace(
            episode_id=ep.id,
            seq=0,
            action_type="navigate",
            ts=1,
            url="https://arxiv.org/abs/2310.11511",
            text_excerpt="Self-RAG",
            thinking="open paper",
        )
    )
    mem.insert_fact(Fact(episode_id=ep.id, kind="extract",
                         content="Self-RAG uses self-reflection tokens"))
    mem.finish_episode(ep.id, status="ok", summary="done")

    runner = CliRunner()
    result = runner.invoke(cli, ["replay", ep.id[:8]])
    assert result.exit_code == 0, result.output
    assert "Episode" in result.output
    assert ep.id in result.output
    assert "navigate" in result.output
    assert "Self-RAG" in result.output
    assert "open paper" in result.output
    assert "self-reflection" in result.output


def test_cli_replay_unknown_prefix_errors(mem: MemoryLane) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["replay", "zzzznonexistent"])
    assert result.exit_code != 0
    assert "no episode matches" in (result.output + result.stderr)


def test_cli_replay_ambiguous_prefix_errors(tmp_path: Path, monkeypatch) -> None:
    """Force a collision by overriding uuid generation."""
    db = tmp_path / "amb.db"
    monkeypatch.setattr("recallo.memory.default_db_path", lambda: db, raising=True)
    m = MemoryLane(db_path=db)
    try:
        # Two ids with the same first character — easy to engineer
        m.conn.execute(
            "INSERT INTO episodes(id, intent, started_at, status) VALUES (?, ?, ?, ?)",
            ("aaaa1111-1111-1111-1111-111111111111", "x", 1, "ok"),
        )
        m.conn.execute(
            "INSERT INTO episodes(id, intent, started_at, status) VALUES (?, ?, ?, ?)",
            ("aaaa2222-2222-2222-2222-222222222222", "y", 2, "ok"),
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["replay", "aaaa"])
        assert result.exit_code != 0
        assert "ambiguous" in (result.output + result.stderr)
    finally:
        m.close()

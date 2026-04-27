"""CLI-level tests covering recall mode behaviour and small UX edges."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from recallo.cli import main as cli
from recallo.memory import Fact, MemoryLane


@pytest.fixture
def mem(tmp_path: Path, monkeypatch) -> MemoryLane:
    db = tmp_path / "cli.db"
    monkeypatch.setattr("recallo.memory.default_db_path", lambda: db, raising=True)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    m = MemoryLane(db_path=db)
    yield m
    m.close()


def test_recall_semantic_mode_errors_without_embedder(mem: MemoryLane) -> None:
    """`--mode semantic` must NOT silently fall back to keyword."""
    ep = mem.start_episode("seed")
    mem.insert_fact(Fact(episode_id=ep.id, kind="paper", content="self-rag"))

    runner = CliRunner()
    result = runner.invoke(cli, ["recall", "self-rag", "--mode", "semantic"])
    assert result.exit_code == 1
    assert "requires OPENAI_API_KEY" in (result.output + result.stderr)


def test_recall_keyword_mode_works_without_embedder(mem: MemoryLane) -> None:
    ep = mem.start_episode("seed")
    mem.insert_fact(
        Fact(episode_id=ep.id, kind="paper", content="Self-RAG retrieval method")
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["recall", "retrieval", "--mode", "keyword"])
    assert result.exit_code == 0
    assert "Self-RAG" in result.output
    assert "mode=keyword" in result.output


def test_recall_no_matches_exits_zero(mem: MemoryLane) -> None:
    """An empty result set should be a clean exit, not an error."""
    runner = CliRunner()
    result = runner.invoke(cli, ["recall", "zzznotpresent", "--mode", "keyword"])
    assert result.exit_code == 0
    assert "no matches" in result.output


def test_format_ts_handles_zero(monkeypatch) -> None:
    """Epoch 0 is a valid timestamp, not 'missing'."""
    from recallo.cli import _format_ts
    out = _format_ts(0)
    assert out != "-"
    assert out.startswith("1970-01-01")
    assert _format_ts(None) == "-"

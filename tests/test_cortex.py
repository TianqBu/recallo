"""Mock-driven tests for cortex._on_step.

We don't import browser-use here; we hand-build dummies that match the field
shapes verified in sources/browser-use/browser_use/{browser,agent}/views.py.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from recallo.cortex import CortexConfig, run_episode
from recallo.memory import MemoryLane


@dataclass
class _DummyState:
    url: str
    title: str


class _DummyAction:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(self, exclude_unset: bool = False) -> dict[str, Any]:
        return self._payload


@dataclass
class _DummyOutput:
    action: list[_DummyAction]
    thinking: str | None = None


@pytest.fixture
def mem(tmp_path: Path) -> MemoryLane:
    m = MemoryLane(db_path=tmp_path / "m.db")
    yield m
    m.close()


@pytest.mark.asyncio
async def test_run_episode_records_trace_for_each_step(mem: MemoryLane, monkeypatch) -> None:
    """Patch the Agent so we can drive _on_step manually."""

    captured_callback = {}

    class _FakeAgent:
        def __init__(self, *, task: str, llm: Any, register_new_step_callback: Any,
                     max_failures: int = 5, **_kw) -> None:
            captured_callback["fn"] = register_new_step_callback

        async def run(self, max_steps: int = 50) -> None:
            cb = captured_callback["fn"]
            await cb(
                _DummyState(url="https://arxiv.org/abs/2310.11511", title="Self-RAG"),
                _DummyOutput(action=[_DummyAction({"navigate": {"url": "x"}})], thinking="open paper"),
                0,
            )
            await cb(
                _DummyState(url="https://arxiv.org/abs/2310.11511", title="Self-RAG"),
                _DummyOutput(action=[_DummyAction({"extract_content": {"goal": "summary"}})]),
                1,
            )

    import recallo.cortex as cortex_mod

    def _fake_build_llm(_cfg):
        return object()

    monkeypatch.setattr(cortex_mod, "_build_llm", _fake_build_llm)

    # Inject a stub `browser_use` module so the deferred import inside
    # run_episode finds our fake Agent without pip-installing browser-use.
    import sys, types
    fake_module = types.ModuleType("browser_use")
    fake_module.Agent = _FakeAgent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "browser_use", fake_module)

    cfg = CortexConfig(llm_provider="openai", max_steps=2)
    ep_id = await run_episode("read Self-RAG", mem, cfg)

    rows = list(
        mem.conn.execute(
            "SELECT seq, action_type, url, text_excerpt, thinking FROM traces WHERE episode_id=? ORDER BY seq",
            (ep_id,),
        )
    )
    assert len(rows) == 2
    assert rows[0]["action_type"] == "navigate"
    assert rows[0]["url"] == "https://arxiv.org/abs/2310.11511"
    assert rows[0]["text_excerpt"] == "Self-RAG"
    assert rows[0]["thinking"] == "open paper"
    assert rows[1]["action_type"] == "extract_content"
    assert rows[1]["thinking"] is None

    ep_rows = mem.list_episodes()
    assert ep_rows[0]["status"] == "ok"


@pytest.mark.asyncio
async def test_run_episode_redacts_blocked_urls(mem: MemoryLane, monkeypatch) -> None:
    captured_callback = {}

    class _FakeAgent:
        def __init__(self, *, register_new_step_callback: Any, **_kw) -> None:
            captured_callback["fn"] = register_new_step_callback

        async def run(self, max_steps: int = 50) -> None:
            await captured_callback["fn"](
                _DummyState(url="https://mail.google.com/u/0/", title="Inbox"),
                _DummyOutput(action=[_DummyAction({"navigate": {"url": "x"}})]),
                0,
            )

    import recallo.cortex as cortex_mod
    monkeypatch.setattr(cortex_mod, "_build_llm", lambda _cfg: object())

    import sys, types
    fake_module = types.ModuleType("browser_use")
    fake_module.Agent = _FakeAgent  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "browser_use", fake_module)

    ep_id = await run_episode("check inbox", mem, CortexConfig())
    row = mem.conn.execute(
        "SELECT action_type, url, text_excerpt FROM traces WHERE episode_id=?",
        (ep_id,),
    ).fetchone()
    assert row["action_type"] == "redacted"
    assert row["url"].startswith("[redacted:")
    assert row["text_excerpt"] is None

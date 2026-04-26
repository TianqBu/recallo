"""Browser Cortex — thin wrapper over browser-use that streams Web Trace records.

The audit (`SOURCES_AUDIT.md`) settled on `register_new_step_callback` as the
official per-step capture point in browser-use 0.12.6. We don't monkey-patch.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from .memory import MemoryLane, Trace
from .safety import is_blocked, redact

logger = logging.getLogger("recallo.cortex")


@dataclass
class CortexConfig:
    llm_provider: str = "openai"           # openai | anthropic | ollama
    llm_model: str | None = None           # default chosen by provider below
    headless: bool = False
    max_steps: int = 50
    max_failures: int = 3
    text_excerpt_chars: int = 1024


def _build_llm(cfg: CortexConfig):
    """Construct a browser-use ChatX adapter from config + env vars.

    Imports are deferred so `recallo --version` doesn't pull in 200MB of SDKs.
    """
    provider = cfg.llm_provider.lower()
    if provider == "openai":
        from browser_use import ChatOpenAI
        return ChatOpenAI(model=cfg.llm_model or "gpt-4o-mini")
    if provider == "anthropic":
        from browser_use import ChatAnthropic
        return ChatAnthropic(model=cfg.llm_model or "claude-3-5-sonnet-latest")
    if provider == "ollama":
        from browser_use import ChatOllama
        return ChatOllama(
            model=cfg.llm_model or "qwen2.5",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    raise ValueError(f"Unknown llm_provider: {cfg.llm_provider}")


async def run_episode(intent: str, memory: MemoryLane, cfg: CortexConfig) -> str:
    """Run one browser-use task, stream traces into memory, return episode id.

    Each step fires `_on_step` which writes a Trace row. The episode row is
    created up-front (status='running') and finalised at the end.
    """
    from browser_use import Agent  # deferred import

    episode = memory.start_episode(intent)
    seq = {"n": 0}

    def _excerpt(text: str | None) -> str | None:
        if text is None:
            return None
        return text[: cfg.text_excerpt_chars]

    async def _on_step(state: Any, model_output: Any, step_idx: int) -> None:
        """browser-use signature: (BrowserStateSummary, AgentOutput, int)."""
        try:
            url = getattr(state, "url", None)
            if url and is_blocked(url):
                # honour the blacklist — drop URL details, keep timing
                memory.insert_trace(
                    Trace(
                        episode_id=episode.id,
                        seq=seq["n"],
                        action_type="redacted",
                        ts=int(time.time()),
                        url=redact(url),
                    )
                )
                seq["n"] += 1
                return

            actions = getattr(model_output, "action", None) or []
            first = actions[0] if actions else None
            action_type = type(first).__name__ if first is not None else "step"
            thinking = getattr(model_output, "thinking", None)

            memory.insert_trace(
                Trace(
                    episode_id=episode.id,
                    seq=seq["n"],
                    action_type=action_type,
                    ts=int(time.time()),
                    url=url,
                    selector=None,
                    text_excerpt=_excerpt(getattr(state, "page_text", None)),
                    thinking=_excerpt(thinking),
                )
            )
            seq["n"] += 1
        except Exception:
            logger.exception("[recallo] failed to record trace; continuing")

    try:
        llm = _build_llm(cfg)
        agent = Agent(
            task=intent,
            llm=llm,
            register_new_step_callback=_on_step,
            max_failures=cfg.max_failures,
        )
        await agent.run(max_steps=cfg.max_steps)
        memory.finish_episode(episode.id, status="ok")
    except Exception as e:
        logger.exception("[recallo] episode failed")
        memory.finish_episode(episode.id, status="failed", summary=str(e)[:512])
        raise
    return episode.id

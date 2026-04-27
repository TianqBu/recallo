"""Browser Cortex — thin wrapper over browser-use that streams Web Trace records.

The audit (`SOURCES_AUDIT.md`) settled on `register_new_step_callback` as the
official per-step capture point in browser-use 0.12.6. We don't monkey-patch.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from .memory import Fact, MemoryLane, Trace
from .safety import is_blocked, redact, scrub_secrets, strip_sensitive_params

logger = logging.getLogger("recallo.cortex")


@dataclass
class CortexConfig:
    llm_provider: str = "openai"           # openai | anthropic | ollama
    llm_model: str | None = None           # default chosen by provider below
    headless: bool = False
    max_steps: int = 50
    max_failures: int = 3
    text_excerpt_chars: int = 1024


def _build_llm(cfg: CortexConfig) -> Any:
    """Construct a browser-use ChatX adapter from config + env vars.

    Imports are deferred so `recallo --version` doesn't pull in 200MB of SDKs.
    Returns ``Any`` because the three Chat* classes don't share a public base.
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

    Each step fires `_on_step` which writes a Trace row off the event loop;
    `_on_done` collects all extracted content and writes it as a single
    batched insert (one embedding round-trip for the whole episode).
    """
    from browser_use import Agent  # deferred import

    episode = memory.start_episode(intent)
    seq = 0
    pending_facts: list[Fact] = []

    def _excerpt(text: str | None) -> str | None:
        if text is None:
            return None
        return text[: cfg.text_excerpt_chars]

    async def _on_step(state: Any, model_output: Any, step_idx: int) -> None:
        """browser-use signature: (BrowserStateSummary, AgentOutput, int).

        BrowserStateSummary fields verified against
        sources/browser-use/browser_use/browser/views.py: url, title, dom_state,
        screenshot, page_info, ... — no `page_text` attribute exists.

        AgentOutput fields verified against
        sources/browser-use/browser_use/agent/views.py: thinking, action (list of
        ActionModel). ActionModel is a dynamic Pydantic model whose first dumped
        key is the action name (e.g. 'click_element', 'navigate', 'done').
        """
        nonlocal seq
        try:
            url = getattr(state, "url", None)
            title = getattr(state, "title", None)

            if url and is_blocked(url):
                trace = Trace(
                    episode_id=episode.id,
                    seq=seq,
                    action_type="redacted",
                    ts=int(time.time()),
                    url=redact(url),
                )
                await asyncio.to_thread(memory.insert_trace, trace)
                seq += 1
                return

            actions = getattr(model_output, "action", None) or []
            first = actions[0] if actions else None
            action_type = "step"
            if first is not None and hasattr(first, "model_dump"):
                dumped = first.model_dump(exclude_unset=True) or {}
                action_type = next(iter(dumped.keys()), "step")

            thinking = getattr(model_output, "thinking", None)
            stored_url = strip_sensitive_params(url) if url else url

            trace = Trace(
                episode_id=episode.id,
                seq=seq,
                action_type=action_type,
                ts=int(time.time()),
                url=stored_url,
                selector=None,
                text_excerpt=scrub_secrets(_excerpt(title)),
                thinking=scrub_secrets(_excerpt(thinking)),
            )
            await asyncio.to_thread(memory.insert_trace, trace)
            seq += 1
        except Exception:
            logger.exception("[recallo] failed to record trace; continuing")

    async def _on_done(history: Any) -> None:
        """browser-use signature: (AgentHistoryList,). Called once at end.

        Walks the AgentHistory items, collects ActionResult content, then
        batches the writes + embeddings into a single transaction.
        """
        if history is None:
            return
        items = getattr(history, "history", None) or []
        for h in items:
            url = getattr(getattr(h, "state", None), "url", None)
            for r in getattr(h, "result", None) or []:
                content = (
                    getattr(r, "long_term_memory", None)
                    or getattr(r, "extracted_content", None)
                    or ""
                )
                content = (content or "").strip()
                if not content:
                    continue
                if url and is_blocked(url):
                    continue
                content = scrub_secrets(content) or ""
                if not content:
                    continue
                if len(content) > 4096:
                    content = content[:4096]
                stored_url = strip_sensitive_params(url) if url else url
                pending_facts.append(
                    Fact(
                        episode_id=episode.id,
                        kind="extract",
                        content=content,
                        source_url=stored_url,
                    )
                )

        if pending_facts:
            try:
                await asyncio.to_thread(memory.insert_facts_batch, pending_facts)
            except Exception:
                logger.exception("[recallo] failed to write facts batch")

    try:
        llm = _build_llm(cfg)
        agent = Agent(
            task=intent,
            llm=llm,
            register_new_step_callback=_on_step,
            register_done_callback=_on_done,
            max_failures=cfg.max_failures,
        )
        await agent.run(max_steps=cfg.max_steps)
        status = "ok" if seq > 0 else "partial"
        summary = (
            f"{seq} step(s), {len(pending_facts)} fact(s) extracted"
            if seq > 0
            else "agent produced no successful steps"
        )
        await asyncio.to_thread(
            memory.finish_episode, episode.id, status, summary
        )
    except Exception as e:
        logger.exception("[recallo] episode failed")
        await asyncio.to_thread(
            memory.finish_episode,
            episode.id,
            "failed",
            scrub_secrets(str(e)[:512]),
        )
        raise
    return episode.id

"""recallo CLI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from . import __version__
from .embed import get_default_embedder
from .memory import MemoryLane, default_db_path

logging.basicConfig(
    level=logging.INFO,
    format="[recallo] %(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _apply_windows_event_loop_policy() -> None:
    """Leave Windows on its default ProactorEventLoop.

    Earlier guidance suggested forcing WindowsSelectorEventLoopPolicy because
    of historical aiohttp issues, but Selector loops do *not* support
    `asyncio.create_subprocess_exec` on Windows, which browser-use needs to
    launch Chromium. Modern aiohttp/cdp-use work fine on Proactor, so the
    correct call is to keep the default. Verified by an actual `recallo
    explore` failure with `NotImplementedError` from `_make_subprocess_transport`.
    """
    return


@click.group(help="Recallo — local-first browser agent with long-term memory.")
@click.version_option(__version__, prog_name="recallo")
def main() -> None:
    _apply_windows_event_loop_policy()


@main.command(help="Initialise the local memory database (~/.recallo/memory.db).")
def init() -> None:
    mem = MemoryLane(embedder=get_default_embedder())
    click.echo(f"[recallo] memory ready at {mem.db_path}")
    click.echo(
        f"[recallo] sqlite-vec: {'on' if mem.vec_available else 'off'}, "
        f"embedder: {'on' if mem.embedder else 'off'}"
    )
    mem.close()


@main.command(help="Run a browser task; capture the trace into local memory.")
@click.argument("task", nargs=-1, required=True)
@click.option("--provider", default="openai", show_default=True,
              type=click.Choice(["openai", "anthropic", "ollama"]),
              help="Which LLM provider to use.")
@click.option("--model", default=None, help="Override the default model name.")
@click.option("--max-steps", default=50, show_default=True, type=int)
def explore(task: tuple[str, ...], provider: str, model: str | None,
            max_steps: int) -> None:
    from .cortex import CortexConfig, run_episode  # deferred — avoids 200MB load

    intent = " ".join(task)
    mem = MemoryLane(embedder=get_default_embedder())
    try:
        cfg = CortexConfig(llm_provider=provider, llm_model=model, max_steps=max_steps)
        episode_id = asyncio.run(run_episode(intent, mem, cfg))
        click.echo(f"[recallo] episode {episode_id} stored")
    finally:
        mem.close()


@main.command(help="Search past episodes. Uses sqlite-vec semantic search when "
                   "an embedder is available, FTS5 keyword search otherwise.")
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", default=10, show_default=True, type=int)
@click.option("--mode", default="auto", show_default=True,
              type=click.Choice(["auto", "semantic", "keyword"]),
              help="auto picks semantic when an embedder is configured.")
def recall(query: tuple[str, ...], limit: int, mode: str) -> None:
    q = " ".join(query)
    embedder = get_default_embedder()
    mem = MemoryLane(embedder=embedder)
    try:
        rows: list = []
        used = "keyword"
        if mode in ("auto", "semantic") and embedder and mem.vec_available:
            rows = mem.search_facts_semantic(q, limit=limit)
            used = "semantic"
        if not rows and mode != "semantic":
            rows = mem.search_facts(q, limit=limit)
            used = "keyword"
        if not rows:
            click.echo("[recallo] no matches")
            return
        click.echo(f"[recallo] mode={used}")
        for row in rows:
            keys = row.keys()
            distance = f"  (d={row['distance']:.3f})" if "distance" in keys else ""
            click.echo(
                f"- [{row['kind']}] {row['content']}  "
                f"(episode {row['episode_id']}){distance}"
            )
    finally:
        mem.close()


@main.command(help="List recent episodes from local memory.")
@click.option("--limit", default=20, show_default=True, type=int)
def replay(limit: int) -> None:
    mem = MemoryLane()
    try:
        rows = mem.list_episodes(limit=limit)
        if not rows:
            click.echo("[recallo] no episodes yet")
            return
        for row in rows:
            click.echo(
                f"{row['id']}  {row['status']:<8}  {row['intent'][:60]}"
            )
    finally:
        mem.close()


if __name__ == "__main__":
    main()

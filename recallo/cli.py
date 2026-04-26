"""recallo CLI entry point."""

from __future__ import annotations

import asyncio
import logging
import sys

import click

from . import __version__
from .memory import MemoryLane, default_db_path

logging.basicConfig(
    level=logging.INFO,
    format="[recallo] %(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _apply_windows_event_loop_policy() -> None:
    """browser-use + Playwright need WindowsSelectorEventLoopPolicy on Windows.

    See SOURCES_AUDIT.md, browser-use deep read, landmine #1.
    """
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


@click.group(help="Recallo — local-first browser agent with long-term memory.")
@click.version_option(__version__, prog_name="recallo")
def main() -> None:
    _apply_windows_event_loop_policy()


@main.command(help="Initialise the local memory database (~/.recallo/memory.db).")
def init() -> None:
    mem = MemoryLane()
    click.echo(f"[recallo] memory ready at {mem.db_path}")
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
    mem = MemoryLane()
    try:
        cfg = CortexConfig(llm_provider=provider, llm_model=model, max_steps=max_steps)
        episode_id = asyncio.run(run_episode(intent, mem, cfg))
        click.echo(f"[recallo] episode {episode_id} stored")
    finally:
        mem.close()


@main.command(help="Search past episodes for relevant facts (M1: keyword/FTS5).")
@click.argument("query", nargs=-1, required=True)
@click.option("--limit", default=10, show_default=True, type=int)
def recall(query: tuple[str, ...], limit: int) -> None:
    q = " ".join(query)
    mem = MemoryLane()
    try:
        rows = mem.search_facts(q, limit=limit)
        if not rows:
            click.echo("[recallo] no matches")
            return
        for row in rows:
            click.echo(f"- [{row['kind']}] {row['content']}  (episode {row['episode_id']})")
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

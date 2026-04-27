"""recallo CLI entry point."""

from __future__ import annotations

import asyncio
import logging

import click

from . import __version__
from .embed import get_default_embedder
from .memory import MemoryLane

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
@click.option("--max-steps", default=50, show_default=True, type=int,
              help="Hard cap on browser-use steps before the agent gives up.")
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


def _format_ts(ts: int | None) -> str:
    if not ts:
        return "-"
    import datetime as _dt
    # UTC keeps replays consistent across machines / time zones.
    return _dt.datetime.fromtimestamp(
        ts, tz=_dt.timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%SZ")


def _truncate(text: str | None, n: int) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ").replace("\r", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


@main.command(help="List recent episodes, or replay one by id (or unique id prefix).")
@click.argument("episode", required=False)
@click.option("--limit", default=20, show_default=True, type=int,
              help="Max rows when listing.")
def replay(episode: str | None, limit: int) -> None:
    mem = MemoryLane()
    try:
        if episode is None:
            rows = mem.list_episodes(limit=limit)
            if not rows:
                click.echo("[recallo] no episodes yet")
                return
            click.echo(f"{'id':<36}  {'status':<8}  {'started (UTC)':<20}  intent")
            for row in rows:
                click.echo(
                    f"{row['id']}  {row['status']:<8}  "
                    f"{_format_ts(row['started_at']):<20}  "
                    f"{_truncate(row['intent'], 60)}"
                )
            return

        # Resolve id or prefix
        candidates = mem.resolve_episode_id(episode)
        if not candidates:
            click.echo(f"[recallo] no episode matches '{episode}'", err=True)
            raise click.exceptions.Exit(1)
        if len(candidates) > 1:
            click.echo(
                f"[recallo] '{episode}' is ambiguous, matches {len(candidates)}:",
                err=True,
            )
            for cid in candidates[:5]:
                click.echo(f"  {cid}", err=True)
            raise click.exceptions.Exit(1)
        ep = mem.get_episode(candidates[0])
        if ep is None:
            click.echo("[recallo] episode disappeared mid-query", err=True)
            raise click.exceptions.Exit(1)

        traces = mem.list_traces(ep["id"])
        facts = mem.list_facts(ep["id"])
        duration = ""
        if ep["started_at"] and ep["ended_at"]:
            duration = f" ({ep['ended_at'] - ep['started_at']}s)"

        click.echo(f"Episode {ep['id']}")
        click.echo(f"  intent : {ep['intent']}")
        click.echo(f"  status : {ep['status']}")
        click.echo(f"  start  : {_format_ts(ep['started_at'])}")
        click.echo(f"  end    : {_format_ts(ep['ended_at'])}{duration}")
        click.echo(f"  steps  : {len(traces)}")
        click.echo(f"  facts  : {len(facts)}")
        if ep["summary"]:
            click.echo(f"  summary: {_truncate(ep['summary'], 200)}")

        click.echo("\nTimeline:")
        if not traces:
            click.echo("  (no steps recorded)")
        for t in traces:
            url = _truncate(t["url"], 60)
            click.echo(f"  [{t['seq']}] {t['action_type']:<18} {url}")
            if t["text_excerpt"]:
                click.echo(f"        text:     {_truncate(t['text_excerpt'], 80)}")
            if t["thinking"]:
                click.echo(f"        thinking: {_truncate(t['thinking'], 80)}")

        click.echo("\nFacts:")
        if not facts:
            click.echo("  (none)")
        for f in facts:
            click.echo(f"  - [{f['kind']}] {_truncate(f['content'], 100)}")
            if f["source_url"]:
                click.echo(f"      src: {f['source_url']}")
    finally:
        mem.close()


if __name__ == "__main__":
    main()

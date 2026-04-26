"""SQLite-backed Memory Lane.

M1 stores episodes / traces / facts and exposes simple insert + FTS5 keyword
search. M2 will add an sqlite-vec virtual table for semantic recall.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path


def default_db_path() -> Path:
    return Path.home() / ".recallo" / "memory.db"


def _load_schema() -> str:
    return files("recallo").joinpath("schema.sql").read_text(encoding="utf-8")


@dataclass
class Episode:
    id: str
    intent: str
    started_at: int
    summary: str | None = None
    ended_at: int | None = None
    status: str = "running"


@dataclass
class Trace:
    episode_id: str
    seq: int
    action_type: str
    ts: int
    url: str | None = None
    selector: str | None = None
    text_excerpt: str | None = None
    thinking: str | None = None


@dataclass
class Fact:
    episode_id: str
    kind: str
    content: str
    source_url: str | None = None
    ts: int = field(default_factory=lambda: int(time.time()))


class MemoryLane:
    """Thin SQLite wrapper. Single connection per process, WAL mode."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_load_schema())

    def close(self) -> None:
        self.conn.close()

    # -- episodes -----------------------------------------------------------

    def start_episode(self, intent: str) -> Episode:
        ep = Episode(id=str(uuid.uuid4()), intent=intent, started_at=int(time.time()))
        self.conn.execute(
            "INSERT INTO episodes(id, intent, started_at, status) VALUES (?, ?, ?, ?)",
            (ep.id, ep.intent, ep.started_at, ep.status),
        )
        return ep

    def finish_episode(self, episode_id: str, status: str, summary: str | None = None) -> None:
        self.conn.execute(
            "UPDATE episodes SET status=?, summary=?, ended_at=? WHERE id=?",
            (status, summary, int(time.time()), episode_id),
        )

    # -- traces -------------------------------------------------------------

    def insert_trace(self, trace: Trace) -> None:
        self.conn.execute(
            """INSERT INTO traces
                 (episode_id, seq, action_type, url, selector, text_excerpt, thinking, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trace.episode_id,
                trace.seq,
                trace.action_type,
                trace.url,
                trace.selector,
                trace.text_excerpt,
                trace.thinking,
                trace.ts,
            ),
        )

    # -- facts --------------------------------------------------------------

    def insert_fact(self, fact: Fact) -> int:
        cur = self.conn.execute(
            "INSERT INTO facts(episode_id, kind, content, source_url, ts) VALUES (?, ?, ?, ?, ?)",
            (fact.episode_id, fact.kind, fact.content, fact.source_url, fact.ts),
        )
        return cur.lastrowid

    def search_facts(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """Keyword search across facts via FTS5 (M1).

        M2 will add a parallel `search_facts_semantic` using sqlite-vec.
        """
        return list(
            self.conn.execute(
                """SELECT f.id, f.episode_id, f.kind, f.content, f.source_url, f.ts
                   FROM facts_fts
                   JOIN facts f ON f.id = facts_fts.rowid
                   WHERE facts_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (query, limit),
            )
        )

    def list_episodes(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT id, intent, summary, started_at, ended_at, status "
                "FROM episodes ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        )

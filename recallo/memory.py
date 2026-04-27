"""SQLite-backed Memory Lane.

Three tables — ``episodes``, ``traces``, ``facts`` — plus an FTS5 mirror over
``facts`` for keyword recall. M2 also creates a ``fact_vec`` virtual table
(``sqlite-vec``) that mirrors ``facts`` by ``rowid``; semantic search becomes
available when an :class:`~recallo.embed.Embedder` is wired in.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

import sqlite_vec

from .embed import EMBEDDING_DIM, Embedder


_VEC_SCHEMA = (
    f"CREATE VIRTUAL TABLE IF NOT EXISTS fact_vec USING vec0("
    f"embedding float[{EMBEDDING_DIM}]"
    f");"
)


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
    """Single SQLite connection with WAL, FTS5, and (optional) sqlite-vec.

    Pass an ``Embedder`` to enable semantic recall. Without one the keyword
    search via :meth:`search_facts` keeps working.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row

        self._vec_available = self._try_enable_vec()
        self.conn.executescript(_load_schema())
        if self._vec_available:
            self.conn.executescript(_VEC_SCHEMA)
        self.embedder = embedder

    def _try_enable_vec(self) -> bool:
        try:
            self.conn.enable_load_extension(True)
        except (AttributeError, sqlite3.OperationalError):
            return False
        try:
            sqlite_vec.load(self.conn)
        except Exception:
            return False
        finally:
            try:
                self.conn.enable_load_extension(False)
            except Exception:
                pass
        return True

    @property
    def vec_available(self) -> bool:
        return self._vec_available

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
            "INSERT INTO facts(episode_id, kind, content, source_url, ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (fact.episode_id, fact.kind, fact.content, fact.source_url, fact.ts),
        )
        fact_id = cur.lastrowid
        if self.embedder and self._vec_available:
            vec = self.embedder.embed(fact.content)
            if len(vec) != EMBEDDING_DIM:
                raise ValueError(
                    f"embedder produced dim={len(vec)}, expected {EMBEDDING_DIM}"
                )
            self.conn.execute(
                "INSERT INTO fact_vec(rowid, embedding) VALUES (?, ?)",
                (fact_id, sqlite_vec.serialize_float32(vec)),
            )
        return fact_id

    def search_facts(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """FTS5 keyword search across ``facts`` (case-insensitive, ranked)."""
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

    def search_facts_semantic(self, query: str, limit: int = 10) -> list[sqlite3.Row]:
        """Vector kNN over ``fact_vec``. Returns ``[]`` if no embedder/extension."""
        if not (self.embedder and self._vec_available):
            return []
        qvec = self.embedder.embed(query)
        return list(
            self.conn.execute(
                """SELECT f.id, f.episode_id, f.kind, f.content, f.source_url, f.ts,
                          fact_vec.distance AS distance
                   FROM fact_vec
                   JOIN facts f ON f.id = fact_vec.rowid
                   WHERE fact_vec.embedding MATCH ?
                     AND k = ?
                   ORDER BY distance""",
                (sqlite_vec.serialize_float32(qvec), limit),
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

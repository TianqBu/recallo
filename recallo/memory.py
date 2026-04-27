"""SQLite-backed Memory Lane.

Three tables — ``episodes``, ``traces``, ``facts`` — plus an FTS5 mirror over
``facts`` for keyword recall. M2 also creates a ``fact_vec`` virtual table
(``sqlite-vec``) that mirrors ``facts`` by ``rowid``; semantic search becomes
available when an :class:`~recallo.embed.Embedder` is wired in.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

# Prefer `pysqlite3-binary` when available — many distro Pythons (notably the
# python.org / actions/setup-python builds on macOS) ship sqlite3 without
# loadable-extension support, which sqlite-vec needs. pysqlite3-binary has
# wheels on Linux + macOS; on Windows the stdlib already supports extensions.
try:
    import pysqlite3 as sqlite3  # type: ignore[import-not-found]
except ImportError:
    import sqlite3  # type: ignore[no-redef]

import sqlite_vec

from .embed import EMBEDDING_DIM, Embedder


_VEC_SCHEMA = f"""\
CREATE VIRTUAL TABLE IF NOT EXISTS fact_vec USING vec0(
    embedding float[{EMBEDDING_DIM}]
);

-- ON DELETE CASCADE doesn't propagate into vec0 virtual tables, so wire it up
-- explicitly: when a fact row goes away, drop its embedding too.
CREATE TRIGGER IF NOT EXISTS fact_vec_ad AFTER DELETE ON facts
BEGIN
    DELETE FROM fact_vec WHERE rowid = old.id;
END;
"""

# Bumped when schema changes. ``MemoryLane.__init__`` reads ``PRAGMA
# user_version`` and runs migrations from there to ``_SCHEMA_VERSION``.
_SCHEMA_VERSION = 1


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
        existed = self.db_path.exists()
        # check_same_thread=False so the connection can be reached from
        # asyncio executor threads (cortex offloads sqlite via to_thread).
        # Single-writer asyncio means no real concurrency.
        self.conn = sqlite3.connect(
            self.db_path, isolation_level=None, check_same_thread=False
        )
        self.conn.row_factory = sqlite3.Row
        try:
            self._vec_available = self._try_enable_vec()
            self.conn.executescript(_load_schema())
            if self._vec_available:
                self.conn.executescript(_VEC_SCHEMA)
            self._migrate_if_needed()
        except Exception:
            self.conn.close()
            raise
        # Lock the file down to the owner on POSIX; chmod is a no-op on Windows.
        if not existed:
            try:
                os.chmod(self.db_path, 0o600)
            except OSError:
                pass
        self.embedder = embedder

    def _migrate_if_needed(self) -> None:
        """Run forward migrations from ``user_version`` to ``_SCHEMA_VERSION``.

        Version 0 (un-tagged) is the initial schema baked into ``schema.sql`` +
        ``_VEC_SCHEMA``; ``CREATE ... IF NOT EXISTS`` makes that step
        idempotent. Future versions add a branch here. We never run downward
        migrations.
        """
        cur = self.conn.execute("PRAGMA user_version")
        current = cur.fetchone()[0]
        if current > _SCHEMA_VERSION:
            raise RuntimeError(
                f"database at {self.db_path} reports schema version "
                f"{current}, newer than this build's {_SCHEMA_VERSION}"
            )
        if current == _SCHEMA_VERSION:
            return
        # current < _SCHEMA_VERSION → step forward.
        # (No mid-version migrations exist yet; this is the scaffolding.)
        self.conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")

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
        if fact_id is None:
            raise RuntimeError("sqlite returned no lastrowid for facts insert")
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

    def insert_facts_batch(self, facts: list[Fact]) -> list[int]:
        """Insert N facts with a single batch embedding call.

        For an episode that produces dozens of facts, ``insert_fact`` would
        fire dozens of serial OpenAI round-trips. This collapses them to one.
        Embeddings are computed first (so a network failure raises before any
        DB write); then facts + vectors are inserted inside one BEGIN/COMMIT.
        """
        if not facts:
            return []
        do_embed = bool(self.embedder and self._vec_available)
        vectors: list[list[float]] = []
        if do_embed:
            assert self.embedder is not None  # narrow for type checker
            vectors = self.embedder.embed_batch([f.content for f in facts])
            for v in vectors:
                if len(v) != EMBEDDING_DIM:
                    raise ValueError(
                        f"embedder produced dim={len(v)}, expected {EMBEDDING_DIM}"
                    )

        ids: list[int] = []
        self.conn.execute("BEGIN")
        try:
            for i, fact in enumerate(facts):
                cur = self.conn.execute(
                    "INSERT INTO facts(episode_id, kind, content, source_url, ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (fact.episode_id, fact.kind, fact.content,
                     fact.source_url, fact.ts),
                )
                fact_id = cur.lastrowid
                if fact_id is None:
                    raise RuntimeError("sqlite returned no lastrowid")
                ids.append(fact_id)
                if do_embed:
                    self.conn.execute(
                        "INSERT INTO fact_vec(rowid, embedding) VALUES (?, ?)",
                        (fact_id, sqlite_vec.serialize_float32(vectors[i])),
                    )
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        return ids

    @staticmethod
    def _fts5_escape(query: str) -> str:
        """Wrap a user query as a single FTS5 phrase.

        FTS5 treats characters like ``"``, ``-``, ``:``, ``(`` and ``AND`` as
        operators; passing user input directly into MATCH triggers
        ``sqlite3.OperationalError: fts5: syntax error`` on common inputs
        like ``self-rag`` or ``"quoted"``. Wrapping the input as one phrase
        and doubling internal quotes is the FTS5-recommended approach.
        """
        return '"' + (query or "").replace('"', '""') + '"'

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
                (self._fts5_escape(query), limit),
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

    # -- replay -------------------------------------------------------------

    def get_episode(self, episode_id: str) -> sqlite3.Row | None:
        """Look up one episode by exact id."""
        row = self.conn.execute(
            "SELECT id, intent, summary, started_at, ended_at, status "
            "FROM episodes WHERE id = ?",
            (episode_id,),
        ).fetchone()
        return row

    def resolve_episode_id(self, prefix: str) -> list[str]:
        """Return episode ids whose id starts with ``prefix``.

        Returns one element on a unique match, more than one on ambiguity, and
        the empty list on no match. CLI callers pick the policy. The prefix
        is escaped so ``%`` and ``_`` from user input don't act as wildcards.
        """
        if not prefix:
            return []
        # Escape LIKE metacharacters; ``\\`` is the escape char declared below.
        escaped = (
            prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        rows = self.conn.execute(
            "SELECT id FROM episodes WHERE id LIKE ? ESCAPE '\\' "
            "ORDER BY started_at DESC LIMIT 16",
            (escaped + "%",),
        ).fetchall()
        return [r["id"] for r in rows]

    def list_traces(self, episode_id: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT seq, action_type, url, selector, text_excerpt, thinking, ts "
                "FROM traces WHERE episode_id = ? ORDER BY seq",
                (episode_id,),
            )
        )

    def list_facts(self, episode_id: str) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT id, kind, content, source_url, ts "
                "FROM facts WHERE episode_id = ? ORDER BY id",
                (episode_id,),
            )
        )

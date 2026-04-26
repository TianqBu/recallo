-- Recallo memory schema. SQLite 3.35+.
-- One file lives at ~/.recallo/memory.db.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One row per recallo task.
CREATE TABLE IF NOT EXISTS episodes (
    id          TEXT PRIMARY KEY,           -- uuid4
    intent      TEXT NOT NULL,              -- the user's original query
    summary     TEXT,                       -- LLM-generated summary, populated when done
    started_at  INTEGER NOT NULL,           -- unix epoch seconds
    ended_at    INTEGER,
    status      TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'ok', 'failed', 'partial', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_episodes_started ON episodes(started_at DESC);

-- One row per browser action emitted by the agent.
CREATE TABLE IF NOT EXISTS traces (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id    TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    seq           INTEGER NOT NULL,         -- step index inside the episode
    action_type   TEXT NOT NULL,            -- navigate / click / type / extract / ...
    url           TEXT,
    selector      TEXT,
    text_excerpt  TEXT,                     -- short content snapshot (capped)
    thinking      TEXT,                     -- LLM thinking for this step, optional
    ts            INTEGER NOT NULL,
    UNIQUE (episode_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_traces_episode ON traces(episode_id, seq);
CREATE INDEX IF NOT EXISTS idx_traces_url ON traces(url);

-- Structured facts extracted from an episode.
CREATE TABLE IF NOT EXISTS facts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id  TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,              -- paper / author / claim / link / ...
    content     TEXT NOT NULL,
    source_url  TEXT,
    ts          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_episode ON facts(episode_id);
CREATE INDEX IF NOT EXISTS idx_facts_kind ON facts(kind);

-- FTS5 keyword index for M1-era recall (M2 will add sqlite-vec for semantic).
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    content,
    kind UNINDEXED,
    episode_id UNINDEXED,
    content='facts',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, content, kind, episode_id)
    VALUES (new.id, new.content, new.kind, new.episode_id);
END;

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, kind, episode_id)
    VALUES ('delete', old.id, old.content, old.kind, old.episode_id);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content, kind, episode_id)
    VALUES ('delete', old.id, old.content, old.kind, old.episode_id);
    INSERT INTO facts_fts(rowid, content, kind, episode_id)
    VALUES (new.id, new.content, new.kind, new.episode_id);
END;

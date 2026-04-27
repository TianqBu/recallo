# Changelog

All notable changes are recorded here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it
hits v1.0.

## [Unreleased]

## [0.1.0] — 2026-04-27

First public cut. Pre-alpha — APIs may break before v0.2.

### Added

- `recallo init` — creates `~/.recallo/memory.db` (SQLite + FTS5 +
  `sqlite-vec` virtual table when the extension is loadable).
- `recallo explore "<task>"` — drives a `browser-use` agent against a URL or
  arxiv id, captures every step into `traces` and every extracted result
  into `facts`.
- `recallo recall "<query>"` — semantic recall via `sqlite-vec` when an
  embedder is configured; FTS5 keyword fallback otherwise. `--mode keyword`
  / `--mode semantic` pin the mode.
- `recallo replay [<id-prefix>]` — list all episodes or render one as a
  step/fact timeline.
- Privacy posture: domain blacklist, URL OAuth-param stripper, API-key
  regex scrubber (`sk-` / `sk-ant-` / AWS / GCP / GitHub PAT / Slack /
  `Bearer …`), `0o600` chmod on the db file (POSIX).
- Schema versioning scaffolding (`PRAGMA user_version`, `_SCHEMA_VERSION`
  in `recallo/memory.py`).
- Batch embeddings: `Embedder.embed_batch(texts)` and
  `MemoryLane.insert_facts_batch(facts)` collapse N round-trips into 1.
- Async-correct sqlite writes: every `memory.insert_*` call from
  browser-use callbacks is dispatched via `asyncio.to_thread`.
- CI: matrix on Linux/macOS/Windows × Python 3.11/3.12, with graceful skip
  for sqlite-vec on platforms whose stdlib sqlite3 lacks loadable-extension
  support.
- 54-test suite covering memory, safety, cortex, embed, ingestor, recall
  CLI, replay CLI, and the `vec0` round-trip.

### Reviewed against

- Two adversarial review passes (20 agents → Tier 1+2 fixes; 4 agents →
  performance + correctness).

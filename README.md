# Recallo

> Give your browser agent a memory it can prove.
> Local-first browser agent with long-term memory, focused on paper reading.

Recallo browses arxiv (or any URL you point it at), parses what it sees, and
stores everything in a local SQLite database under `~/.recallo/`. Next time
you ask "what did that Self-RAG paper say about retrieval?", it answers from
your past sessions — no cloud round-trip, no re-prompting.

> **Status:** pre-alpha. M1 skeleton only. Not all commands listed below are
> wired up yet.

## Why local-first?

Atlas, Comet and most "AI browsers" keep your browsing memory on someone
else's servers. Recallo keeps it in `~/.recallo/memory.db` on your machine —
a single SQLite file you can inspect, back up, share, or delete.

## Quick start

```bash
pip install -e .                       # from a clone, until PyPI is ready
recallo init                           # creates ~/.recallo/memory.db
recallo explore "Summarize arxiv:2310.11511"
# ...later...
recallo recall "what did that Self-RAG paper say about retrieval?"
# Force keyword mode (FTS5) when you don't want to spend on embeddings:
recallo recall "self rag" --mode keyword
```

### Provider keys

Recallo is BYOK. Set one of:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
# or run a local Ollama server, no key needed
```

### Optional: high-quality PDF parsing via MinerU

For full-text academic PDF parsing (figures, tables, equations), start
MinerU's HTTP API in another terminal:

```bash
pip install "mineru[pipeline]"
# Mainland China users: faster model download
export MINERU_MODEL_SOURCE=modelscope
mineru-models-download
mineru-api --host 127.0.0.1 --port 8000
```

If `mineru-api` is not running, Recallo falls back to `trafilatura`, then to
the arxiv abstract page.

> PDF parsing in Recallo is powered by [MinerU](https://github.com/opendatalab/MinerU).

## Windows notes

- Recallo keeps the default `ProactorEventLoop`; do not override it (Selector
  loops can't `create_subprocess_exec`, which browser-use needs for Chromium)
- If Chrome is in a non-default location, set
  `BROWSER_USE_BROWSER_PATH=C:\Path\To\chrome.exe`

## What's stored

Three tables plus two indexes, all in a single SQLite file:

- `episodes` — one row per task, with intent, status, summary
- `traces` — per-step browser action records (action, URL, selector, text)
- `facts` — content extracted from the page, written by the done-callback
- `facts_fts` — FTS5 keyword index over `facts` (M1 fallback)
- `fact_vec` — sqlite-vec virtual table, 1536-d float vectors over `facts` (M2)

See `recallo/schema.sql` for the full schema.

### Recall modes

When `OPENAI_API_KEY` is set, `recallo recall` embeds your query and runs
kNN over `fact_vec`. Without a key, it transparently falls back to FTS5 on
`facts_fts`. Pass `--mode keyword` or `--mode semantic` to pin the mode.

## Privacy

Recallo never uploads anything. A built-in domain blacklist skips banking,
webmail, and health sites. Edit `recallo/safety.py` to extend it.

## Roadmap

- M1 — installable skeleton, `init`, `explore` runs browser-use ✅
- M2 — sqlite-vec semantic `recall` + FTS5 fallback, fact extraction from
  agent history ✅ ⬅ current
- M3 — packaging for `pip install recallo` from PyPI, demo GIF, docs
- M4 — Memory Replay timeline, MinerU three-tier fallback, broader tests

## Standing on the shoulders of giants

- [browser-use](https://github.com/browser-use/browser-use) — browser automation
- [MinerU](https://github.com/opendatalab/MinerU) — academic PDF parsing
- [trafilatura](https://github.com/adbar/trafilatura) — fallback text extraction
- [sqlite-vec](https://github.com/asg017/sqlite-vec) — local vector search

See [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md) for full attribution.

## License

Apache 2.0

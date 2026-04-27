# Launch copy

Drop-in copy for announcing Recallo. Pick the one that fits the venue.

---

## Hacker News (Show HN)

**Title** (≤80 chars, no clickbait per HN rules):

```
Show HN: Recallo – local-first browser agent with long-term memory in SQLite
```

**Body** (the URL field gets the GitHub repo, body is the optional comment):

```
Hi HN, Recallo is a small Python CLI that drives browser-use to read pages
(arxiv papers, mostly) and stores everything — episodes, per-step traces,
extracted facts — in a single SQLite file under ~/.recallo/.

The thing I wanted to build was the recall side. After you've read 50
papers, "what did that Self-RAG paper say about retrieval?" should answer
from disk, not re-prompt the LLM. Recallo does it in two ways:

  * sqlite-vec semantic search when you have an embedder configured
  * FTS5 keyword fallback when you don't (or to save credits)

Both go through the same `recallo recall <query>` command.

The pitch vs. ChatGPT Atlas / Comet: those keep your browsing memory on
their servers. Recallo keeps it in ~/.recallo/memory.db — one file you can
inspect, back up, share, or delete. There's a domain blacklist + URL
scrubber + API-key scrubber so banking / mail / OAuth tokens don't end
up in the trace table.

Stack: browser-use 0.12.6 (pinned), sqlite-vec, trafilatura. Optional
MinerU as a sidecar HTTP service for high-quality PDF parsing.

Status is pre-alpha — 45 tests, CI green on Linux/macOS/Windows × Py 3.11/3.12,
but the API will move before v0.2. Feedback wanted especially on:

  - which sites belong on the default blacklist
  - whether the FTS5+vec dual recall feels right or you'd want a single mode
  - how you'd want trace replay (currently a CLI table; thinking of a TUI)

https://github.com/TianqBu/recallo
```

---

## X / Twitter

**Tweet 1 (the hook, single tweet)**:

```
shipped Recallo — a local-first browser agent that actually remembers

it reads papers via browser-use, dumps every step + extracted fact into
a SQLite file under ~/.recallo/, and lets you `recallo recall "..."` any
of it later. semantic via sqlite-vec, keyword via FTS5

no cloud. one .db file you own.

https://github.com/TianqBu/recallo
```

**Thread version (5 tweets)**:

```
1/  shipped Recallo — local-first browser agent w/ long-term memory.
    https://github.com/TianqBu/recallo

    pip install git+https://github.com/TianqBu/recallo.git
    recallo explore "summarize arxiv 2310.11511"
    recallo recall "what did that self-rag paper say about retrieval?"

2/  the differentiator is the second command. it runs WITHOUT a network
    round-trip — Recallo answers from ~/.recallo/memory.db, even offline.

    Atlas / Comet keep this on their servers. Recallo keeps it in one
    SQLite file you can inspect, back up, share, or delete.

3/  stack:
      • browser-use 0.12.6 (pinned)
      • sqlite-vec for semantic recall
      • FTS5 fallback when you don't want to spend on embeddings
      • trafilatura + optional MinerU sidecar for PDFs

    no Postgres, no Docker, no daemon.

4/  privacy isn't an afterthought:
      • domain blacklist (banking, webmail, social DMs, password mgrs)
      • URL OAuth-token stripper
      • regex scrubber for sk-/sk-ant-/AWS/GCP/GitHub/Slack keys
      • 0o600 chmod on the .db file

5/  pre-alpha. 45 tests, CI green on linux/mac/windows × py 3.11/3.12.
    looking for feedback on:
      - default blacklist coverage
      - FTS5+vec dual recall vs picking one
      - trace replay UX

    https://github.com/TianqBu/recallo
```

---

## reddit r/MachineLearning (low priority, mods are strict)

Tag: `[P]` (project)

**Title**:

```
[P] Recallo: a local-first browser agent that stores everything (traces, facts, embeddings) in one SQLite file
```

Body: same as HN, but lead with the technical content (sqlite-vec + FTS5 dual,
browser-use callbacks) since /r/ML cares about the architecture more than the
pitch.

---

## reddit r/LocalLLaMA

These users care about local-first. The pitch lands harder here than ML.

**Title**:

```
Recallo — pip install, no daemon, no docker. Browse → remember in SQLite. Local recall via sqlite-vec OR FTS5 fallback.
```

Lead with the Ollama support (`recallo explore --provider ollama`) — that's the
killer feature for this sub.

---

## What to do RIGHT NOW (in order)

1. ✅ Repo description + topics — done
2. Record the GIF: `vhs docs/demo.tape` → `docs/demo.gif`, then add to README
3. Pin a "v0.1.0" GitHub Release with changelog (no PyPI yet, just a GH release)
4. Post Show HN at 8–10am Pacific on a Tuesday/Wednesday (best traffic window)
5. Post the X thread same morning, link to the HN post in tweet 5
6. r/LocalLLaMA in the afternoon if HN doesn't take off

Don't post all venues simultaneously — HN ranks down posts that look like
launch spam, and a parallel reddit post that goes hot can divert traffic from
your HN attempt.

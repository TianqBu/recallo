# Demo script

A reproducible script for capturing the README demo (asciinema or
`vhs`-style GIF). Run from a clean machine with `OPENAI_API_KEY` set.

```bash
# Install
pip install recallo

# Initialise local memory
recallo init

# Read a paper. The browser opens; the agent navigates arxiv and extracts
# the abstract, then writes facts into ~/.recallo/memory.db.
recallo explore "Open arxiv 2310.11511 and summarize the Self-RAG abstract"

# Recall — semantic when an embedder is available, FTS5 keyword fallback.
recallo recall "what did that Self-RAG paper say about retrieval?"

# Force keyword mode if you don't want to spend on embeddings.
recallo recall "self rag" --mode keyword

# List past episodes; replay one by id prefix.
recallo replay
recallo replay 6e6c4710
```

## Recording the GIF

We deliberately don't bundle a recording dependency. Two reasonable choices:

- **`vhs`** (Charm, Go) — declarative `.tape` files, deterministic output.
- **`asciinema` + `agg`** — text-based; smaller, but no real cursor / browser.

A minimal `vhs` tape that exercises the four commands above lives at
`docs/demo.tape` (TODO: contributor welcome).

## What to highlight

The pitch is "memory you can prove":

1. `recallo explore` runs once → DB grows.
2. **Close the terminal.** Reopen.
3. `recallo recall` answers from `~/.recallo/memory.db` — no LLM call, no
   network, just a single `.db` file you own.

That third beat is the differentiator vs Atlas / Comet.

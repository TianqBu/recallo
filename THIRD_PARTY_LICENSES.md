# Third-Party Licenses

Recallo builds on the following open-source projects. Their licenses and
attribution requirements are honored here.

## browser-use

- Source: https://github.com/browser-use/browser-use
- License: MIT
- Used as: pip dependency (`browser-use==0.12.6`), pinned for API stability
- Role in Recallo: Browser Cortex — drives the LLM-controlled browser session
  and supplies the per-step callback used to capture Web Trace records

## MinerU

- Source: https://github.com/opendatalab/MinerU
- License: MinerU Open Source License (Apache 2.0 base + commercial threshold)
- Used as: optional `mineru-api` subprocess started by the user, called over
  HTTP — no source modification, no static linking
- Role in Recallo: high-quality PDF / Office parsing for academic papers

> PDF parsing in Recallo is powered by MinerU.

The MinerU license imposes additional terms above 100M MAU or USD 20M/month
revenue. Recallo is a single-user, local-first project and does not approach
these thresholds in its open-source form.

## trafilatura

- Source: https://github.com/adbar/trafilatura
- License: Apache 2.0
- Used as: pip dependency
- Role in Recallo: lightweight fallback web/PDF text extraction when MinerU
  is unavailable

## sqlite-vec (optional, for M2 vector recall)

- Source: https://github.com/asg017/sqlite-vec
- License: Apache 2.0 / MIT (dual)
- Used as: optional pip dependency for semantic recall
- Role in Recallo: vector index over Episode/Fact embeddings

## httpx

- Source: https://github.com/encode/httpx
- License: BSD-3-Clause
- Used as: pip dependency
- Role in Recallo: HTTP client to talk to the user's local `mineru-api`

## click

- Source: https://github.com/pallets/click
- License: BSD-3-Clause
- Used as: pip dependency (already pulled in by browser-use)
- Role in Recallo: CLI argument parsing

---

## Standing on the shoulders of giants

Recallo would not exist without the work above. Bug reports and improvements
should also be sent upstream where appropriate.

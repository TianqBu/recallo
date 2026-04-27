# Security Policy

## Reporting a vulnerability

Recallo is local-first and stores potentially sensitive browsing data in
`~/.recallo/memory.db`. Security issues — especially anything that could leak
that data, bypass the domain blacklist, leak a stored API key, or allow
remote code execution — are taken seriously.

**Please do not file public issues for security problems.**

Email <tianqibu.me@gmail.com> with:

- A short description of the vulnerability
- Steps to reproduce (a minimal repro is gold)
- The Recallo version (`recallo --version`) and OS

You can expect:

- An acknowledgement within 5 days
- A fix or written rationale within 30 days for HIGH/CRITICAL issues
- Credit in the release notes if you'd like (your call)

## What's in scope

- The Recallo CLI and its persisted data (`~/.recallo/`)
- The `recallo/safety.py` blacklist / URL-scrubber / secret-scrubber paths
- The schema / migration logic in `recallo/memory.py`
- The browser-use integration in `recallo/cortex.py`

## What's out of scope

- Vulnerabilities in upstream dependencies
  ([browser-use](https://github.com/browser-use/browser-use),
  [sqlite-vec](https://github.com/asg017/sqlite-vec),
  [trafilatura](https://github.com/adbar/trafilatura),
  [MinerU](https://github.com/opendatalab/MinerU)) — please report
  upstream first; we'll bump our pin once a patch lands
- Issues that require an attacker to already have local code execution on
  the user's machine (Recallo's threat model assumes a trusted local user)
- Issues in your LLM provider (OpenAI / Anthropic / Ollama) — report to them

## Supported versions

Pre-alpha (v0.1.x) is the only line under active development. We'll
backport security fixes once we cut a v1.0.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

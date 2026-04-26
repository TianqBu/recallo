"""Doc Ingestor — three-tier fallback for turning a URL/PDF into text.

Tier 1: MinerU FastAPI server at http://127.0.0.1:8000 (must be started by
        the user separately; see README).
Tier 2: trafilatura for general-purpose web/PDF text extraction.
Tier 3: arxiv abstract page scrape, last-resort.

The audit (`SOURCES_AUDIT.md`) confirmed MinerU has no Python library API,
so tier 1 is HTTP only.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

logger = logging.getLogger("recallo.ingestor")

DEFAULT_MINERU_URL = "http://127.0.0.1:8000"
ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5})(v\d+)?")


@dataclass
class ParsedDoc:
    source: str           # "mineru" | "trafilatura" | "arxiv_html"
    text: str             # plain text or markdown
    url: str | None = None


def _looks_like_arxiv(target: str) -> str | None:
    m = ARXIV_ID_RE.search(target)
    return m.group(1) if m else None


def parse(target: str, *, mineru_url: str = DEFAULT_MINERU_URL,
          timeout_s: float = 60.0) -> ParsedDoc:
    """Resolve `target` (URL, arxiv id, or local path) into a ParsedDoc."""
    arxiv_id = _looks_like_arxiv(target)
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else target
    abs_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else target

    if Path(target).exists():
        try:
            return _via_mineru_local_pdf(Path(target), mineru_url, timeout_s)
        except Exception as e:
            logger.warning("[recallo] mineru local-pdf failed: %s", e)

    try:
        return _via_trafilatura(pdf_url, timeout_s) or _via_trafilatura(abs_url, timeout_s)
    except Exception as e:
        logger.warning("[recallo] trafilatura failed: %s", e)

    if arxiv_id:
        try:
            return _via_arxiv_html(arxiv_id, timeout_s)
        except Exception as e:
            logger.warning("[recallo] arxiv html scrape failed: %s", e)

    raise RuntimeError(f"all ingestion tiers failed for: {target}")


def _via_mineru_local_pdf(pdf: Path, mineru_url: str, timeout_s: float) -> ParsedDoc:
    with httpx.Client(timeout=timeout_s) as client:
        with pdf.open("rb") as fh:
            resp = client.post(
                f"{mineru_url}/file_parse",
                files={"files": (pdf.name, fh, "application/pdf")},
                data={"return_md": "true"},
            )
        resp.raise_for_status()
        body = resp.json()
        md = body.get("md") or ""
        if not md:
            raise RuntimeError("mineru returned no markdown")
        return ParsedDoc(source="mineru", text=md, url=None)


def _via_trafilatura(url: str, timeout_s: float) -> ParsedDoc | None:
    try:
        import trafilatura
    except ImportError:
        return None
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None
    text = trafilatura.extract(downloaded, include_formatting=True)
    if not text:
        return None
    return ParsedDoc(source="trafilatura", text=text, url=url)


def _via_arxiv_html(arxiv_id: str, timeout_s: float) -> ParsedDoc:
    abs_url = f"https://arxiv.org/abs/{arxiv_id}"
    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        r = client.get(abs_url, headers={"User-Agent": "recallo/0.1"})
        r.raise_for_status()
    html = r.text
    m = re.search(r'<blockquote class="abstract[^"]*">(.+?)</blockquote>',
                  html, re.DOTALL)
    abstract = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    if not abstract:
        raise RuntimeError("arxiv abstract not found")
    return ParsedDoc(source="arxiv_html", text=abstract, url=abs_url)

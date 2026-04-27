"""Domain blacklist + URL/secret scrubbing.

Recallo is local-first; this module exists so even local storage doesn't
capture banking, webmail, health-portal content, OAuth-style tokens in URLs,
or API keys leaked into model outputs. Users can extend the blacklist.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# Conservative defaults. Match by suffix — `mail.google.com` matches `google.com`
# only when explicitly listed; more specific hostnames take precedence.
_DEFAULT_BLACKLIST: frozenset[str] = frozenset(
    {
        # banking
        "chase.com", "bankofamerica.com", "wellsfargo.com", "citi.com",
        "icbc.com.cn", "ccb.com", "abchina.com", "boc.cn", "cmbchina.com",
        "alipay.com", "paypal.com", "stripe.com",
        # webmail
        "mail.google.com", "outlook.live.com", "outlook.office.com",
        "mail.yahoo.com", "mail.qq.com", "mail.163.com", "protonmail.com",
        "proton.me", "exmail.qq.com", "icloud.com",
        # health
        "mychart.com", "patientportal.com", "kp.org",
        # private messaging / social DMs
        "web.whatsapp.com", "telegram.org", "web.telegram.org",
        "messenger.com", "discord.com", "discordapp.com",
        "twitter.com", "x.com", "instagram.com",
        # collab tools (often hold private docs)
        "notion.so", "slack.com",
        # dev secrets
        "1password.com", "lastpass.com", "bitwarden.com",
    }
)


# Query-string keys that frequently carry credentials/session material.
# Stripped from URLs before they hit the trace table.
_SENSITIVE_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "access_token", "id_token", "refresh_token", "auth_token",
        "code", "token", "session", "session_id", "sessionid",
        "api_key", "apikey", "key", "secret", "client_secret",
        "password", "passwd", "pwd",
        "state", "nonce",
        "sig", "signature",
    }
)


# In-text secret patterns — best-effort scrubbing for episode summaries and
# trace text. Compiled once into a single alternation so `scrub_secrets` makes
# one regex pass instead of N. Covers common provider key shapes; not
# exhaustive.
#
# Generic api_key/password/token pattern: bound the value to {8,64} so a benign
# title like ``secret=MyProjectName`` doesn't eat the rest of the line, and
# stop before whitespace/quote/path-separator boundaries.
_SECRET_PATTERN = re.compile(
    "|".join((
        r"sk-ant-[A-Za-z0-9_\-]{20,}",                       # Anthropic — first, more specific
        r"sk-[A-Za-z0-9_\-]{20,}",                            # OpenAI / generic sk-
        r"AIza[0-9A-Za-z_\-]{35}",                            # Google
        r"AKIA[0-9A-Z]{16}",                                  # AWS access key
        r"ghp_[A-Za-z0-9]{36,}",                              # GitHub PAT
        r"github_pat_[A-Za-z0-9_]{20,}",                      # GitHub fine-grained
        r"xox[abprs]-[A-Za-z0-9\-]{10,}",                     # Slack
        r"Bearer\s+[A-Za-z0-9._\-]{20,}",                     # OAuth bearer
        # Generic key-like assignment, bounded length + end before whitespace/quote
        r"\b(?:api[_-]?key|secret|password|passwd|token)"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,64}(?=[\s\"'`]|$)",
    )),
    re.IGNORECASE,
)


def is_blocked(url: str, extra_blacklist: frozenset[str] | None = None) -> bool:
    """Return True if the URL's host (or any parent suffix) is blocked.

    Returns False on parse failure or empty host — callers that want stronger
    guarantees should pre-validate. (We don't fail-closed because the trace
    callback fires on every navigation including ``about:blank``.)
    """
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    if not host:
        return False
    # Avoid the unconditional set-union allocation in the hot path —
    # extra_blacklist is None for ~all calls.
    blacklist = (
        _DEFAULT_BLACKLIST | extra_blacklist if extra_blacklist
        else _DEFAULT_BLACKLIST
    )
    parts = host.split(".")
    for i in range(len(parts)):
        if ".".join(parts[i:]) in blacklist:
            return True
    return False


def redact(url: str) -> str:
    """Return a privacy-preserving placeholder for blocked URLs."""
    try:
        host = urlparse(url).hostname or "?"
    except Exception:
        host = "?"
    return f"[redacted:{host}]"


def strip_sensitive_params(url: str) -> str:
    """Remove credential-bearing query params (and the URL fragment) from a URL.

    Returns the original string unchanged on parse failure. Preserves param
    order for keys that survive the filter.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.query and not parsed.fragment:
        return url
    kept = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _SENSITIVE_QUERY_KEYS
    ]
    new_query = urlencode(kept)
    return urlunparse(parsed._replace(query=new_query, fragment=""))


def scrub_secrets(text: str | None) -> str | None:
    """Mask common API-key shapes in a free-text string.

    Pass-through for ``None`` / empty strings. One regex pass over the input.
    """
    if not text:
        return text
    return _SECRET_PATTERN.sub("[redacted-secret]", text)

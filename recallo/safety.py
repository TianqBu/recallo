"""Domain blacklist for sensitive sites that should never be recorded.

Recallo is local-first; this list exists so even local storage doesn't capture
banking, webmail, or health-portal content. Users can extend it.
"""

from __future__ import annotations

from urllib.parse import urlparse


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
        # health
        "mychart.com", "patientportal.com", "kp.org",
        # private messaging
        "web.whatsapp.com", "telegram.org", "web.telegram.org",
        "messenger.com", "discord.com",
        # dev secrets
        "1password.com", "lastpass.com", "bitwarden.com",
    }
)


def is_blocked(url: str, extra_blacklist: frozenset[str] | None = None) -> bool:
    """Return True if the URL's host (or any parent suffix) is blocked."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    if not host:
        return False
    blacklist = _DEFAULT_BLACKLIST | (extra_blacklist or frozenset())
    parts = host.split(".")
    for i in range(len(parts) - 1):
        if ".".join(parts[i:]) in blacklist:
            return True
    return host in blacklist


def redact(url: str) -> str:
    """Return a privacy-preserving placeholder for blocked URLs."""
    try:
        host = urlparse(url).hostname or "?"
    except Exception:
        host = "?"
    return f"[redacted:{host}]"

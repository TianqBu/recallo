from recallo.safety import is_blocked, redact


def test_blocks_exact_host():
    assert is_blocked("https://chase.com/login")


def test_blocks_subdomain_via_suffix():
    # cmbchina.com is in the default blacklist; subdomain should also be blocked
    assert is_blocked("https://retail.cmbchina.com/account")


def test_does_not_block_unrelated_substring():
    # `chase.com.evil.example` shares the chars but the host suffix is example
    assert not is_blocked("https://chase.com.evil.example/x")


def test_allows_arxiv_and_github():
    assert not is_blocked("https://arxiv.org/abs/2310.11511")
    assert not is_blocked("https://github.com/recallo/recallo")


def test_handles_malformed_url():
    assert not is_blocked("")
    assert not is_blocked("not a url")
    assert not is_blocked(None)  # type: ignore[arg-type]


def test_redact_returns_redacted_marker():
    out = redact("https://chase.com/account/summary")
    assert out.startswith("[redacted:")
    assert "chase.com" in out


def test_extra_blacklist_extends_defaults():
    assert is_blocked("https://internal.corp", frozenset({"corp"}))
    assert not is_blocked("https://internal.corp")

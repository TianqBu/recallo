from recallo.safety import is_blocked, redact, scrub_secrets, strip_sensitive_params


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


def test_blocks_expanded_categories():
    # Social DMs / collab tools / private chat — newly added in safety.py
    assert is_blocked("https://twitter.com/messages")
    assert is_blocked("https://x.com/messages/123")
    assert is_blocked("https://www.notion.so/private-page")
    assert is_blocked("https://workspace.slack.com/archives/C123")
    assert is_blocked("https://discordapp.com/channels/@me")
    assert is_blocked("https://account.proton.me/u/0/inbox")


def test_strip_sensitive_params_removes_oauth_tokens():
    url = (
        "https://example.com/cb?code=abc&state=xyz&access_token=secret"
        "&kept=ok&id_token=jwt#fragment"
    )
    out = strip_sensitive_params(url)
    assert "code=" not in out
    assert "state=" not in out
    assert "access_token" not in out
    assert "id_token" not in out
    assert "secret" not in out
    assert "kept=ok" in out
    assert "#fragment" not in out


def test_strip_sensitive_params_passthrough():
    assert strip_sensitive_params("") == ""
    assert strip_sensitive_params("https://arxiv.org/abs/2310.11511") == \
        "https://arxiv.org/abs/2310.11511"


def test_scrub_secrets_masks_known_shapes():
    text = (
        "OPENAI_API_KEY=sk-abc123def456ghi789jklmnopqrstuv "
        "tok=ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
        "Authorization: Bearer eyJabcdefghijklmnopqrstuvwxyz "
        "ant=sk-ant-aaaaaaaaaaaaaaaaaaaaaa"
    )
    out = scrub_secrets(text)
    assert "sk-abc123" not in out
    assert "ghp_" not in out
    assert "eyJabcdef" not in out
    assert "sk-ant-aaaa" not in out
    assert "[redacted-secret]" in out


def test_scrub_secrets_passthrough():
    assert scrub_secrets("") == ""
    assert scrub_secrets(None) is None
    assert scrub_secrets("nothing sensitive here") == "nothing sensitive here"

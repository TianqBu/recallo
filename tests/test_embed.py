from recallo.embed import EMBEDDING_DIM, OpenAIEmbedder, StubEmbedder, get_default_embedder


def test_stub_embedder_dim_default():
    e = StubEmbedder()
    v = e.embed("hello")
    assert e.dim == EMBEDDING_DIM
    assert len(v) == EMBEDDING_DIM
    assert all(-1.0 <= x <= 1.0 for x in v)


def test_stub_embedder_is_deterministic():
    e = StubEmbedder()
    a = e.embed("self-rag")
    b = e.embed("self-rag")
    assert a == b


def test_stub_embedder_distinguishes_inputs():
    e = StubEmbedder()
    a = e.embed("self-rag retrieval")
    b = e.embed("attention is all you need")
    assert a != b
    diff = sum(1 for x, y in zip(a, b) if abs(x - y) > 1e-6)
    assert diff > EMBEDDING_DIM // 2  # at least half the dims differ


def test_stub_embedder_custom_dim():
    e = StubEmbedder(dim=8)
    assert len(e.embed("x")) == 8


def test_openai_embedder_dim_for_known_models():
    assert OpenAIEmbedder("text-embedding-3-small").dim == 1536
    assert OpenAIEmbedder("text-embedding-3-large").dim == 3072


def test_get_default_embedder_returns_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_default_embedder() is None


def test_get_default_embedder_returns_openai_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    e = get_default_embedder()
    assert isinstance(e, OpenAIEmbedder)

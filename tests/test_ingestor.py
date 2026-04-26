from recallo.ingestor import _looks_like_arxiv


def test_arxiv_id_detection():
    assert _looks_like_arxiv("arxiv:2310.11511") == "2310.11511"
    assert _looks_like_arxiv("https://arxiv.org/abs/2310.11511") == "2310.11511"
    assert _looks_like_arxiv("https://arxiv.org/pdf/2310.11511v3.pdf") == "2310.11511"
    assert _looks_like_arxiv("https://arxiv.org/abs/2503.12345") == "2503.12345"


def test_arxiv_id_rejects_non_matches():
    assert _looks_like_arxiv("https://example.com/whatever") is None
    assert _looks_like_arxiv("https://arxiv.org/list/cs.CL") is None
    assert _looks_like_arxiv("12345") is None

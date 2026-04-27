"""Embedding providers.

M2 default: OpenAI text-embedding-3-small (1536 dim). The vec0 schema in
``schema.sql`` is locked to 1536 floats; if you swap the embedder for one
with a different dimension, drop ``fact_vec`` and re-create the database
under a new path.
"""

from __future__ import annotations

import hashlib
import os
import struct
from typing import Protocol, runtime_checkable


EMBEDDING_DIM = 1536


@runtime_checkable
class Embedder(Protocol):
    @property
    def dim(self) -> int: ...
    def embed(self, text: str) -> list[float]: ...


class OpenAIEmbedder:
    """Calls ``openai.embeddings.create``. Reads ``OPENAI_API_KEY`` from env."""

    def __init__(self, model: str = "text-embedding-3-small") -> None:
        self.model = model
        # text-embedding-3-small / ada-002 → 1536; text-embedding-3-large → 3072.
        # M2 schema is hard-pinned at 1536, so we error early if a non-1536 model
        # is requested without explicit support.
        if "large" in model:
            self._dim = 3072
        else:
            self._dim = 1536

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        from openai import OpenAI  # deferred import — adds ~15MB of types
        client = OpenAI()
        # OpenAI rejects empty / whitespace-only strings; substitute a sentinel.
        if not text or not text.strip():
            text = "[empty]"
        resp = client.embeddings.create(model=self.model, input=text)
        return list(resp.data[0].embedding)


class StubEmbedder:
    """Deterministic hash-based embedder. Useful for tests; not semantic."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, text: str) -> list[float]:
        out: list[float] = []
        seed = 0
        while len(out) < self._dim:
            h = hashlib.sha512(f"{seed}:{text}".encode("utf-8")).digest()
            for i in range(0, len(h) - 3, 4):
                if len(out) >= self._dim:
                    break
                v = struct.unpack("<i", h[i:i + 4])[0]
                out.append(v / 2_147_483_648.0)
            seed += 1
        return out[: self._dim]


def get_default_embedder() -> Embedder | None:
    """Pick an embedder based on env. ``None`` if no provider configured."""
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIEmbedder()
    return None

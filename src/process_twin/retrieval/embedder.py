"""Embedding + reranking behind a tiny protocol (brief §7.4, §2).

fastembed (ONNX) instead of sentence-transformers: BGE models on CPU with no torch
install and no per-embed API cost — the whole point of choosing BGE for a laptop-scale
project (docs/architecture.md, phase 1). Imports are lazy so unit tests and CI never
pay the model-download cost.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    """BGE dense embeddings via fastembed (downloads the model on first use, ~130MB)."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding  # lazy: see module docstring

        self._model = TextEmbedding(model_name=model_name)
        self.model_name = model_name
        self.dim = len(next(iter(self._model.embed(["dimension probe"]))))

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


class HashingEmbedder:
    """TEST-ONLY deterministic embedder: character-trigram hashing, L2-normalized.

    NOT semantic — it measures lexical overlap. It exists so retrieval *mechanics*
    (indexing, search, rerank plumbing, k-limits) are unit-testable offline with zero
    model downloads. Semantic quality is measured only by `make probe` against the
    real corpus with real BGE models. Never wire this into production paths.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = f"  {text.lower()}  "
        for i in range(len(t) - 2):
            tri = t[i : i + 3]
            slot = int.from_bytes(hashlib.blake2s(tri.encode(), digest_size=4).digest(), "big")
            vec[slot % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class Reranker:
    """Cross-encoder wrapper. score(query, texts) -> relevance per text (higher=better).

    Also reused by the phase-4 citation validator: (decision text, cited clause) must
    score above `citation_relevance_threshold` — same model, same code path.
    """

    def __init__(self, model_name: str) -> None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # lazy

        self._model = TextCrossEncoder(model_name=model_name)
        self.model_name = model_name

    def score(self, query: str, texts: list[str]) -> list[float]:
        return list(self._model.rerank(query, texts))


def get_embedder(use_test_embedder: bool = False) -> Embedder:
    from process_twin.config import get_settings

    if use_test_embedder:
        return HashingEmbedder()
    return FastEmbedEmbedder(get_settings().embedding_model)


def get_reranker() -> Reranker | None:
    """None when fastembed (or the model download) is unavailable — retrieval degrades
    to vector order and says so, rather than failing the whole pipeline."""
    from process_twin.config import get_settings

    try:
        return Reranker(get_settings().reranker_model)
    except Exception as exc:  # noqa: BLE001 — degradation point, logged loudly
        print(f"  [warn] reranker unavailable ({exc.__class__.__name__}: {exc}); "
              "falling back to vector order")
        return None

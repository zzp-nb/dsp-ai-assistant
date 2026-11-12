"""Replaceable, dependency-light text embedding.

The v1 implementation is a local hashed TF-IDF vectoriser over Chinese
characters/n-grams and ASCII terms. It requires no external embedding API and
no model download, which keeps Streamlit Community Cloud deployments cheap.

The ``TextEmbedder`` protocol makes a future sentence-transformers or hosted
embedding backend a drop-in replacement.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence

import numpy as np

_ASCII_RE = re.compile(r"[a-z][a-z0-9_+\-\.]{1,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_SPACE_RE = re.compile(r"\s+")


class TextEmbedder(Protocol):
    dim: int
    version: str

    def fit(self, texts: Sequence[str]) -> "TextEmbedder": ...

    def transform(self, texts: Sequence[str]) -> np.ndarray: ...

    def to_state(self) -> dict: ...


def analyze_terms(text: str) -> list[str]:
    """Tokenise mixed Chinese/English DSP text deterministically."""

    normalized = (text or "").lower()
    normalized = _SPACE_RE.sub(" ", normalized)
    terms: list[str] = []
    for run in _CJK_RUN_RE.findall(normalized):
        if len(run) == 1:
            terms.append(run)
            continue
        for size in (2, 3):
            if len(run) < size:
                continue
            terms.extend(run[index : index + size] for index in range(len(run) - size + 1))
    terms.extend(_ASCII_RE.findall(normalized))
    return terms


class HashingTfidfEmbedder:
    version = "hash-tfidf-v1"

    def __init__(self, dim: int = 2048):
        if dim < 256:
            raise ValueError("Embedding dimension is too small.")
        self.dim = int(dim)
        self.idf = np.ones(self.dim, dtype=np.float32)
        self._fitted = False

    @staticmethod
    def _bucket(term: str, dim: int) -> int:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "little") % dim

    def _counts(self, text: str) -> dict[int, float]:
        counts: dict[int, float] = {}
        for term in analyze_terms(text):
            bucket = self._bucket(term, self.dim)
            counts[bucket] = counts.get(bucket, 0.0) + 1.0
        return counts

    def fit(self, texts: Sequence[str]) -> "HashingTfidfEmbedder":
        document_frequency = np.zeros(self.dim, dtype=np.float32)
        for text in texts:
            for bucket in self._counts(text):
                document_frequency[bucket] += 1.0
        count = max(1, len(texts))
        self.idf = (np.log((1.0 + count) / (1.0 + document_frequency)) + 1.0).astype(np.float32)
        self._fitted = True
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts = self._counts(text)
            for bucket, value in counts.items():
                matrix[row, bucket] = (1.0 + math.log(value)) * float(self.idf[bucket])
            norm = float(np.linalg.norm(matrix[row]))
            if norm > 0:
                matrix[row] /= norm
        return matrix

    def to_state(self) -> dict:
        return {
            "version": self.version,
            "dim": self.dim,
            "idf": self.idf.tolist(),
            "fitted": self._fitted,
        }

    @classmethod
    def from_state(cls, state: dict) -> "HashingTfidfEmbedder":
        embedder = cls(dim=int(state.get("dim", 2048)))
        idf = np.asarray(state.get("idf", []), dtype=np.float32)
        if idf.shape[0] == embedder.dim:
            embedder.idf = idf
        embedder._fitted = bool(state.get("fitted", True))
        return embedder


def get_embedder(provider: str = "hash") -> TextEmbedder:
    """Factory for the replaceable embedding layer."""

    provider = (provider or "hash").strip().lower()
    if provider in {"hash", "local", "tfidf"}:
        return HashingTfidfEmbedder()
    raise ValueError(
        f"未知的 Embedding provider：{provider}。当前版本支持本地 hash TF-IDF；"
        "接入外部模型时请实现 TextEmbedder 协议。"
    )

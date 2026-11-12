"""Hybrid BM25 + local TF-IDF retrieval over parsed course materials."""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from core.database import Database
from core.document_loader import (
    Chunk,
    DocumentLoadError,
    chunk_document,
    file_sha256,
    list_material_files,
    load_document,
)
from core.embedding import HashingTfidfEmbedder, analyze_terms

INDEX_VERSION = 1


@dataclass
class RetrievalHit:
    chunk: Chunk
    score: float
    vector_score: float
    keyword_score: float

    @property
    def citation(self) -> dict[str, Any]:
        item = self.chunk.citation
        item["score"] = round(self.score, 4)
        item["snippet"] = self.chunk.text[:220]
        return item


@dataclass
class BuildReport:
    ok: bool
    chunk_count: int
    material_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    indexed_at: str = ""


@dataclass
class _BM25Stats:
    df: dict[str, int]
    doc_len: list[int]
    avgdl: float
    k1: float = 1.5
    b: float = 0.75


def _atomic_write_text(path: Path, content: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8")
    os.replace(temp, path)


def _build_bm25(chunks: list[Chunk]) -> _BM25Stats:
    df: dict[str, int] = {}
    doc_len: list[int] = []
    for chunk in chunks:
        terms = analyze_terms(chunk.text)
        doc_len.append(len(terms))
        for term in set(terms):
            df[term] = df.get(term, 0) + 1
    avgdl = (sum(doc_len) / len(doc_len)) if doc_len else 0.0
    return _BM25Stats(df=df, doc_len=doc_len, avgdl=avgdl)


def build_index(
    materials_dir: str | Path,
    vector_dir: str | Path,
    database: Database,
    *,
    max_chars: int = 700,
    overlap: int = 80,
) -> BuildReport:
    materials_dir = Path(materials_dir)
    vector_dir = Path(vector_dir)
    vector_dir.mkdir(parents=True, exist_ok=True)
    files = list_material_files(materials_dir)
    errors: list[str] = []
    warnings: list[str] = []
    chunks: list[Chunk] = []
    successful: set[str] = set()
    started = time.monotonic()

    for path in files:
        try:
            file_hash = file_sha256(path)
            document = load_document(path)
            doc_chunks = chunk_document(document, max_chars=max_chars, overlap=overlap)
            chunks.extend(doc_chunks)
            successful.add(path.name)
            database.upsert_material(
                {
                    "source_name": path.name,
                    "file_path": str(path.resolve()),
                    "file_hash": file_hash,
                    "doc_type": document.doc_type,
                    "size_bytes": path.stat().st_size,
                    "page_count": len(document.pages),
                    "chunk_count": len(doc_chunks),
                    "image_page_count": len(document.image_only_pages),
                    "ocr_used": 1 if document.ocr_used else 0,
                    "status": "ready" if doc_chunks else "empty",
                    "error": None if doc_chunks else "未提取到可用文字",
                    "indexed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            )
            warnings.extend(f"{path.name}：{note}" for note in document.notes)
            if not doc_chunks:
                errors.append(f"{path.name}：未提取到可用文字（可能是图片/扫描件）")
        except (DocumentLoadError, OSError) as exc:
            errors.append(f"{path.name}：{exc}")
            database.upsert_material(
                {
                    "source_name": path.name,
                    "file_path": str(path.resolve()),
                    "file_hash": "",
                    "doc_type": path.suffix.lower().lstrip("."),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                    "page_count": 0,
                    "chunk_count": 0,
                    "image_page_count": 0,
                    "ocr_used": 0,
                    "status": "error",
                    "error": str(exc)[:400],
                    "indexed_at": None,
                }
            )
        except Exception as exc:
            errors.append(f"{path.name}：解析失败（{type(exc).__name__}）")
            database.upsert_material(
                {
                    "source_name": path.name,
                    "file_path": str(path.resolve()),
                    "file_hash": "",
                    "doc_type": path.suffix.lower().lstrip("."),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                    "page_count": 0,
                    "chunk_count": 0,
                    "image_page_count": 0,
                    "ocr_used": 0,
                    "status": "error",
                    "error": str(exc)[:400],
                    "indexed_at": None,
                }
            )

    for material in database.list_materials():
        if material["source_name"] not in {path.name for path in files}:
            database.delete_material(material["source_name"])

    embedder = HashingTfidfEmbedder()
    texts = [chunk.text for chunk in chunks]
    if texts:
        embedder.fit(texts)
        matrix = embedder.transform(texts)
    else:
        embedder.fit([""])
        matrix = np.zeros((0, embedder.dim), dtype=np.float32)

    bm25 = _build_bm25(chunks)
    indexed_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = {
        "index_version": INDEX_VERSION,
        "embedding_version": embedder.version,
        "created_at": indexed_at,
        "source_dir": str(materials_dir.resolve()),
        "material_count": len(files),
        "chunk_count": len(chunks),
        "build_seconds": round(time.monotonic() - started, 2),
        "errors": errors,
        "warnings": warnings,
    }

    chunks_path = vector_dir / "chunks.jsonl"
    _atomic_write_text(chunks_path, "\n".join(json.dumps(chunk.to_dict(), ensure_ascii=False) for chunk in chunks))
    np.savez_compressed(vector_dir / "vectors.npz", matrix=matrix, idf=embedder.idf)
    _atomic_write_text(
        vector_dir / "bm25.json",
        json.dumps({"df": bm25.df, "doc_len": bm25.doc_len, "avgdl": bm25.avgdl}, ensure_ascii=False),
    )
    _atomic_write_text(vector_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return BuildReport(
        ok=not errors,
        chunk_count=len(chunks),
        material_count=len(files),
        errors=errors,
        warnings=warnings,
        indexed_at=indexed_at,
    )


class RAGEngine:
    def __init__(self, vector_dir: str | Path, *, min_score: float = 0.12):
        self.vector_dir = Path(vector_dir)
        self.min_score = max(0.0, float(min_score))
        self.chunks: list[Chunk] = []
        self.matrix = np.zeros((0, 2048), dtype=np.float32)
        self.embedder = HashingTfidfEmbedder()
        self.bm25 = _BM25Stats(df={}, doc_len=[], avgdl=0.0)
        self.manifest: dict[str, Any] = {}
        self._signature: tuple[int, int] | None = None
        self._doc_term_counts: list[dict[str, int]] = []

    @property
    def ready(self) -> bool:
        return bool(self.chunks) and self.matrix.shape[0] == len(self.chunks)

    def _manifest_signature(self) -> tuple[int, int] | None:
        path = self.vector_dir / "manifest.json"
        if not path.exists():
            return None
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size

    def refresh_if_changed(self) -> None:
        signature = self._manifest_signature()
        if signature is None:
            self._clear()
            return
        if signature != self._signature:
            self.load()

    def _clear(self) -> None:
        self.chunks = []
        self.matrix = np.zeros((0, self.embedder.dim), dtype=np.float32)
        self.manifest = {}
        self.bm25 = _BM25Stats(df={}, doc_len=[], avgdl=0.0)
        self._doc_term_counts = []
        self._signature = None

    def load(self) -> "RAGEngine":
        manifest_path = self.vector_dir / "manifest.json"
        chunks_path = self.vector_dir / "chunks.jsonl"
        vectors_path = self.vector_dir / "vectors.npz"
        bm25_path = self.vector_dir / "bm25.json"
        if not all(path.exists() for path in (manifest_path, vectors_path, bm25_path)):
            self._clear()
            return self
        try:
            self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            chunks: list[Chunk] = []
            if chunks_path.exists():
                for line in chunks_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        chunks.append(Chunk.from_dict(json.loads(line)))
            with np.load(vectors_path, allow_pickle=False) as data:
                matrix = np.asarray(data["matrix"], dtype=np.float32)
                idf = np.asarray(data["idf"], dtype=np.float32)
            bm25_data = json.loads(bm25_path.read_text(encoding="utf-8"))
            if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
                raise ValueError("索引向量与文本块数量不一致")
            embedder = HashingTfidfEmbedder(dim=int(idf.shape[0]))
            embedder.idf = idf
            embedder._fitted = True
            self.embedder = embedder
            self.chunks = chunks
            self.matrix = matrix
            self.bm25 = _BM25Stats(
                df={str(k): int(v) for k, v in bm25_data.get("df", {}).items()},
                doc_len=[int(value) for value in bm25_data.get("doc_len", [])],
                avgdl=float(bm25_data.get("avgdl", 0.0)),
            )
            self._doc_term_counts = [self._term_counts(chunk.text) for chunk in chunks]
            self._signature = self._manifest_signature()
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            self._clear()
        return self

    @staticmethod
    def _term_counts(text: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for term in analyze_terms(text):
            counts[term] = counts.get(term, 0) + 1
        return counts

    def _keyword_scores(self, query: str) -> np.ndarray:
        counts = self._term_counts(query)
        scores = np.zeros(len(self.chunks), dtype=np.float32)
        if not counts or not self.bm25.doc_len:
            return scores
        total_docs = len(self.chunks)
        avgdl = self.bm25.avgdl or 1.0
        for index, doc_counts in enumerate(self._doc_term_counts):
            length = self.bm25.doc_len[index] if index < len(self.bm25.doc_len) else sum(doc_counts.values())
            score = 0.0
            for term, query_tf in counts.items():
                tf = doc_counts.get(term, 0)
                if not tf:
                    continue
                df = self.bm25.df.get(term, 0)
                idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
                denominator = tf + self.bm25.k1 * (1.0 - self.bm25.b + self.bm25.b * length / avgdl)
                score += idf * (tf * (self.bm25.k1 + 1.0) / denominator) * min(query_tf, 3)
            scores[index] = score
        return scores

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        chapter: str | None = None,
        min_score: float | None = None,
    ) -> list[RetrievalHit]:
        self.refresh_if_changed()
        query = (query or "").strip()
        if not query or not self.chunks:
            return []
        query_vector = self.embedder.transform([query])[0]
        vector_scores = self.matrix @ query_vector
        keyword_scores = self._keyword_scores(query)

        if keyword_scores.size and float(keyword_scores.max()) > 0:
            keyword_normalized = keyword_scores / float(keyword_scores.max())
        else:
            keyword_normalized = np.zeros_like(keyword_scores)

        combined = 0.58 * vector_scores + 0.42 * keyword_normalized
        priority = np.asarray([chunk.priority for chunk in self.chunks], dtype=np.float32)
        combined = combined * (1.0 + 0.025 * (priority - 1.0))

        results: list[RetrievalHit] = []
        threshold = self.min_score if min_score is None else max(0.0, float(min_score))
        seen_texts: set[str] = set()
        for index in np.argsort(combined)[::-1]:
            score = float(combined[index])
            if score < threshold:
                break
            chunk = self.chunks[int(index)]
            if chapter and chapter.strip() and chapter.strip() not in chunk.chapter:
                continue
            fingerprint = chunk.text[:160]
            if fingerprint in seen_texts:
                continue
            seen_texts.add(fingerprint)
            results.append(
                RetrievalHit(
                    chunk=chunk,
                    score=round(score, 4),
                    vector_score=round(float(vector_scores[index]), 4),
                    keyword_score=round(float(keyword_normalized[index]), 4),
                )
            )
            if len(results) >= max(1, top_k):
                break
        return results

    def chapters(self) -> list[str]:
        self.refresh_if_changed()
        values = {chunk.chapter.strip() for chunk in self.chunks if chunk.chapter.strip()}
        return sorted(values)

    def materials(self) -> list[dict[str, Any]]:
        self.refresh_if_changed()
        counts: dict[str, int] = {}
        for chunk in self.chunks:
            counts[chunk.source_name] = counts.get(chunk.source_name, 0) + 1
        return [
            {"source_name": name, "chunks": count}
            for name, count in sorted(counts.items())
        ]

    def stats(self) -> dict[str, Any]:
        self.refresh_if_changed()
        return {
            "ready": self.ready,
            "chunks": len(self.chunks),
            "materials": len({chunk.source_name for chunk in self.chunks}),
            "created_at": self.manifest.get("created_at", ""),
            "build_seconds": self.manifest.get("build_seconds", 0),
        }


_ENGINE: RAGEngine | None = None
_ENGINE_KEY: tuple[str, float] | None = None


def get_rag_engine(vector_dir: str | Path, min_score: float = 0.12) -> RAGEngine:
    """Process-local singleton; reloads itself when the index manifest changes."""

    global _ENGINE, _ENGINE_KEY
    key = (str(Path(vector_dir).resolve()), float(min_score))
    if _ENGINE is None or _ENGINE_KEY != key:
        _ENGINE = RAGEngine(vector_dir, min_score=min_score).load()
        _ENGINE_KEY = key
    else:
        _ENGINE.refresh_if_changed()
    return _ENGINE


def invalidate_rag_engine() -> None:
    global _ENGINE, _ENGINE_KEY
    _ENGINE = None
    _ENGINE_KEY = None


def build_context(hits: list[RetrievalHit], *, max_chars: int = 5600) -> tuple[str, list[dict[str, Any]]]:
    blocks: list[str] = []
    citations: list[dict[str, Any]] = []
    used = 0
    for index, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        header = (
            f"[资料{index}] 来源：《{chunk.source_name}》 | {chunk.page_label}"
            f" | 章节：{chunk.chapter or '未标注'}"
        )
        body = chunk.text
        remaining = max_chars - used
        if remaining <= 120:
            break
        body = body[: remaining - len(header) - 20]
        block = f"{header}\n{body}"
        blocks.append(block)
        citation = hit.citation
        citation["marker"] = f"资料{index}"
        citations.append(citation)
        used += len(block)
    return "\n\n".join(blocks), citations


def manifest_for_ui(vector_dir: str | Path) -> dict[str, Any]:
    path = Path(vector_dir) / "manifest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def report_to_dict(report: BuildReport) -> dict[str, Any]:
    return asdict(report)

"""Replaceable material-storage interface.

v1 ships a local-directory backend. A deployment with S3/R2/Supabase Storage
can implement the same small interface without touching parsing or retrieval.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.document_loader import SUPPORTED_EXTENSIONS, list_material_files


class StorageError(Exception):
    pass


class MaterialStorage(Protocol):
    def list_files(self) -> list[Path]: ...

    def save(self, filename: str, content: bytes, *, overwrite: bool = False) -> Path: ...

    def write_sidecar(self, source_name: str, text: str) -> Path: ...

    def delete(self, filename: str) -> None: ...

    def resolve(self, filename: str) -> Path: ...


class LocalMaterialStorage:
    """Store files on the host filesystem (persistent volume or ephemeral disk)."""

    def __init__(self, root: str | Path, *, max_size_mb: int = 30):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.max_size_mb = max_size_mb

    def list_files(self) -> list[Path]:
        return list_material_files(self.root)

    def _safe_name(self, filename: str) -> str:
        name = Path(filename).name
        if not name or name.startswith(".") or name != filename.strip():
            raise StorageError("文件名不合法。")
        if Path(name).suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise StorageError("只支持 PDF、PPTX、TXT、MD。")
        return name

    def resolve(self, filename: str) -> Path:
        return self.root / self._safe_name(filename)

    def save(self, filename: str, content: bytes, *, overwrite: bool = False) -> Path:
        name = self._safe_name(filename)
        if len(content) > self.max_size_mb * 1024 * 1024:
            raise StorageError(f"文件超过 {self.max_size_mb} MB 限制。")
        target = self.root / name
        if target.exists() and not overwrite:
            raise StorageError("同名文件已存在；如需替换请勾选覆盖。")
        target.write_bytes(content)
        return target

    def write_sidecar(self, source_name: str, text: str) -> Path:
        name = self._safe_name(source_name)
        if len(text.encode("utf-8")) > 2 * 1024 * 1024:
            raise StorageError("补录文本不能超过 2 MB。")
        target = self.root / f"{name}.ocr.txt"
        target.write_text(text, encoding="utf-8")
        return target

    def delete(self, filename: str) -> None:
        target = self.resolve(filename)
        if target.exists():
            target.unlink()


def get_material_storage(root: str | Path, *, max_size_mb: int = 30) -> MaterialStorage:
    """Factory; add new cloud backends here and keep the UI unchanged."""

    return LocalMaterialStorage(root, max_size_mb=max_size_mb)

"""Course-material parsing and chunking.

Supported in v1:
- PDF text via PyMuPDF, with page numbers and PDF outline chapter mapping.
- PPTX text via python-pptx, with slide numbers and speaker notes.
- Plain text / Markdown supplements.

PPT images, screenshots, scanned PDF pages and equations stored as pictures are
NOT silently treated as recognised. A transparent sidecar file can supply the
text without changing the original material. See ``docs/material_import.md``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".txt", ".md"}
MAX_PDF_PAGES = 800
MAX_PPT_SLIDES = 400
MAX_TEXT_CHARS_PER_DOCUMENT = 3_000_000

CHAPTER_RE = re.compile(
    r"(第\s*[一二三四五六七八九十百零〇\d]+\s*[章节][^\n]{0,40}|Chapter\s+\d+[^\n]{0,50})",
    re.IGNORECASE,
)
PAGE_MARKER_RE = re.compile(r"\[\[\s*(?:PAGE|SLIDE)\s+(\d+)\s*\]\]", re.IGNORECASE)
WHITESPACE_RE = re.compile(r"[ \t\u00a0]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


class DocumentLoadError(Exception):
    pass


@dataclass
class ParsedPage:
    number: int
    page_kind: str  # "page" or "slide"
    text: str
    title: str = ""
    chapter: str = ""
    image_count: int = 0
    ocr_applied: bool = False

    @property
    def label(self) -> str:
        return f"第 {self.number} 页" if self.page_kind == "page" else f"幻灯片 {self.number}"


@dataclass
class ParsedDocument:
    source_name: str
    path: Path
    doc_type: str
    pages: list[ParsedPage]
    title: str = ""
    image_only_pages: list[int] = field(default_factory=list)
    ocr_used: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    id: str
    source_name: str
    doc_type: str
    page: int
    page_label: str
    chapter: str
    section: str
    text: str
    priority: float
    part: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "doc_type": self.doc_type,
            "page": self.page,
            "page_label": self.page_label,
            "chapter": self.chapter,
            "section": self.section,
            "text": self.text,
            "priority": self.priority,
            "part": self.part,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Chunk":
        return cls(**{key: data[key] for key in cls.__dataclass_fields__ if key in data})

    @property
    def citation(self) -> dict:
        return {
            "source": self.source_name,
            "location": self.page_label,
            "chapter": self.chapter,
            "doc_type": self.doc_type,
            "page": self.page,
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = WHITESPACE_RE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    cleaned = BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def _detect_chapter(text: str, fallback: str = "") -> str:
    match = CHAPTER_RE.search(text or "")
    if match:
        return match.group(1).strip()
    return fallback.strip()


def _doc_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".pptx":
        return "pptx"
    if suffix in {".txt", ".md"}:
        return "text"
    raise DocumentLoadError(f"不支持的资料格式：{suffix or '无扩展名'}（支持 PDF、PPTX、TXT、MD）")


def _load_sidecar(path: Path) -> dict[int, str]:
    candidates = [
        path.with_name(path.name + ".ocr.txt"),
        path.with_suffix(path.suffix + ".ocr.txt"),
        path.with_suffix(".ocr.txt"),
    ]
    sidecar = next((candidate for candidate in candidates if candidate.exists()), None)
    if sidecar is None:
        return {}
    text = clean_text(sidecar.read_text(encoding="utf-8", errors="replace"))
    if not text:
        return {}
    matches = list(PAGE_MARKER_RE.finditer(text))
    if not matches:
        return {1: text}
    pages: dict[int, str] = {}
    for index, match in enumerate(matches):
        number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = clean_text(text[start:end])
        if content:
            pages[number] = content
    return pages


def _parse_pdf(path: Path, sidecar: dict[int, str]) -> ParsedDocument:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DocumentLoadError("服务端缺少 PyMuPDF，无法解析 PDF。") from exc

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise DocumentLoadError(f"无法打开 PDF：{exc}") from exc

    try:
        if doc.needs_pass:
            raise DocumentLoadError("PDF 已加密，无法解析。请提供未加密版本。")
        if doc.page_count > MAX_PDF_PAGES:
            raise DocumentLoadError(f"PDF 页数过多（{doc.page_count}），当前上限为 {MAX_PDF_PAGES} 页。")

        toc_chapters = _pdf_outline_map(doc)
        pages: list[ParsedPage] = []
        current_chapter = ""
        image_only: list[int] = []
        ocr_used = False
        total_chars = 0
        for index in range(doc.page_count):
            page = doc[index]
            page_number = index + 1
            text = clean_text(page.get_text("text") or "")
            if page_number in toc_chapters:
                current_chapter = toc_chapters[page_number]
            else:
                current_chapter = _detect_chapter(text, current_chapter)
            if page_number in sidecar:
                text = clean_text(f"{text}\n{sidecar[page_number]}") if text else sidecar[page_number]
                ocr_used = True
            image_count = len(page.get_images(full=True))
            if len(text) < 30 and image_count:
                image_only.append(page_number)
            elif len(text) < 30:
                continue
            total_chars += len(text)
            if total_chars > MAX_TEXT_CHARS_PER_DOCUMENT:
                raise DocumentLoadError("PDF 文本量过大，请拆分后再导入。")
            title = _first_heading(page) or f"第 {page_number} 页"
            pages.append(
                ParsedPage(
                    number=page_number,
                    page_kind="page",
                    text=text,
                    title=title,
                    chapter=current_chapter,
                    image_count=image_count,
                    ocr_applied=page_number in sidecar,
                )
            )
        metadata = doc.metadata or {}
        title = str(metadata.get("title") or "").strip() or path.stem
        notes = []
        if image_only:
            notes.append(
                f"{len(image_only)} 页几乎只有图片/扫描内容，未做 OCR；可提供 .ocr.txt 补录文本。"
            )
        return ParsedDocument(
            source_name=path.name,
            path=path,
            doc_type="pdf",
            pages=pages,
            title=title,
            image_only_pages=image_only,
            ocr_used=ocr_used,
            notes=notes,
        )
    finally:
        doc.close()


def _pdf_outline_map(doc: object) -> dict[int, str]:
    try:
        toc = doc.get_toc(simple=True)  # type: ignore[attr-defined]
    except Exception:
        return {}
    mapped: dict[int, str] = {}
    for entry in toc or []:
        if not isinstance(entry, (list, tuple)) or len(entry) < 3:
            continue
        level, title, page = entry[0], str(entry[1]).strip(), entry[2]
        if level <= 2 and title and isinstance(page, int) and page > 0:
            mapped.setdefault(page, _detect_chapter(title, title))
    return mapped


def _first_heading(page: object) -> str:
    try:
        blocks = page.get_text("dict").get("blocks", [])  # type: ignore[attr-defined]
        for block in blocks[:3]:
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(span.get("text", "") for span in spans).strip()
                if text and len(text) <= 80:
                    return text
    except Exception:
        return ""
    return ""


def _shape_text(shape: object) -> list[str]:
    pieces: list[str] = []
    try:
        if getattr(shape, "has_text_frame", False) and shape.text_frame is not None:
            for paragraph in shape.text_frame.paragraphs:
                text = "".join(run.text for run in paragraph.runs).strip()
                if not text:
                    text = (paragraph.text or "").strip()
                if text:
                    pieces.append(text)
        has_table = getattr(shape, "has_table", False)
        if has_table and shape.table is not None:
            for row in shape.table.rows:
                cells = [clean_text(cell.text) for cell in row.cells]
                if any(cells):
                    pieces.append(" | ".join(cells))
        if getattr(shape, "shape_type", None) == 6 and hasattr(shape, "shapes"):  # group
            for child in shape.shapes:
                pieces.extend(_shape_text(child))
    except Exception:
        return pieces
    return pieces


def _parse_pptx(path: Path, sidecar: dict[int, str]) -> ParsedDocument:
    try:
        from pptx import Presentation
    except ImportError as exc:  # pragma: no cover
        raise DocumentLoadError("服务端缺少 python-pptx，无法解析 PPTX。") from exc

    try:
        presentation = Presentation(str(path))
    except Exception as exc:
        raise DocumentLoadError(f"无法打开 PPTX：{exc}") from exc
    slides = list(presentation.slides)
    if len(slides) > MAX_PPT_SLIDES:
        raise DocumentLoadError(f"PPT 页数过多（{len(slides)}），当前上限为 {MAX_PPT_SLIDES} 页。")

    pages: list[ParsedPage] = []
    image_only: list[int] = []
    ocr_used = False
    current_chapter = _detect_chapter(path.stem, "")
    total_chars = 0
    for index, slide in enumerate(slides, start=1):
        parts: list[str] = []
        title = ""
        try:
            if slide.shapes.title is not None and slide.shapes.title.text:
                title = clean_text(slide.shapes.title.text)
                parts.append(title)
        except Exception:
            title = ""
        image_count = 0
        for shape in slide.shapes:
            parts.extend(_shape_text(shape))
            if getattr(shape, "shape_type", None) == 13:  # picture
                image_count += 1
            try:
                if getattr(shape, "has_chart", False):
                    parts.append("[图表数据未提取]")
            except Exception:
                pass
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
                notes = clean_text(slide.notes_slide.notes_text_frame.text)
                if notes:
                    parts.append(f"[讲稿] {notes}")
        except Exception:
            pass
        text = clean_text("\n".join(parts))
        if index in sidecar:
            text = clean_text(f"{text}\n{sidecar[index]}") if text else sidecar[index]
            ocr_used = True
        current_chapter = _detect_chapter(text, current_chapter)
        if len(text) < 15 and image_count:
            image_only.append(index)
            continue
        if len(text) < 15:
            continue
        total_chars += len(text)
        if total_chars > MAX_TEXT_CHARS_PER_DOCUMENT:
            raise DocumentLoadError("PPT 文本量过大，请拆分后再导入。")
        pages.append(
            ParsedPage(
                number=index,
                page_kind="slide",
                text=text,
                title=title or f"幻灯片 {index}",
                chapter=current_chapter,
                image_count=image_count,
                ocr_applied=index in sidecar,
            )
        )
    notes = []
    if image_only:
        notes.append(
            f"{len(image_only)} 张幻灯片只有图片/公式截图，未做 OCR；可提供 .ocr.txt 补录文本。"
        )
    return ParsedDocument(
        source_name=path.name,
        path=path,
        doc_type="pptx",
        pages=pages,
        title=path.stem,
        image_only_pages=image_only,
        ocr_used=ocr_used,
        notes=notes,
    )


def _parse_text(path: Path, sidecar: dict[int, str]) -> ParsedDocument:
    text = clean_text(path.read_text(encoding="utf-8", errors="replace"))
    if sidecar:
        text = clean_text(text + "\n" + "\n".join(sidecar.values()))
    if not text:
        raise DocumentLoadError("文本文件为空。")
    return ParsedDocument(
        source_name=path.name,
        path=path,
        doc_type="text",
        pages=[
            ParsedPage(
                number=1,
                page_kind="page",
                text=text,
                title=path.stem,
                chapter=_detect_chapter(text, path.stem),
            )
        ],
        title=path.stem,
    )


def load_document(path: str | Path) -> ParsedDocument:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise DocumentLoadError(f"文件不存在：{path.name}")
    if path.name.endswith(".ocr.txt"):
        raise DocumentLoadError("OCR 侧车文件不能单独导入，请与同名 PDF/PPTX 放在一起。")
    doc_type = _doc_type_for(path)
    sidecar = _load_sidecar(path)
    if doc_type == "pdf":
        return _parse_pdf(path, sidecar)
    if doc_type == "pptx":
        return _parse_pptx(path, sidecar)
    return _parse_text(path, sidecar)


def list_material_files(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    files = [
        path
        for path in directory.iterdir()
        if path.is_file()
        and not path.name.startswith(".")
        and path.name.lower() not in {"readme.md", "readme.txt"}
        and path.suffix.lower() in SUPPORTED_EXTENSIONS
        and not path.name.endswith(".ocr.txt")
    ]
    return sorted(files, key=lambda item: (item.suffix.lower() != ".pptx", item.name.lower()))


def split_text(text: str, max_chars: int = 700, overlap: int = 80) -> list[str]:
    """Split at paragraph/sentence boundaries with a small character overlap."""

    text = clean_text(text)
    if len(text) <= max_chars:
        return [text] if text else []
    max_chars = max(200, max_chars)
    overlap = max(0, min(overlap, max_chars // 3))
    sentences = re.split(r"(?<=[。！？!?；;])\s*|\n+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            start = 0
            while start < len(sentence):
                chunks.append(sentence[start : start + max_chars].strip())
                start += max_chars - overlap
            continue
        candidate = f"{current}\n{sentence}".strip() if current else sentence
        if len(candidate) > max_chars:
            chunks.append(current.strip())
            tail = current[-overlap:] if overlap and current else ""
            current = f"{tail}\n{sentence}".strip()
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return [chunk for chunk in chunks if chunk]


def chunk_document(document: ParsedDocument, *, max_chars: int = 700, overlap: int = 80) -> list[Chunk]:
    chunks: list[Chunk] = []
    priority = {"pptx": 3.0, "pdf": 1.0, "text": 2.0}.get(document.doc_type, 1.0)
    for page in document.pages:
        parts = split_text(page.text, max_chars=max_chars, overlap=overlap)
        for part_index, part in enumerate(parts):
            chunk_id = hashlib.sha1(
                f"{document.source_name}|{page.number}|{part_index}|{part}".encode("utf-8")
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source_name=document.source_name,
                    doc_type=document.doc_type,
                    page=page.number,
                    page_label=page.label,
                    chapter=page.chapter,
                    section=page.title,
                    text=part,
                    priority=priority,
                    part=part_index,
                )
            )
    return chunks


def iter_chunks(files: Iterable[Path]) -> tuple[list[Chunk], list[ParsedDocument], list[str]]:
    chunks: list[Chunk] = []
    documents: list[ParsedDocument] = []
    errors: list[str] = []
    for path in files:
        try:
            document = load_document(path)
            documents.append(document)
            chunks.extend(chunk_document(document))
        except DocumentLoadError as exc:
            errors.append(f"{path.name}：{exc}")
        except Exception as exc:  # keep one bad file from stopping the import
            errors.append(f"{path.name}：解析失败（{type(exc).__name__}）")
    return chunks, documents, errors

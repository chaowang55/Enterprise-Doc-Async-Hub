from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from docx import Document
from pypdf import PdfReader

from app.config import get_settings


@dataclass(frozen=True)
class Source:
    id: str
    location: str
    text: str


@dataclass(frozen=True)
class SourceDocument:
    sources: tuple[Source, ...]

    @property
    def text(self):
        return "\n".join(source.text for source in self.sources)


def parse_with_sources(path: str) -> SourceDocument:
    source = Path(path)
    limit = get_settings().max_text_chars
    parts = []
    length = 0

    def append(text, location):
        nonlocal length
        length += len(text) + 1
        if length > limit:
            raise ValueError(f"解析文本超过 {limit} 字符，请拆分文件")
        for offset in range(0, len(text), 2000):
            piece = text[offset:offset + 2000]
            if piece.strip():
                parts.append(Source(f"s{len(parts) + 1:05d}",
                                    f"{location} · 字符 {offset + 1}–{offset + len(piece)}", piece))

    if source.suffix == ".txt":
        with source.open(encoding="utf-8-sig") as stream:
            # Bounded read before decoding an entire large file.
            text = stream.read(limit + 1)
        for line, value in enumerate(text.splitlines(), 1):
            append(value, f"文本第 {line} 行")
    elif source.suffix == ".pdf":
        reader = PdfReader(source)
        if reader.is_encrypted:
            raise ValueError("不支持加密 PDF")
        if len(reader.pages) > 1000:
            raise ValueError("PDF 超过 1000 页")
        for page, value in enumerate(reader.pages, 1):
            append(value.extract_text() or "", f"PDF 第 {page} 页")
    elif source.suffix == ".docx":
        with ZipFile(source) as archive:
            if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("DOCX 解压大小超过限制")
        doc = Document(source)
        for index, block in enumerate(doc.iter_inner_content(), 1):
            if hasattr(block, "rows"):
                for row_index, row in enumerate(block.rows, 1):
                    append(" | ".join(cell.text for cell in row.cells),
                           f"DOCX 块 {index} 表格第 {row_index} 行")
            else:
                append(block.text, f"DOCX 块 {index} 段落")
    else:
        raise ValueError("仅支持 UTF-8 TXT、文本 PDF 和 DOCX")
    if not parts:
        raise ValueError("未提取到文本；扫描件需要先进行 OCR")
    return SourceDocument(tuple(parts))


def parse_document(path: str) -> str:
    return parse_with_sources(path).text

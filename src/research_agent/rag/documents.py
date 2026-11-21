"""Load local documents and preserve page or line locations in chunks."""

import os
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path

from research_agent.security import open_authorized

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_TEXT_CHARS = 100_000
MAX_FILES = 24
MAX_CHUNKS = 256


@dataclass(frozen=True)
class Chunk:
    source: str
    location: str
    text: str


@dataclass(frozen=True)
class Corpus:
    chunks: tuple[Chunk, ...]
    issues: tuple[str, ...]


def clean(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def chunk_text(text: str, source: str, *, page: int | None = None) -> list[Chunk]:
    text = clean(text)
    result = []
    start = 0
    while start < len(text):
        end = min(start + 600, len(text))
        if end < len(text):
            boundary = max(text.rfind(" ", start + 400, end), text.rfind("\n", start + 400, end))
            if boundary != -1:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            first = text.count("\n", 0, start) + 1
            last = text.count("\n", 0, end - 1) + 1
            where = f"p. {page}" if page is not None else f"lines {first}–{last}"
            result.append(Chunk(source, where, piece))
        if end == len(text):
            break
        start = end - 90
    return result


def _read_document(root: Path, path: Path, source: str) -> list[Chunk]:
    with open_authorized(root, path) as handle:
        if os.fstat(handle.fileno()).st_size > MAX_FILE_BYTES:
            raise ValueError("file exceeds 12 MiB")
        if path.suffix.lower() != ".pdf":
            with TextIOWrapper(handle, encoding="utf-8-sig") as reader:
                text = reader.read(MAX_TEXT_CHARS + 1)
            if len(text) > MAX_TEXT_CHARS:
                raise ValueError("text exceeds 100000 characters")
            return chunk_text(text, source)
        data = handle.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("file exceeds 12 MiB")
    try:
        import pymupdf
    except ImportError as error:
        raise ValueError("Install research-agent[rag] for PDF extraction") from error
    chunks = []
    size = 0
    try:
        with pymupdf.open(stream=data, filetype="pdf") as pdf:
            if pdf.needs_pass or pdf.page_count > 40:
                raise ValueError("PDF is encrypted or exceeds 40 pages")
            for i, page in enumerate(pdf, start=1):
                text = page.get_text(sort=True)
                size += len(text)
                if size > MAX_TEXT_CHARS:
                    raise ValueError("extracted PDF exceeds 100000 characters")
                chunks.extend(chunk_text(text, source, page=i))
    except (RuntimeError, OSError) as error:
        raise ValueError("PDF extraction failed") from error
    return chunks


def load_corpus(root: Path) -> Corpus:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Document root must be a directory")
    chunks = []
    issues = []
    seen = set()
    for folder, directories, files in os.walk(root):
        current = Path(folder)
        depth = len(current.relative_to(root).parts)
        directories[:] = [
            name for name in sorted(directories)
            if depth < 3 and not name.startswith(".") and not (current / name).is_symlink()
            and not (current / name).is_junction()
        ]
        for name in sorted(files):
            path = current / name
            if name.startswith(".") or path.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            source = path.relative_to(root).as_posix()
            try:
                resolved = path.resolve(strict=True)
                if (not resolved.is_relative_to(root) or not resolved.is_file()
                        or resolved.suffix.lower() != path.suffix.lower()):
                    raise ValueError("path does not point to an authorized document")
                if resolved in seen:
                    continue
                if len(seen) == MAX_FILES:
                    return Corpus(tuple(chunks), (*issues, "Document limit reached (24 files)"))
                seen.add(resolved)
                document_chunks = _read_document(root, resolved, source)
                if not document_chunks:
                    raise ValueError("no extractable text")
                if len(chunks) + len(document_chunks) > MAX_CHUNKS:
                    raise ValueError("document would exceed the 256-chunk corpus limit")
                chunks.extend(document_chunks)
            except (OSError, ValueError, RuntimeError) as error:
                issues.append(f"{source}: {error}")
    return Corpus(tuple(chunks), tuple(issues))

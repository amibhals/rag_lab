from pathlib import Path
from pypdf import PdfReader
from docx import Document
from .config import settings
from .models import Chunk
import re

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

def parse_file(path: Path) -> list[dict]:
    ext = path.suffix.lower()
    pages = []
    if ext == ".pdf":
        reader = PdfReader(str(path))
        for i, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            pages.append({"page": i, "section": None, "text": text})
    elif ext == ".docx":
        doc = Document(str(path))
        current_section = None
        buffer = []
        page_no = 1
        for p in doc.paragraphs:
            txt = p.text.strip()
            if not txt:
                continue
            if p.style and p.style.name and "Heading" in p.style.name:
                if buffer:
                    pages.append({"page": page_no, "section": current_section, "text": "\n".join(buffer)})
                    buffer = []
                current_section = txt
            else:
                buffer.append(txt)
        if buffer:
            pages.append({"page": page_no, "section": current_section, "text": "\n".join(buffer)})
        if not pages:
            pages = [{"page": 1, "section": None, "text": ""}]
    else:
        text = path.read_text(encoding="utf-8", errors="ignore")
        blocks = re.split(r"\n\s*\n", text)
        pages = [{"page": 1, "section": None, "text": "\n\n".join(blocks)}]
    return pages

def chunk_text(text: str, size: int, overlap: int):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + size)
        if end < n:
            boundary = max(text.rfind(". ", start, end), text.rfind("; ", start, end), text.rfind(" ", start, end))
            if boundary > start + int(size * 0.55):
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, end, piece))
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks

def build_chunks(path: Path) -> list[Chunk]:
    pages = parse_file(path)
    all_chunks = []
    counter = 1
    doc_key = re.sub(r"[^A-Za-z0-9]+", "_", path.name).strip("_")
    for item in pages:
        for start, end, piece in chunk_text(item["text"], settings.chunk_size, settings.chunk_overlap):
            cid = f"{doc_key}__c{counter:04d}"
            all_chunks.append(Chunk(
                id=cid, document=path.name, page=item["page"], section=item["section"],
                text=piece, start_char=start, end_char=end, chunk_size=len(piece),
                overlap=settings.chunk_overlap,
                metadata={"extension": path.suffix.lower(), "source_path": str(path), "page": item["page"], "section": item["section"]}
            ))
            counter += 1
    return all_chunks

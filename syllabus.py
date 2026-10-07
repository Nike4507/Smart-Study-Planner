"""syllabus.py — turn an uploaded file or pasted text into a clean list of topics.

Rule from the spec: *never let an upload failure block the planner.*
Every function here returns ``(result, error_message)`` instead of raising,
so the UI can fall back to manual entry.
"""
from __future__ import annotations

import io
import re

# "1.", "2)", "Unit 3:", "Chapter 4 -", "Module II.", "Topic 5:", bullets, etc.
_PREFIX = re.compile(
    r"^\s*(?:[-•*▪●◦>·]+\s*|(?:unit|chapter|module|topic|section|lesson|part)\s+[\w.]+\s*[:\-–—.)]?\s*|\d+(?:\.\d+)*\s*[.):\-–—]\s*)",
    re.IGNORECASE,
)


def extract_text(uploaded) -> tuple[str, str | None]:
    """Read text from a Streamlit UploadedFile (txt / pdf / docx)."""
    name = (getattr(uploaded, "name", "") or "").lower()
    try:
        data = uploaded.getvalue()
        if name.endswith(".txt"):
            return data.decode("utf-8", errors="ignore"), None
        if name.endswith(".pdf"):
            try:
                from pypdf import PdfReader
            except ImportError:
                return "", "PDF support needs `pip install pypdf`. Please paste the topics manually."
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            if not text.strip():
                return "", "No text found in this PDF (it may be scanned). Please paste the topics manually."
            return text, None
        if name.endswith(".docx"):
            try:
                from docx import Document
            except ImportError:
                return "", "DOCX support needs `pip install python-docx`. Please paste the topics manually."
            doc = Document(io.BytesIO(data))
            headings = [p.text for p in doc.paragraphs if p.text.strip() and p.style.name.lower().startswith("heading")]
            lines = headings or [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n".join(lines), None
        return "", "Unsupported file type. Use PDF, DOCX or TXT, or paste the topics manually."
    except Exception as exc:  # noqa: BLE001 — a broken file must never crash the app
        return "", f"Could not read the file ({exc.__class__.__name__}). Please paste the topics manually."


def parse_topics(text: str, max_topics: int = 80) -> list[str]:
    """Normalise raw text into unique, tidy topic names (one per line)."""
    topics: list[str] = []
    seen: set[str] = set()
    for raw in re.split(r"[\r\n]+", text or ""):
        line = _PREFIX.sub("", raw).strip(" \t:-–—.;,")
        if len(line) < 3 or not re.search(r"[A-Za-z]", line):
            continue
        if re.fullmatch(r"(page\s*)?\d+(\s*of\s*\d+)?", line, re.IGNORECASE):   # page numbers
            continue
        if len(line) > 90 or len(line.split()) > 12:                            # paragraph text, not a heading
            continue
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        topics.append(line[:1].upper() + line[1:])
        if len(topics) >= max_topics:
            break
    return topics

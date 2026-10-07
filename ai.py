"""ai.py — reading handwritten notes and building study material from notes or the web.

Material priority used by the app (see learning.py):
    1. the student's own notes / PDFs   -> flashcards + quiz built from them
    2. the topic name searched on the web (needs an Anthropic API key)
    3. the small built-in knowledge base / generic checklist

Everything returns ``(result, error_message)`` and never raises, so a failure here can never
block the planner. Without an API key the app still works: typed/PDF/DOCX/TXT notes are turned
into cards and quizzes with a simple offline extractor; only handwriting and web search need a key.
"""
from __future__ import annotations

import base64
import json
import os
import re

MODEL = os.environ.get("STUDY_PLANNER_MODEL", "claude-sonnet-5-5")
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "gif": "image/gif"}
_OVERRIDE: dict[str, str] = {}      # key typed into the sidebar (kept in memory only, never saved to disk)


# --------------------------------------------------------------------------- #
# API access
# --------------------------------------------------------------------------- #
def set_key(key: str) -> None:
    _OVERRIDE["key"] = key.strip()


def get_key() -> str:
    if _OVERRIDE.get("key"):
        return _OVERRIDE["key"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    try:
        import streamlit as st
        return str(st.secrets.get("ANTHROPIC_API_KEY", ""))
    except Exception:  # noqa: BLE001 — no secrets file is normal
        return ""


def available() -> bool:
    return bool(get_key())


def _ask(content: list, system: str, web: bool = False, max_tokens: int = 4000) -> tuple[str, str | None]:
    try:
        import anthropic
    except ImportError:
        return "", "Install the AI add-on with `pip install anthropic`."
    if not available():
        return "", "No API key set. Add one in the sidebar (Settings) to use this feature."
    try:
        client = anthropic.Anthropic(api_key=get_key())
        kwargs = {"tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]} if web else {}
        msg = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": content}], **kwargs)
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text"), None
    except Exception as exc:  # noqa: BLE001
        return "", f"The AI request failed ({exc.__class__.__name__}). Check your key and connection."


def _b64(data: bytes) -> str:
    return base64.standard_b64encode(data).decode()


# --------------------------------------------------------------------------- #
# Reading handwriting / scanned pages
# --------------------------------------------------------------------------- #
def read_handwriting(data: bytes, ext: str) -> tuple[str, str | None]:
    """Transcribe a photo (png/jpg/webp) or a scanned PDF of handwritten or printed notes."""
    ext = ext.lower().lstrip(".")
    if ext == "pdf":
        block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(data)}}
    elif ext in IMAGE_TYPES:
        block = {"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[ext], "data": _b64(data)}}
    else:
        return "", "Unsupported file type for handwriting."
    text, err = _ask(
        [block, {"type": "text", "text": "Transcribe every word on this page exactly as written, keeping headings, "
                                          "bullets, formulas and line order. Write maths in plain text. Output only the "
                                          "transcription. If a word is unreadable write [unclear]."}],
        "You are a careful transcriber of student notes, including messy handwriting.")
    if err:
        return "", err
    if not text.strip():
        return "", "Nothing readable was found on that page."
    return text.strip(), None


# --------------------------------------------------------------------------- #
# Picking the part of the notes that talks about a topic
# --------------------------------------------------------------------------- #
def relevant_notes(notes: list[dict], topic_name: str, max_chars: int = 12000) -> tuple[str, bool]:
    """Return (excerpt, matched). ``matched`` is False when no note mentions the topic."""
    words = [w for w in re.findall(r"[a-z0-9]+", topic_name.lower()) if len(w) > 3]
    paras = [p.strip() for n in notes for p in re.split(r"\n\s*\n", n.get("text", "")) if p.strip()]
    scored = [(sum(w in p.lower() for w in words), i, p) for i, p in enumerate(paras)]
    hits = sorted((s for s in scored if s[0] > 0), key=lambda s: (-s[0], s[1]))
    if not hits:
        return "", False
    keep = sorted(hits[:25], key=lambda s: s[1])          # best paragraphs, back in reading order
    return "\n\n".join(p for _, _, p in keep)[:max_chars], True


# --------------------------------------------------------------------------- #
# Material generation
# --------------------------------------------------------------------------- #
_SYSTEM = ("You write study material for students. Reply with ONE JSON object and nothing else, shaped as "
           '{"summary": str, "points": [str], "definitions": [[term, meaning]], '
           '"cards": [{"front": str, "back": str}], '
           '"quiz": [{"q": str, "options": [str, str, str, str], "answer": 0-3, "explanation": str}]}. '
           "Give 4-8 cards and 5-8 quiz questions with plausible distractors. Be accurate and concise.")


def _clean(raw: str, source: str) -> dict | None:
    try:
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return None
    cards = [{"front": str(c["front"]).strip(), "back": str(c["back"]).strip()}
             for c in obj.get("cards", []) if isinstance(c, dict) and c.get("front") and c.get("back")]
    quiz = []
    for q in obj.get("quiz", []):
        try:
            opts = [str(o) for o in q["options"]]
            if len(opts) >= 3 and 0 <= int(q["answer"]) < len(opts) and q.get("q"):
                quiz.append({"q": str(q["q"]), "options": opts, "answer": int(q["answer"]),
                             "explanation": str(q.get("explanation", ""))})
        except (KeyError, TypeError, ValueError):
            continue
    if not (cards or quiz):
        return None
    return {"source": source, "summary": str(obj.get("summary", "")).strip(),
            "points": [str(p) for p in obj.get("points", [])][:10],
            "definitions": [[str(d[0]), str(d[1])] for d in obj.get("definitions", []) if len(d) >= 2][:10],
            "cards": cards, "quiz": quiz}


def local_material(topic_name: str, notes_text: str) -> dict | None:
    """Offline fallback: turn 'X is Y' / 'X: Y' sentences from the notes into cards and quiz questions."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", notes_text) if 25 <= len(s.strip()) <= 220]
    pairs = []
    for s in sentences:
        m = re.match(r"^(?:[-•*]\s*)?([A-Za-z][\w\s'\-()/]{2,50}?)\s*(?::|\bis defined as\b|\bmeans\b|\brefers to\b|\bis\b|\bare\b)\s+(.{12,})$", s)
        if m and len(m.group(1).split()) <= 6:
            pairs.append((m.group(1).strip(), m.group(2).strip().rstrip(".")))
    if len(pairs) < 2:
        return None
    pairs = pairs[:12]
    cards = [{"front": f"What is {t}?" if not t.lower().startswith("the ") else f"What is {t}?", "back": d + "."}
             for t, d in pairs]
    quiz = []
    for i, (t, d) in enumerate(pairs):
        wrong = [x[1] for j, x in enumerate(pairs) if j != i][:3]
        if len(wrong) == 3:
            quiz.append({"q": f"Which statement best describes: {t}?", "options": wrong + [d], "answer": 3,
                         "explanation": f"From your notes: {t} — {d}."})
    return {"source": "your notes (offline)", "summary": " ".join(sentences[:3]),
            "points": [s for s in sentences[:6]], "definitions": [[t, d] for t, d in pairs[:6]],
            "cards": cards, "quiz": quiz}


def build_material(subject_name: str, topic_name: str, notes: list[dict]) -> tuple[dict | None, str | None]:
    """Notes first; if the notes never mention the topic, search the web by topic name."""
    excerpt, matched = relevant_notes(notes, topic_name)
    if matched:
        if available():
            text, err = _ask([{"type": "text", "text": f"Subject: {subject_name}\nTopic: {topic_name}\n\n"
                               f"Student notes (use ONLY these):\n{excerpt}"}], _SYSTEM)
            mat = None if err else _clean(text, "your notes")
            if mat:
                return mat, None
        mat = local_material(topic_name, excerpt)
        if mat:
            return mat, None
        return None, "Your notes mention this topic but I could not turn them into cards. Add an API key or clearer 'term: meaning' lines."
    if not available():
        return None, ("None of your notes mention this topic. Add notes for it, or set an API key "
                      "so the app can search the web using the topic name.")
    text, err = _ask([{"type": "text", "text": f"Subject: {subject_name}\nTopic: {topic_name}\n"
                       "Search the web for reliable information on this topic, then write the study material."}],
                     _SYSTEM, web=True, max_tokens=6000)
    if err:
        return None, err
    mat = _clean(text, "web search")
    return (mat, None) if mat else (None, "The web result could not be turned into study material. Try again.")

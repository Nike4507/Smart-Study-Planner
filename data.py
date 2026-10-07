"""data.py — state model, persistence and small shared helpers.

Everything the app knows lives in ONE plain-dict "state" object that is kept in
``st.session_state`` and saved to ``study_data.json`` after every change, so a
page refresh never loses the student's data.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

DATA_FILE = Path(os.environ.get("STUDY_PLANNER_DATA", Path(__file__).with_name("study_data.json")))

STATUSES = ["Not started", "In progress", "Completed"]
METHODS = ["Mixed", "Reading notes", "Practice problems", "Flashcards", "Video lectures"]
DAY_TYPES = ["weekday", "saturday", "sunday", "holiday"]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def to_min(hhmm: str) -> int:
    """'18:30' -> 1110"""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def to_hhmm(minutes: int) -> str:
    """1110 -> '18:30'"""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def days_until(iso_date: str, today: date) -> int:
    return (date.fromisoformat(iso_date) - today).days


def fmt_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    return f"{h}h" if h else f"{m}m"


# --------------------------------------------------------------------------- #
# State factory + persistence
# --------------------------------------------------------------------------- #
def default_state() -> dict:
    return {
        "subjects": [],
        "tasks": [],
        "availability": {
            "windows": {
                "weekday": [["18:00", "21:00"]],
                "saturday": [["10:00", "13:00"], ["16:00", "19:00"]],
                "sunday": [["09:00", "12:00"], ["15:00", "18:00"]],
                "holiday": [["09:00", "12:00"], ["15:00", "18:00"]],
            },
            "blocked": {
                "weekday": [["09:00", "16:00"], ["16:00", "17:00"]],  # college + travel
                "saturday": [],
                "sunday": [],
                "holiday": [],
            },
            "holiday_dates": [],
            "holiday_mode": False,
            "max_session_min": 50,
            "break_min": 10,
            "daily_cap_min": 240,
        },
        "gamification": {"points": 0, "completed_days": [], "bonus_days": [], "badges": []},
        "flashcards": {},      # topic_id -> {card_key: {known, reviews, missed}}
        "custom_cards": {},    # topic_id -> [{front, back}]
        "card_log": {},        # iso date -> cards reviewed that day
        "quiz_history": [],
        "settings": {"daily_card_target": 10, "daily_target_pct": 60, "plan_days": 7},
    }


def _merge(base: dict, saved: dict) -> None:
    for key, value in saved.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def load_state() -> dict:
    state = default_state()
    if DATA_FILE.exists():
        try:
            _merge(state, json.loads(DATA_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass  # corrupted file -> start fresh instead of crashing the app
    return state


def save_state(state: dict) -> None:
    try:
        tmp = DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(DATA_FILE)
    except OSError:
        pass  # read-only filesystem (e.g. some cloud hosts): app still works in-memory


# --------------------------------------------------------------------------- #
# Model factories
# --------------------------------------------------------------------------- #
def make_subject(name, exam_date, difficulty, importance, progress=0, est_hours=0.0, method="Mixed") -> dict:
    return {
        "id": new_id("sub"),
        "name": name.strip(),
        "exam_date": exam_date.isoformat() if isinstance(exam_date, date) else exam_date,
        "difficulty": int(difficulty),
        "importance": int(importance),
        "progress": float(progress),
        "est_hours": float(est_hours or 0),
        "method": method,
        "topics": [],
    }


def make_topic(name: str, est_minutes: int = 45) -> dict:
    return {
        "id": new_id("top"),
        "name": name.strip(),
        "status": "Not started",
        "est_minutes": int(est_minutes),
        "done_min": 0,        # study minutes completed through tasks
        "weak": False,        # flagged by a poor quiz result
        "quiz_done": False,
    }


def make_task(day: date, start_min: int, end_min: int, kind: str, subject: dict | None,
              topic: dict | None, title: str, reason: str, status: str = "pending") -> dict:
    return {
        "id": new_id("task"),
        "date": day.isoformat(),
        "start": to_hhmm(start_min),
        "end": to_hhmm(end_min),
        "duration": end_min - start_min,
        "type": kind,  # study | revision | quiz | break
        "subject_id": subject["id"] if subject else None,
        "topic_id": topic["id"] if topic else None,
        "title": title,
        "reason": reason,
        "status": status,  # pending | done | missed | skipped | break
        "points": 0,
    }


def default_topic_minutes(subject: dict) -> int:
    """Rough study time per topic when the student doesn't specify one."""
    return 30 + 10 * int(subject["difficulty"])


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def find_subject(state: dict, subject_id: str | None) -> dict | None:
    return next((s for s in state["subjects"] if s["id"] == subject_id), None)


def find_topic(state: dict, topic_id: str | None) -> tuple[dict | None, dict | None]:
    for s in state["subjects"]:
        for t in s["topics"]:
            if t["id"] == topic_id:
                return s, t
    return None, None


def find_task(state: dict, task_id: str) -> dict | None:
    return next((t for t in state["tasks"] if t["id"] == task_id), None)


# --------------------------------------------------------------------------- #
# Progress engine (shared by planner, gamification and UI)
# --------------------------------------------------------------------------- #
def topic_fraction(topic: dict) -> float:
    if topic["status"] == "Completed":
        return 1.0
    return min(topic.get("done_min", 0) / max(topic["est_minutes"], 1), 1.0)


def topic_remaining(topic: dict) -> int:
    """Study minutes still needed for a topic."""
    if topic["status"] == "Completed":
        return 0
    return max(0, topic["est_minutes"] - topic.get("done_min", 0))


def subject_progress(subject: dict) -> float:
    """0-100. Starts at the student's own estimate and climbs to 100 as topics are finished."""
    base = float(subject.get("progress", 0))
    topics = subject.get("topics", [])
    if not topics:
        return base
    total = sum(t["est_minutes"] for t in topics) or 1
    fraction = sum(topic_fraction(t) * t["est_minutes"] for t in topics) / total
    return base + (100 - base) * fraction


# --------------------------------------------------------------------------- #
# Demo data (matches the judges' demo story in the spec)
# --------------------------------------------------------------------------- #
def load_demo(state: dict) -> None:
    fresh = default_state()
    today = date.today()

    def build(name, days, diff, imp, prog, topics):
        s = make_subject(name, today + timedelta(days=days), diff, imp, prog, method="Practice problems")
        s["topics"] = [make_topic(n, m) for n, m in topics]
        return s

    fresh["subjects"] = [
        build("Mathematics", 3, 4, 5, 30, [("Integration", 60), ("Differentiation", 45), ("Limits and Continuity", 45)]),
        build("Physics", 5, 5, 4, 20, [("Electrostatics", 60), ("Laws of Motion", 45), ("Current Electricity", 45)]),
        build("Python", 7, 3, 4, 40, [("Loops", 40), ("Functions", 45), ("Lists and Dictionaries", 45)]),
    ]
    # College until 4 PM + 1h travel, study 6-9 PM on weekdays (already the default)
    fresh["gamification"]["completed_days"] = [(today - timedelta(days=i)).isoformat() for i in range(4, 0, -1)]
    fresh["gamification"]["points"] = 150  # demo: points from the 4 previous days
    state.clear()
    state.update(fresh)

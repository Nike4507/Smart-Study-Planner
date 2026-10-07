"""planner.py — priority scoring, availability windows, schedule generation and adaptive rescheduling.

Principle (spec §5.6):
    Exam urgency + difficulty + importance + progress gap + topic urgency
        -> priority score -> greedy allocation into the student's free windows.

Every task carries a human-readable ``reason`` so the planner can explain itself.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import data as D
import gamification as G

# Tunable weights (spec §7: "exact weights can be tuned during testing")
W = {
    "urgency_max": 50,      # exam today -> 50 pts, 7 days away -> 25, 14 days -> ~17
    "difficulty": 4,        # x (1-5)  -> 4..20
    "importance": 4,        # x (1-5)  -> 4..20
    "gap": 0.2,             # x (100 - progress) -> 0..20
    "weak": 15,             # topic failed a quiz
    "in_progress": 5,       # started but unfinished
    "repeat_penalty": 12,   # per session of the same subject already placed today (interleaving)
    "followup_boost": 6,    # quizzes / revision slightly outrank fresh study
}
MIN_CHUNK = 20      # don't create study blocks shorter than this (unless that is all that's left)
QUIZ_MIN = 15
REVISION_MIN = 20
MIN_GAP = 10        # smallest free gap worth scheduling into


# --------------------------------------------------------------------------- #
# Priority engine
# --------------------------------------------------------------------------- #
def exam_urgency(days_left: int) -> float:
    return W["urgency_max"] * 7 / (7 + max(days_left, 0))


def topic_priority(subject: dict, topic: dict, today: date) -> tuple[float, str]:
    """Return (score, explanation) for one topic."""
    days_left = D.days_until(subject["exam_date"], today)
    progress = D.subject_progress(subject)
    started = topic["status"] == "In progress" or topic.get("done_min", 0) > 0
    parts = {
        "urgency": exam_urgency(days_left),
        "difficulty": subject["difficulty"] * W["difficulty"],
        "importance": subject["importance"] * W["importance"],
        "gap": (100 - progress) * W["gap"],
        "topic": (W["weak"] if topic.get("weak") else 0) + (W["in_progress"] if started else 0),
    }
    reasons = []
    if topic.get("weak"):
        reasons.append("Weak topic – needs revision")
    if days_left <= 3:
        reasons.append(f"Exam in {max(days_left, 0)} day{'s' if days_left != 1 else ''}")
    elif days_left <= 7:
        reasons.append("Exam soon")
    if progress < 50:
        reasons.append(f"Only {progress:.0f}% complete")
    if subject["difficulty"] >= 4:
        reasons.append("High difficulty")
    if subject["importance"] >= 4:
        reasons.append("High importance")
    if started and not topic.get("weak"):
        reasons.append("Finish what you started")
    return sum(parts.values()), " + ".join(reasons[:3]) or "Steady progress through the syllabus"


def rank_topics(state: dict, today: date) -> list[dict]:
    """All unfinished topics ranked by priority (used by dashboard + 'why this plan' view)."""
    rows = []
    for s in state["subjects"]:
        if D.days_until(s["exam_date"], today) < 0:
            continue
        for t in s["topics"]:
            if D.topic_remaining(t) <= 0:
                continue
            score, reason = topic_priority(s, t, today)
            rows.append({"subject": s, "topic": t, "score": score, "reason": reason,
                         "days_left": D.days_until(s["exam_date"], today)})
    return sorted(rows, key=lambda r: -r["score"])


def subject_priority(subject: dict, today: date) -> float:
    days_left = D.days_until(subject["exam_date"], today)
    return (exam_urgency(days_left) + subject["difficulty"] * W["difficulty"]
            + subject["importance"] * W["importance"] + (100 - D.subject_progress(subject)) * W["gap"])


# --------------------------------------------------------------------------- #
# Availability engine
# --------------------------------------------------------------------------- #
def day_type(avail: dict, day: date) -> str:
    if avail.get("holiday_mode") or day.isoformat() in avail.get("holiday_dates", []):
        return "holiday"
    return {5: "saturday", 6: "sunday"}.get(day.weekday(), "weekday")


def _normalize(windows: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Drop invalid windows, sort, merge overlaps."""
    out: list[tuple[int, int]] = []
    for s, e in sorted(w for w in windows if w[1] > w[0]):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(windows: list[tuple[int, int]], busy: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove ``busy`` intervals from ``windows``."""
    result = []
    for s, e in windows:
        pieces = [(s, e)]
        for bs, be in busy:
            nxt = []
            for ps, pe in pieces:
                if be <= ps or bs >= pe:
                    nxt.append((ps, pe))
                    continue
                if bs > ps:
                    nxt.append((ps, bs))
                if be < pe:
                    nxt.append((be, pe))
            pieces = nxt
        result.extend(pieces)
    return sorted(result)


def get_windows(avail: dict, day: date) -> list[tuple[int, int]]:
    """Free study windows (minutes since midnight) = study windows minus blocked periods."""
    kind = day_type(avail, day)
    study = _normalize([(D.to_min(a), D.to_min(b)) for a, b in avail["windows"].get(kind, [])])
    blocked = [(D.to_min(a), D.to_min(b)) for a, b in avail["blocked"].get(kind, [])]
    return subtract(study, blocked)


def available_minutes(state: dict, day: date) -> int:
    avail = state["availability"]
    raw = sum(e - s for s, e in get_windows(avail, day))
    return min(raw, avail["daily_cap_min"])


# --------------------------------------------------------------------------- #
# Schedule engine
# --------------------------------------------------------------------------- #
def _ceil5(x: int) -> int:
    return int(math.ceil(x / 5) * 5)


def _followup(kind: str, subject: dict, topic: dict, due: date, weak: bool = False) -> dict:
    return {"kind": kind, "subject": subject, "topic": topic, "due": due, "weak": weak,
            "minutes": QUIZ_MIN if kind == "quiz" else REVISION_MIN}


def _done_revision_since(state: dict, topic_id: str, since: date | None) -> bool:
    return any(t["type"] == "revision" and t["status"] == "done" and t["topic_id"] == topic_id
               and (since is None or t["date"] >= since.isoformat()) for t in state["tasks"])


def _seed_followups(state: dict, today: date) -> list[dict]:
    """Quizzes / revision owed for topics that are already finished or flagged weak."""
    out = []
    for s in state["subjects"]:
        for t in s["topics"]:
            finished = t["status"] == "Completed" or (D.topic_remaining(t) == 0 and t.get("done_min", 0) > 0)
            if finished and not t.get("quiz_done"):
                out.append(_followup("quiz", s, t, today))
            if t.get("weak"):
                if not _done_revision_since(state, t["id"], today - timedelta(days=3)):
                    out.append(_followup("revision", s, t, today, weak=True))
            elif finished and not _done_revision_since(state, t["id"], None):
                out.append(_followup("revision", s, t, today))
    return out


def _pick(state, day, remaining, followups, free, cap_left, max_session, counts):
    """Choose the best-scoring item that fits into ``free`` minutes. Returns (candidate, duration) or None."""
    limit = min(free, cap_left)
    cands = []
    for s in state["subjects"]:
        if D.days_until(s["exam_date"], day) <= 0:      # study only BEFORE exam day
            continue
        for t in s["topics"]:
            rem = remaining.get(t["id"], 0)
            if rem <= 0:
                continue
            score, reason = topic_priority(s, t, day)
            score -= W["repeat_penalty"] * counts.get(s["id"], 0)   # interleave subjects
            cands.append({"kind": "study", "subject": s, "topic": t, "score": score, "reason": reason,
                          "need": min(MIN_CHUNK, rem), "max": min(rem, max_session), "rem": rem})
    for f in followups:
        if f["due"] > day or D.days_until(f["subject"]["exam_date"], day) <= 0:
            continue
        score, _ = topic_priority(f["subject"], f["topic"], day)
        if f["kind"] == "quiz":
            reason = "Check understanding"
        else:
            reason = "Weak topic – revise it" if f["weak"] else "Reinforce concepts"
        cands.append({"kind": f["kind"], "subject": f["subject"], "topic": f["topic"], "followup": f,
                      "score": score + W["followup_boost"], "reason": reason,
                      "need": f["minutes"], "max": f["minutes"], "rem": 0})
    for c in sorted(cands, key=lambda c: -c["score"]):
        if limit >= c["need"]:
            dur = min(c["max"], limit)
            if c["kind"] == "study" and 0 < c["rem"] - dur < MIN_CHUNK and c["rem"] - MIN_CHUNK >= MIN_CHUNK:
                dur = c["rem"] - MIN_CHUNK               # balance the split instead of leaving a tiny block
            dur -= dur % 5
            return c, max(dur, 5)
    return None


def _plan_day(state, day, remaining, followups, from_minute):
    avail = state["availability"]
    iso = day.isoformat()
    existing = [t for t in state["tasks"] if t["date"] == iso and t["status"] in ("done", "missed", "skipped")]
    busy = [(D.to_min(t["start"]), D.to_min(t["end"])) for t in existing]
    if from_minute:
        busy.append((0, from_minute))
    windows = subtract(get_windows(avail, day), busy)
    cap_left = avail["daily_cap_min"] - sum(t["duration"] for t in existing if t["status"] == "done")
    max_session, brk = avail["max_session_min"], avail["break_min"]
    counts: dict[str, int] = {}
    created = []

    for ws, we in windows:
        cursor, prev = ws, False
        while cap_left >= MIN_GAP:
            gap = brk if prev else 0
            free = we - cursor - gap
            if free < MIN_GAP:
                break
            choice = _pick(state, day, remaining, followups, free, cap_left, max_session, counts)
            if not choice:
                break
            c, dur = choice
            start = cursor + gap
            if gap:
                created.append(D.make_task(day, cursor, start, "break", None, None, "Break", "Recovery", status="break"))
            s, t = c["subject"], c["topic"]
            title = {"study": f"{s['name']} — {t['name']}",
                     "revision": f"{t['name']} flashcards",
                     "quiz": f"{t['name']} quiz"}[c["kind"]]
            created.append(D.make_task(day, start, start + dur, c["kind"], s, t, title, c["reason"]))
            cursor, prev, cap_left = start + dur, True, cap_left - dur

            if c["kind"] == "study":
                remaining[t["id"]] -= dur
                counts[s["id"]] = counts.get(s["id"], 0) + 1
                if remaining[t["id"]] <= 0:              # topic fully scheduled -> quiz now, revise tomorrow
                    followups.append(_followup("quiz", s, t, day))
                    followups.append(_followup("revision", s, t, day + timedelta(days=1)))
            else:
                followups.remove(c["followup"])
    state["tasks"].extend(created)


def generate_plan(state: dict, start: date | None = None, days: int = 7, from_minute: int | None = None) -> dict:
    """(Re)build all pending tasks from ``start`` onward. Done/missed/skipped tasks are kept as history."""
    start = start or date.today()
    iso = start.isoformat()
    state["tasks"] = [t for t in state["tasks"]
                      if not (t["status"] in ("pending", "break") and t["date"] >= iso)]
    state["settings"]["plan_days"] = days

    remaining = {t["id"]: _ceil5(D.topic_remaining(t)) for s in state["subjects"] for t in s["topics"]}
    followups = _seed_followups(state, start)
    for offset in range(days):
        _plan_day(state, start + timedelta(days=offset), remaining, followups,
                  from_minute if offset == 0 else None)

    new = [t for t in state["tasks"] if t["status"] == "pending" and t["date"] >= iso]
    unscheduled, no_topics, expired = [], [], []
    for s in state["subjects"]:
        left = D.days_until(s["exam_date"], start)
        if left <= 0:
            expired.append(s["name"])
            continue
        if not s["topics"]:
            no_topics.append(s["name"])
        for t in s["topics"]:
            if remaining.get(t["id"], 0) > 0:
                unscheduled.append({"subject": s["name"], "topic": t["name"], "minutes": remaining[t["id"]]})
    return {"tasks": len(new), "minutes": sum(t["duration"] for t in new),
            "unscheduled": unscheduled, "no_topics": no_topics, "expired": expired}


# --------------------------------------------------------------------------- #
# Task events: complete / undo / miss (adaptive engine)
# --------------------------------------------------------------------------- #
def complete_task(state: dict, task_id: str, today: date | None = None, award: bool = True) -> list[str]:
    today = today or date.today()
    task = D.find_task(state, task_id)
    if not task or task["status"] == "done":
        return []
    task["status"] = "done"
    msgs: list[str] = []
    _, topic = D.find_topic(state, task["topic_id"])
    if topic and task["type"] == "study":
        topic["done_min"] = topic.get("done_min", 0) + task["duration"]
        if D.topic_remaining(topic) == 0:
            topic["status"] = "Completed"
            msgs.append(f"✅ Topic completed: {topic['name']}")
        elif topic["status"] != "Completed":
            topic["status"] = "In progress"
    points = G.task_points(state, task) if award else 0
    task["points"] = points
    G.add_points(state, points)
    if points:
        msgs.insert(0, f"+{points} points")
    msgs += G.refresh_day(state, date.fromisoformat(task["date"]))
    msgs += [f"🏅 New badge: {b}" for b in G.update_badges(state, today)]
    return msgs


def undo_task(state: dict, task_id: str) -> None:
    task = D.find_task(state, task_id)
    if not task or task["status"] != "done":
        return
    task["status"] = "pending"
    _, topic = D.find_topic(state, task["topic_id"])
    if topic and task["type"] == "study":
        topic["done_min"] = max(0, topic.get("done_min", 0) - task["duration"])
        if topic["status"] == "Completed" and D.topic_remaining(topic) > 0:
            topic["status"] = "In progress" if topic["done_min"] > 0 else "Not started"
    G.add_points(state, -task.get("points", 0))
    task["points"] = 0
    G.refresh_day(state, date.fromisoformat(task["date"]))


def miss_task(state: dict, task_id: str, today: date | None = None, status: str = "missed") -> dict | None:
    """Mark a task missed/skipped and redistribute the remaining work. Returns where it was moved to."""
    today = today or date.today()
    task = D.find_task(state, task_id)
    if not task or task["status"] != "pending":
        return None
    task["status"] = status
    summary = generate_plan(state, today, state["settings"].get("plan_days", 7))
    pending = sorted((t for t in state["tasks"] if t["status"] == "pending"
                      and t["topic_id"] == task["topic_id"] and t["type"] == task["type"]),
                     key=lambda t: (t["date"], t["start"]))
    return {"task": task, "moved_to": pending[0] if pending else None, "summary": summary}


def mark_overdue(state: dict, today: date) -> int:
    """Pending tasks from earlier days become 'missed'. Returns how many."""
    iso = today.isoformat()
    n = 0
    for t in state["tasks"]:
        if t["status"] == "pending" and t["date"] < iso:
            t["status"] = "missed"
            n += 1
    state["tasks"] = [t for t in state["tasks"] if not (t["status"] == "break" and t["date"] < iso)]
    return n


def next_task(state: dict, day: date) -> dict | None:
    iso = day.isoformat()
    pending = [t for t in state["tasks"] if t["date"] == iso and t["status"] == "pending"]
    return min(pending, key=lambda t: t["start"]) if pending else None

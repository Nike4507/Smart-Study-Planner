"""gamification.py — points, streaks, badges and levels (simple event-based rules)."""
from __future__ import annotations

from datetime import date, timedelta

import data as D

POINTS = {
    "study": 10,          # normal study task
    "study_high": 15,     # difficult / high-priority task
    "revision": 10,
    "quiz": 10,           # completing a quiz
    "quiz_bonus": 10,     # quiz score >= 80%
    "daily_bonus": 25,    # whole daily plan completed
    "streak7": 100,       # 7-day streak badge
}
LEVEL_XP = 200

BADGES = {
    "First Day": "Hit your daily target for the first time",
    "3-Day Streak": "Reach a 3-day streak",
    "7-Day Streak": "Reach a 7-day streak (+100 bonus points)",
    "Exam Ready": "Reach 90% progress in any subject",
    "Quiz Ace": "Score 80% or more in a quiz",
}


# --------------------------------------------------------------------------- #
# Day statistics
# --------------------------------------------------------------------------- #
def day_stats(state: dict, day: date) -> dict:
    iso = day.isoformat()
    tasks = [t for t in state["tasks"] if t["date"] == iso and t["type"] != "break"]
    planned = sum(t["duration"] for t in tasks)
    done = sum(t["duration"] for t in tasks if t["status"] == "done")
    return {
        "n_total": len(tasks),
        "n_done": sum(1 for t in tasks if t["status"] == "done"),
        "planned_min": planned,
        "done_min": done,
        "pct": (done / planned * 100) if planned else 0.0,
    }


# --------------------------------------------------------------------------- #
# Points
# --------------------------------------------------------------------------- #
def is_high_priority(subject: dict | None, day: date) -> bool:
    if not subject:
        return False
    return subject["difficulty"] >= 4 or D.days_until(subject["exam_date"], day) <= 3


def task_points(state: dict, task: dict) -> int:
    if task["type"] == "quiz":
        return POINTS["quiz"]
    if task["type"] == "revision":
        return POINTS["revision"]
    subject = D.find_subject(state, task["subject_id"])
    day = date.fromisoformat(task["date"])
    return POINTS["study_high"] if is_high_priority(subject, day) else POINTS["study"]


def add_points(state: dict, amount: int) -> None:
    g = state["gamification"]
    g["points"] = max(0, g["points"] + amount)


def refresh_day(state: dict, day: date) -> list[str]:
    """Re-evaluate the daily target + full-plan bonus for ``day``. Safe to call after complete AND undo."""
    g = state["gamification"]
    iso = day.isoformat()
    stats = day_stats(state, day)
    msgs: list[str] = []

    target = state["settings"].get("daily_target_pct", 60)
    target_met = stats["planned_min"] > 0 and stats["pct"] >= target
    if target_met and iso not in g["completed_days"]:
        g["completed_days"].append(iso)
        msgs.append("Daily target reached — streak extended!")
    elif not target_met and iso in g["completed_days"]:
        g["completed_days"].remove(iso)

    full = stats["n_total"] > 0 and stats["n_done"] == stats["n_total"]
    if full and iso not in g["bonus_days"]:
        g["bonus_days"].append(iso)
        add_points(state, POINTS["daily_bonus"])
        msgs.append(f"Whole daily plan completed! +{POINTS['daily_bonus']} bonus points")
    elif not full and iso in g["bonus_days"]:
        g["bonus_days"].remove(iso)
        add_points(state, -POINTS["daily_bonus"])
    return msgs


# --------------------------------------------------------------------------- #
# Streaks, levels, badges
# --------------------------------------------------------------------------- #
def current_streak(state: dict, today: date) -> int:
    days = set(state["gamification"]["completed_days"])
    cursor = today if today.isoformat() in days else today - timedelta(days=1)
    count = 0
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def best_streak(state: dict) -> int:
    days = sorted(date.fromisoformat(d) for d in state["gamification"]["completed_days"])
    best = run = 0
    prev = None
    for d in days:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    return best


def streak_message(state: dict, today: date) -> str | None:
    days = state["gamification"]["completed_days"]
    if days and current_streak(state, today) == 0:
        return "Your streak reset — no worries, every great streak starts with one good day. Today is a fresh start!"
    return None


def level_info(points: int) -> dict:
    return {"level": points // LEVEL_XP + 1, "xp": points % LEVEL_XP, "needed": LEVEL_XP}


def update_badges(state: dict, today: date) -> list[str]:
    g = state["gamification"]
    best = best_streak(state)
    checks = {
        "First Day": len(g["completed_days"]) >= 1,
        "3-Day Streak": best >= 3,
        "7-Day Streak": best >= 7,
        "Exam Ready": any(D.subject_progress(s) >= 90 for s in state["subjects"]),
        "Quiz Ace": any(q.get("pct", 0) >= 80 for q in state["quiz_history"]),
    }
    new = []
    for name, ok in checks.items():
        if ok and name not in g["badges"]:
            g["badges"].append(name)
            new.append(name)
            if name == "7-Day Streak":
                add_points(state, POINTS["streak7"])
    return new

"""Run with:  pytest -q"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import data as D          # noqa: E402
import gamification as G  # noqa: E402
import learning as L      # noqa: E402
import planner as P       # noqa: E402
import syllabus as SY     # noqa: E402

TODAY = date(2026, 10, 7)  # a Wednesday


def make_state():
    state = D.default_state()
    maths = D.make_subject("Mathematics", TODAY + timedelta(days=3), 4, 5, 30)
    maths["topics"] = [D.make_topic("Integration", 60), D.make_topic("Differentiation", 45)]
    phys = D.make_subject("Physics", TODAY + timedelta(days=5), 5, 4, 20)
    phys["topics"] = [D.make_topic("Electrostatics", 60), D.make_topic("Laws of Motion", 45)]
    state["subjects"] = [maths, phys]
    return state


def study_tasks(state):
    return [t for t in state["tasks"] if t["type"] != "break"]


def test_priority_rises_as_exam_gets_closer():
    s = make_state()
    subj, topic = s["subjects"][0], s["subjects"][0]["topics"][0]
    far = P.topic_priority(subj, topic, TODAY - timedelta(days=20))[0]
    near = P.topic_priority(subj, topic, TODAY)[0]
    assert near > far


def test_weak_topic_gets_extra_priority_and_explanation():
    s = make_state()
    subj, topic = s["subjects"][0], s["subjects"][0]["topics"][0]
    base, _ = P.topic_priority(subj, topic, TODAY)
    topic["weak"] = True
    boosted, reason = P.topic_priority(subj, topic, TODAY)
    assert boosted > base and "Weak" in reason


def test_tasks_stay_inside_free_windows_and_outside_blocked_time():
    s = make_state()
    s["availability"]["windows"]["weekday"] = [["16:00", "21:00"]]   # overlaps blocked college/travel until 17:00
    P.generate_plan(s, TODAY, 1)
    assert study_tasks(s)
    for t in s["tasks"]:
        assert D.to_min(t["start"]) >= D.to_min("17:00")
        assert D.to_min(t["end"]) <= D.to_min("21:00")


def test_no_overlaps_and_daily_cap_respected():
    s = make_state()
    s["availability"]["daily_cap_min"] = 90
    s["availability"]["windows"]["weekday"] = [["17:00", "22:00"]]
    P.generate_plan(s, TODAY, 3)
    for day in {t["date"] for t in s["tasks"]}:
        day_tasks = sorted((t for t in s["tasks"] if t["date"] == day), key=lambda t: t["start"])
        assert sum(t["duration"] for t in day_tasks if t["type"] != "break") <= 90
        for a, b in zip(day_tasks, day_tasks[1:]):
            assert a["end"] <= b["start"]


def test_sessions_never_exceed_max_session_and_breaks_are_inserted():
    s = make_state()
    s["availability"]["max_session_min"] = 30
    P.generate_plan(s, TODAY, 1)
    assert all(t["duration"] <= 30 for t in study_tasks(s) if t["type"] == "study")
    assert any(t["type"] == "break" for t in s["tasks"])


def test_nothing_scheduled_on_or_after_exam_day():
    s = make_state()
    P.generate_plan(s, TODAY, 7)
    maths = s["subjects"][0]
    exam = maths["exam_date"]
    assert not [t for t in s["tasks"] if t["subject_id"] == maths["id"] and t["date"] >= exam]


def test_large_topic_is_split_and_total_minutes_match_estimate():
    s = make_state()
    P.generate_plan(s, TODAY, 7)
    topic = s["subjects"][0]["topics"][0]  # Integration, 60 min, max session 50
    chunks = [t for t in s["tasks"] if t["topic_id"] == topic["id"] and t["type"] == "study"]
    assert len(chunks) >= 2
    assert sum(t["duration"] for t in chunks) == 60


def test_plan_contains_quiz_and_revision_sessions():
    s = make_state()
    P.generate_plan(s, TODAY, 7)
    kinds = {t["type"] for t in s["tasks"]}
    assert {"study", "quiz", "revision"} <= kinds


def test_every_task_has_a_reason():
    s = make_state()
    P.generate_plan(s, TODAY, 3)
    assert all(t["reason"] for t in s["tasks"])


def test_unscheduled_work_is_reported_when_time_is_short():
    s = make_state()
    s["availability"]["windows"]["weekday"] = [["18:00", "18:30"]]
    summary = P.generate_plan(s, TODAY, 3)
    assert summary["unscheduled"]


def test_complete_task_awards_points_and_updates_progress():
    s = make_state()
    P.generate_plan(s, TODAY, 1)
    task = next(t for t in s["tasks"] if t["type"] == "study")
    before = D.subject_progress(D.find_subject(s, task["subject_id"]))
    msgs = P.complete_task(s, task["id"], TODAY)
    assert s["gamification"]["points"] >= 10 and msgs
    assert D.subject_progress(D.find_subject(s, task["subject_id"])) > before


def test_undo_reverses_points_and_progress():
    s = make_state()
    P.generate_plan(s, TODAY, 1)
    task = next(t for t in s["tasks"] if t["type"] == "study")
    _, topic = D.find_topic(s, task["topic_id"])
    P.complete_task(s, task["id"], TODAY)
    P.undo_task(s, task["id"])
    assert s["gamification"]["points"] == 0
    assert topic["done_min"] == 0 and task["status"] == "pending"


def test_completing_whole_day_gives_bonus_and_streak():
    s = make_state()
    P.generate_plan(s, TODAY, 1)
    for t in [t for t in s["tasks"] if t["status"] == "pending"]:
        P.complete_task(s, t["id"], TODAY)
    assert TODAY.isoformat() in s["gamification"]["bonus_days"]
    assert G.current_streak(s, TODAY) == 1
    assert "First Day" in s["gamification"]["badges"]


def test_streak_counts_consecutive_days_and_resets_after_gap():
    s = make_state()
    s["gamification"]["completed_days"] = [(TODAY - timedelta(days=i)).isoformat() for i in (1, 2, 3)]
    assert G.current_streak(s, TODAY) == 3
    assert G.current_streak(s, TODAY + timedelta(days=2)) == 0
    assert G.streak_message(s, TODAY + timedelta(days=2))


def test_missed_task_is_rescheduled_not_lost():
    s = make_state()
    P.generate_plan(s, TODAY, 3)
    task = next(t for t in s["tasks"] if t["type"] == "study" and t["date"] == TODAY.isoformat())
    _, topic = D.find_topic(s, task["topic_id"])
    result = P.miss_task(s, task["id"], TODAY)
    assert task["status"] == "missed"
    assert result["moved_to"] is not None
    assert result["moved_to"]["id"] != task["id"]
    # all of the topic's minutes are still planned somewhere (missed one doesn't count as done)
    planned = sum(t["duration"] for t in s["tasks"]
                  if t["topic_id"] == topic["id"] and t["type"] == "study" and t["status"] == "pending")
    assert planned == topic["est_minutes"]


def test_overdue_pending_tasks_become_missed():
    s = make_state()
    P.generate_plan(s, TODAY, 2)
    assert P.mark_overdue(s, TODAY + timedelta(days=1)) > 0
    assert not [t for t in s["tasks"] if t["status"] == "pending" and t["date"] < (TODAY + timedelta(days=1)).isoformat()]


def test_holiday_dates_use_holiday_windows():
    s = make_state()
    s["availability"]["holiday_dates"] = [TODAY.isoformat()]
    s["availability"]["blocked"]["holiday"] = []
    assert P.day_type(s["availability"], TODAY) == "holiday"
    assert P.get_windows(s["availability"], TODAY) == [(540, 720), (900, 1080)]


def test_subtract_intervals():
    assert P.subtract([(0, 100)], [(20, 30), (90, 120)]) == [(0, 20), (30, 90)]


def test_syllabus_parser_cleans_headings():
    text = "Unit 1: Limits\n2. Derivatives\n• Integration\n\nPage 3\nintegration\n- Applications of Integrals;\n"
    assert SY.parse_topics(text) == ["Limits", "Derivatives", "Integration", "Applications of Integrals"]


def test_quiz_scoring_flags_weak_topic_and_awards_points():
    s = make_state()
    subj, topic = s["subjects"][0], s["subjects"][0]["topics"][0]
    pool = L.quiz_pool(s, subj, topic)
    assert len(pool) >= 5
    result = L.finish_quiz(s, subj["id"], topic["id"], 2, 5, TODAY)
    assert result["weak"] and topic["weak"]
    assert s["gamification"]["points"] == 10
    result = L.finish_quiz(s, subj["id"], topic["id"], 5, 5, TODAY)
    assert not topic["weak"] and s["gamification"]["points"] == 10 + 20
    assert "Quiz Ace" in s["gamification"]["badges"]


def test_prepare_quiz_keeps_correct_answer_after_shuffle():
    s = make_state()
    subj, topic = s["subjects"][0], s["subjects"][0]["topics"][0]
    pool = L.quiz_pool(s, subj, topic)
    for q in L.prepare_quiz(pool, 5, seed=1):
        original = next(p for p in pool if p["q"] == q["q"])
        assert q["options"][q["answer"]] == original["options"][original["answer"]]


def test_custom_cards_unlock_quiz():
    s = make_state()
    subj = s["subjects"][0]
    topic = D.make_topic("Vectors", 30)
    subj["topics"].append(topic)
    assert L.quiz_pool(s, subj, topic) == []
    for i in range(5):
        L.add_custom_card(s, topic["id"], f"Q{i}", f"A{i}")
    assert len(L.quiz_pool(s, subj, topic)) == 5


def test_progress_formula_starts_at_user_value_and_reaches_100():
    subj = D.make_subject("X", TODAY, 3, 3, progress=40)
    subj["topics"] = [D.make_topic("A", 60)]
    assert D.subject_progress(subj) == 40
    subj["topics"][0]["status"] = "Completed"
    assert D.subject_progress(subj) == 100


# ---- notes / handwriting-era additions: study material built from notes ----
def test_notes_become_cards_and_quiz_offline():
    import ai
    notes = [{"name": "n", "text": "Photosynthesis is the process plants use to turn light into chemical energy.\n"
              "Chlorophyll is the green pigment that absorbs light in chloroplasts.\n"
              "Stomata are tiny pores on leaves that let gases move in and out.\n"
              "Glucose is the sugar produced by photosynthesis and used as fuel."}]
    mat, err = ai.build_material("Biology", "Photosynthesis", notes)
    assert err is None and mat["source"].startswith("your notes")
    assert len(mat["cards"]) >= 3 and len(mat["quiz"]) >= 3
    assert all(q["options"][q["answer"]] for q in mat["quiz"])


def test_topic_missing_from_notes_without_key_gives_clear_message():
    import ai
    ai._OVERRIDE.clear()
    mat, err = ai.build_material("Biology", "Meiosis", [{"name": "n", "text": "Unrelated text about rivers."}])
    if not ai.available():
        assert mat is None and "notes" in err.lower()


def test_generated_material_takes_priority_over_builtin():
    from datetime import date, timedelta
    s = D.default_state()
    subj = D.make_subject("Mathematics", date.today() + timedelta(days=10), 3, 3)
    topic = D.make_topic("Integration", 45)
    subj["topics"].append(topic)
    s["subjects"].append(subj)
    s["materials"][topic["id"]] = {"source": "your notes", "summary": "x", "points": [], "definitions": [],
                                   "cards": [{"front": "Q", "back": "A"}], "quiz": [
                                       {"q": "q", "options": ["a", "b", "c", "d"], "answer": 1, "explanation": ""}]}
    assert L.get_cards(s, subj, topic)[0]["front"] == "Q"
    assert L.quiz_pool(s, subj, topic)[0]["q"] == "q"
    assert L.get_content(subj, topic, s)["source"] == "your notes"

"""app.py — Smart Study Planner (Streamlit front-end).

Run with:  streamlit run app.py

Navigation has five main pages. Everything else lives inside them:
  Dashboard  -> start-studying timer (full-page focus mode)
  Subjects   -> list -> add subject -> syllabus & notes (one flow, no extra tabs)
  Planner    -> Today / Week plan / Schedule
  Study      -> Learn / Flashcards / Quiz (built from your notes, or the web)
  Progress   -> Overview / Subjects / Rewards
Styling lives in theme.py and charts.py; logic in planner.py, learning.py, ai.py, gamification.py.
"""
from __future__ import annotations

import random
import time
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import streamlit as st

import ai
import charts as C
import data as D
import gamification as G
import learning as L
import planner as P
import syllabus as SY
import theme as T

st.set_page_config(page_title="Smart Study Planner", page_icon=":material/school:", layout="wide")

PAGE_DASH, PAGE_SUBJECTS, PAGE_PLANNER, PAGE_STUDY, PAGE_PROGRESS = "Dashboard", "Subjects", "Planner", "Study", "Progress"
PAGES = [PAGE_DASH, PAGE_SUBJECTS, PAGE_PLANNER, PAGE_STUDY, PAGE_PROGRESS]
TYPE_LABEL = {"study": "Study", "revision": "Revision", "quiz": "Quiz", "break": "Break"}
WIDGET_PREFIXES = ("av_", "ns_", "ed_", "tp_", "sel_", "quizrun_", "dash_")
UPLOAD_TYPES = ["pdf", "docx", "txt", "png", "jpg", "jpeg", "webp"]


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def S() -> dict:
    return st.session_state.state


def save() -> None:
    D.save_state(S())


def flash(message: str, kind: str = "success") -> None:
    st.session_state.setdefault("flash", []).append((kind, message))


def show_flash() -> None:
    for kind, message in st.session_state.pop("flash", []):
        getattr(st, kind)(message)


def go(page: str) -> None:
    st.session_state.page = page


def tab_control(key: str, options: list[str]) -> str:
    """A pill-style tab switcher whose value can also be set from callbacks."""
    st.session_state.setdefault(key, options[0])
    if st.session_state[key] not in options:
        st.session_state[key] = options[0]
    return st.segmented_control("View", options, key=key, label_visibility="collapsed") or options[0]


def focus_topic(subject_id: str, topic_id: str, tab: str) -> None:
    """Jump to the Study page with a topic pre-selected. tab: Learn / Flashcards / Quiz."""
    st.session_state["sel_study_subject"] = subject_id
    st.session_state["sel_study_topic"] = topic_id
    st.session_state["study_tab"] = tab
    st.session_state.page = PAGE_STUDY


def open_planner(tab: str) -> None:
    st.session_state["planner_tab"] = tab
    st.session_state.page = PAGE_PLANNER


def reset_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(WIDGET_PREFIXES) or key in ("card_session", "quiz_run", "focus", "subj_view", "subj_sid"):
            del st.session_state[key]


def pick_topic(prefix: str):
    """Subject + topic selectors for the Study page. Returns (subject, topic)."""
    state = S()
    subjects = state["subjects"]
    if not subjects:
        st.info("Add a subject first on the Subjects page.")
        return None, None
    ids = [s["id"] for s in subjects]
    names = {s["id"]: s["name"] for s in subjects}
    sk, tk = f"sel_{prefix}_subject", f"sel_{prefix}_topic"
    if st.session_state.get(sk) not in ids:
        st.session_state.pop(sk, None)
    c1, c2 = st.columns(2, gap="large")
    sid = c1.selectbox("Subject", ids, format_func=names.get, key=sk)
    subject = D.find_subject(state, sid)
    if not subject["topics"]:
        c2.info("This subject has no topics yet. Add its syllabus under Subjects.")
        return subject, None
    tids = [t["id"] for t in subject["topics"]]
    tnames = {t["id"]: t["name"] for t in subject["topics"]}
    if st.session_state.get(tk) not in tids:
        st.session_state.pop(tk, None)
    tid = c2.selectbox("Topic", tids, format_func=tnames.get, key=tk)
    return subject, next(t for t in subject["topics"] if t["id"] == tid)


def week_df(state: dict, days: list[date]) -> pd.DataFrame:
    real = [t for t in state["tasks"] if t["type"] != "break"]
    done = [t for t in real if t["status"] == "done"]
    return pd.DataFrame({
        "Day": [d.strftime("%a %d") for d in days],
        "Planned": [sum(t["duration"] for t in real if t["date"] == d.isoformat()) for d in days],
        "Completed": [sum(t["duration"] for t in done if t["date"] == d.isoformat()) for d in days]})


def studied_topics(state: dict, day: date) -> list[tuple[dict, dict]]:
    """Topics with a finished study session on ``day`` — these unlock a quiz and flashcards."""
    seen, out = set(), []
    for t in state["tasks"]:
        if t["date"] == day.isoformat() and t["type"] == "study" and t["status"] == "done" and t["topic_id"] not in seen:
            subject, topic = D.find_topic(state, t["topic_id"])
            if topic:
                seen.add(t["topic_id"])
                out.append((D.find_subject(state, t["subject_id"]) or subject, topic))
    return out


# --------------------------------------------------------------------------- #
# Callbacks (run BEFORE the next rerun, so state is always fresh when the page redraws)
# --------------------------------------------------------------------------- #
def cb_load_demo() -> None:
    D.load_demo(S())
    reset_widget_state()
    G.update_badges(S(), date.today())
    save()
    flash("Demo data loaded: Mathematics, Physics and Python. Next: open Planner and generate your plan.", "info")


def cb_reset() -> None:
    S().clear()
    S().update(D.default_state())
    reset_widget_state()
    save()
    flash("All data erased.", "info")


def cb_set_key() -> None:
    ai.set_key(st.session_state.get("sel_api_key", ""))


def cb_generate(days: int | None = None, from_now: bool = False) -> None:
    state = S()
    days = days or state["settings"].get("plan_days", 7)
    from_minute = None
    if from_now:
        now = datetime.now()
        from_minute = now.hour * 60 + now.minute
    summary = P.generate_plan(state, date.today(), days, from_minute)
    save()
    st.session_state.last_summary = summary
    flash(f"Plan generated: {summary['tasks']} tasks, {D.fmt_minutes(summary['minutes'])} of study.")


def cb_generate_and_open() -> None:
    cb_generate()
    open_planner("Week plan")


def cb_complete(task_id: str) -> None:
    for m in P.complete_task(S(), task_id):
        flash(m, "success")
    save()


def cb_undo(task_id: str) -> None:
    P.undo_task(S(), task_id)
    save()


def cb_miss(task_id: str, status: str) -> None:
    result = P.miss_task(S(), task_id, status=status)
    save()
    if not result:
        return
    t, moved = result["task"], result["moved_to"]
    verb = "missed" if status == "missed" else "skipped"
    if moved:
        when = date.fromisoformat(moved["date"]).strftime("%a %d %b")
        flash(f"“{t['title']}” {verb}. Rescheduled to {when}, {moved['start']}–{moved['end']}. The rest of your plan was rebalanced.", "warning")
    else:
        flash(f"“{t['title']}” {verb}. There was no free slot before the exam. Check the Week plan for details.", "warning")


# ---- focus timer (whole page becomes a timer) ----
def cb_start_focus(minutes: int, label: str, task_id: str | None = None) -> None:
    st.session_state.focus = {"minutes": int(minutes), "label": label, "task_id": task_id,
                              "start": time.time(), "done": False}


def cb_start_from_dashboard() -> None:
    choice = st.session_state.get("dash_preset") or "25 min"
    minutes = int(st.session_state.get("dash_custom", 25)) if choice == "Custom" else int(choice.split()[0])
    task_id = st.session_state.get("dash_task")
    task = D.find_task(S(), task_id) if task_id else None
    cb_start_focus(minutes, task["title"] if task else "Focus session", task_id if task else None)


def cb_start_task(task_id: str) -> None:
    t = D.find_task(S(), task_id)
    if t:
        cb_start_focus(t["duration"], t["title"], task_id)


def cb_start_next() -> None:
    t = P.next_task(S(), date.today())
    if t:
        cb_start_task(t["id"])


def cb_exit_focus() -> None:
    st.session_state.pop("focus", None)


def cb_finish_focus_task() -> None:
    f = st.session_state.get("focus") or {}
    if f.get("task_id"):
        cb_complete(f["task_id"])
    cb_exit_focus()


# ---- subjects ----
def cb_open_subject(sid: str) -> None:
    st.session_state.subj_view, st.session_state.subj_sid = "detail", sid
    st.session_state.pop("subj_new", None)


def cb_subject_view(view: str) -> None:
    st.session_state.subj_view = view
    st.session_state.pop("subj_new", None)


def cb_delete_subject(sid: str) -> None:
    state = S()
    state["subjects"] = [s for s in state["subjects"] if s["id"] != sid]
    state["tasks"] = [t for t in state["tasks"] if t["subject_id"] != sid]
    state["notes"].pop(sid, None)
    save()
    flash("Subject deleted.", "info")


def cb_add_topics(sid: str, text_key: str, minutes_key: str, auto_key: str) -> None:
    state = S()
    subject = D.find_subject(state, sid)
    names = SY.parse_topics(st.session_state.get(text_key, ""))
    existing = {t["name"].lower() for t in subject["topics"]}
    names = [n for n in names if n.lower() not in existing]
    if not names:
        flash("No new topics found. Type one topic per line.", "warning")
        return
    minutes = int(st.session_state.get(minutes_key, D.default_topic_minutes(subject)))
    if subject["est_hours"] > 0 and st.session_state.get(auto_key, False):
        total = len(subject["topics"]) + len(names)
        minutes = max(15, min(180, round(subject["est_hours"] * 60 / total / 5) * 5))
    subject["topics"].extend(D.make_topic(n, minutes) for n in names)
    st.session_state[text_key] = ""
    save()
    flash(f"Added {len(names)} topic(s) to {subject['name']}. Regenerate your plan to include them.")


def cb_move_topic(sid: str, index: int, delta: int) -> None:
    topics = D.find_subject(S(), sid)["topics"]
    j = index + delta
    if 0 <= j < len(topics):
        topics[index], topics[j] = topics[j], topics[index]
        save()


def cb_delete_topic(sid: str, tid: str) -> None:
    subject = D.find_subject(S(), sid)
    subject["topics"] = [t for t in subject["topics"] if t["id"] != tid]
    S()["tasks"] = [t for t in S()["tasks"] if not (t["topic_id"] == tid and t["status"] in ("pending", "break"))]
    S()["materials"].pop(tid, None)
    save()


def cb_remove_note(sid: str, index: int) -> None:
    notes = S()["notes"].get(sid, [])
    if 0 <= index < len(notes):
        notes.pop(index)
        save()


def cb_add_holiday() -> None:
    d = st.session_state.get("av_new_holiday")
    holidays = S()["availability"]["holiday_dates"]
    if d and d.isoformat() not in holidays:
        holidays.append(d.isoformat())
        holidays.sort()
        save()


def cb_remove_holiday(iso: str) -> None:
    S()["availability"]["holiday_dates"].remove(iso)
    save()


def cb_mark_understood(topic_id: str) -> None:
    _, topic = D.find_topic(S(), topic_id)
    topic["status"] = "Completed"
    G.update_badges(S(), date.today())
    save()
    flash("Marked as understood. A quiz and a revision session will be added next time you generate the plan.")


# ---- flashcards ----
def cb_start_cards(subject_id: str, topic_id: str, limit: int) -> None:
    subject, topic = D.find_subject(S(), subject_id), D.find_topic(S(), topic_id)[1]
    queue = L.review_queue(S(), subject, topic, limit)
    st.session_state.card_session = {"topic_id": topic_id, "queue": queue, "idx": 0,
                                     "flipped": False, "known": 0, "review": 0}


def cb_flip() -> None:
    st.session_state.card_session["flipped"] = True


def cb_rate_card(known: bool) -> None:
    sess = st.session_state.card_session
    L.record_card(S(), sess["topic_id"], sess["queue"][sess["idx"]], known)
    sess["known" if known else "review"] += 1
    sess["idx"] += 1
    sess["flipped"] = False
    save()


def cb_end_cards() -> None:
    st.session_state.pop("card_session", None)


# ---- quiz ----
def cb_start_quiz(subject_id: str, topic_id: str, n: int) -> None:
    subject, topic = D.find_subject(S(), subject_id), D.find_topic(S(), topic_id)[1]
    pool = L.quiz_pool(S(), subject, topic)
    st.session_state.quiz_run = {
        "subject_id": subject_id, "topic_id": topic_id,
        "questions": L.prepare_quiz(pool, n, seed=random.randrange(10**6)),
        "idx": 0, "checked": False, "correct": 0, "last_correct": None, "finished": False,
        "nonce": random.randrange(10**6), "result": None,
    }


def cb_check_answer(key: str) -> None:
    run = st.session_state.quiz_run
    choice = st.session_state.get(key)
    if choice is None:
        return
    q = run["questions"][run["idx"]]
    run["last_correct"] = choice == q["options"][q["answer"]]
    run["correct"] += int(run["last_correct"])
    run["checked"] = True


def cb_next_question() -> None:
    run = st.session_state.quiz_run
    if run["idx"] + 1 >= len(run["questions"]):
        run["result"] = L.finish_quiz(S(), run["subject_id"], run["topic_id"], run["correct"], len(run["questions"]))
        run["finished"] = True
        save()
    else:
        run["idx"] += 1
        run["checked"] = False
        run["last_correct"] = None


def cb_end_quiz() -> None:
    st.session_state.pop("quiz_run", None)


# --------------------------------------------------------------------------- #
# Init + sidebar
# --------------------------------------------------------------------------- #
def init() -> None:
    if "state" not in st.session_state:
        st.session_state.state = D.load_state()
        st.session_state.page = PAGE_DASH
    state, today = S(), date.today()
    if st.session_state.get("checked_on") != today.isoformat():
        st.session_state.checked_on = today.isoformat()
        overdue = P.mark_overdue(state, today)
        if overdue:
            P.generate_plan(state, today, state["settings"].get("plan_days", 7))
            flash(f"{overdue} task(s) from earlier days were missed. Your remaining work was rescheduled automatically.", "warning")
        save()


def sidebar() -> None:
    state, today = S(), date.today()
    with st.sidebar:
        st.markdown("<div class='brand'>Smart Study<br>Planner</div><div class='brand-sub'>Plan well. Learn deeply. Stay consistent.</div>",
                    unsafe_allow_html=True)
        st.radio("Navigate", PAGES, key="page", label_visibility="collapsed")
        lvl = G.level_info(state["gamification"]["points"])
        st.markdown(f"<div class='side-stat'><b>{G.current_streak(state, today)}</b> day streak<br>"
                    f"<b>{state['gamification']['points']}</b> points &nbsp;·&nbsp; Level {lvl['level']}</div>", unsafe_allow_html=True)
        with st.expander("Settings and data"):
            st.text_input("Anthropic API key (optional)", type="password", key="sel_api_key", on_change=cb_set_key,
                          help="Needed only to read handwriting and to search the web for flashcards. Kept in memory, never saved.")
            st.caption("AI features are on." if ai.available() else "AI features are off. Typed, PDF, DOCX and TXT notes still work.")
            st.button("Load demo data", on_click=cb_load_demo, width="stretch")
            confirm = st.checkbox("I want to erase everything", key="sel_confirm_reset")
            st.button("Reset all data", on_click=cb_reset, disabled=not confirm, width="stretch")


# --------------------------------------------------------------------------- #
# Focus timer: the whole page becomes the timer until it ends or the user exits
# --------------------------------------------------------------------------- #
@st.fragment(run_every=1)
def focus_clock() -> None:
    f = st.session_state.get("focus")
    if not f:
        return
    total = max(f["minutes"] * 60, 1)
    remaining = max(0.0, total - (time.time() - f["start"]))
    m, s = divmod(int(remaining + 0.999), 60)
    note = "Session complete. Well done." if remaining <= 0 else f"of {f['minutes']} minutes"
    st.markdown(
        f"<div class='focus-wrap'><div class='focus-label'>{T.esc(f['label'])}</div>"
        f"<div style='position:relative;width:320px;height:320px'>{T.ring_svg(1 - remaining / total)}"
        f"<div class='focus-time' style='position:absolute;inset:0;display:flex;align-items:center;justify-content:center'>{m:02d}:{s:02d}</div></div>"
        f"<div class='muted' style='margin-top:1.4rem;font-size:1.05rem'>{note}</div></div>", unsafe_allow_html=True)
    if remaining <= 0 and not f["done"]:
        f["done"] = True
        st.rerun(scope="app")


def page_focus() -> None:
    f = st.session_state["focus"]
    focus_clock()
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if f["done"] and f.get("task_id"):
            st.button("Mark task complete and exit", type="primary", on_click=cb_finish_focus_task, width="stretch")
        st.button("Exit timer", on_click=cb_exit_focus, width="stretch", icon=":material/close:")


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def page_dashboard() -> None:
    state, today = S(), date.today()
    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    T.page_header(greeting, today.strftime("%A, %d %B %Y"))

    if not state["subjects"]:
        with T.card():
            T.section("Let's get you started")
            st.markdown("Add your subjects and exam dates, then their syllabus, then set your free hours. "
                        "The planner builds your schedule from there.")
            c1, c2, _ = st.columns([1.3, 1.3, 2])
            c1.button("Add my first subject", type="primary", on_click=lambda: (go(PAGE_SUBJECTS), cb_subject_view("add")),
                      width="stretch", icon=":material/add:")
            c2.button("Try with demo data", on_click=cb_load_demo, width="stretch")
        return

    stats = G.day_stats(state, today)
    avail = P.available_minutes(state, today)
    c = st.columns(4, gap="medium")
    with c[0]:
        T.stat("Planned today", D.fmt_minutes(stats["planned_min"]), f"{D.fmt_minutes(avail)} free to study")
    with c[1]:
        T.stat("Completed", f"{stats['pct']:.0f}%", f"{stats['n_done']} of {stats['n_total']} tasks")
    with c[2]:
        T.stat("Streak", f"{G.current_streak(state, today)} days", G.streak_message(state, today) or "Keep it going")
    with c[3]:
        T.stat("Points", state["gamification"]["points"], f"Level {G.level_info(state['gamification']['points'])['level']}")

    left, right = st.columns([3, 2], gap="large")
    with left:
        with T.card():
            T.section("Today's schedule")
            tasks = sorted((t for t in state["tasks"] if t["date"] == today.isoformat() and t["type"] != "break"), key=lambda t: t["start"])
            if tasks:
                st.markdown("<div>" + "".join(
                    T.row(f"{t['start']} – {t['end']}", t["title"], f"{TYPE_LABEL[t['type']]} · {t['duration']} min", t["status"])
                    for t in tasks) + "</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='muted'>Nothing planned for today. You have {D.fmt_minutes(avail)} of free study time.</div>",
                            unsafe_allow_html=True)
            b1, b2 = st.columns(2)
            b1.button("Generate plan", on_click=cb_generate_and_open, width="stretch", icon=":material/auto_awesome:")
            b2.button("Start next task", on_click=cb_start_next, disabled=P.next_task(state, today) is None,
                      width="stretch", icon=":material/play_arrow:")
    with right:
        with T.card():
            T.section("Start studying", "Pick a length. The whole screen becomes your timer.")
            st.session_state.setdefault("dash_preset", "25 min")
            st.segmented_control("Length", ["15 min", "25 min", "45 min", "60 min", "90 min", "Custom"], key="dash_preset",
                                 label_visibility="collapsed")
            if st.session_state.get("dash_preset") == "Custom":
                st.number_input("Minutes", 5, 240, 30, step=5, key="dash_custom")
            pending = [t for t in tasks if t["status"] == "pending"] if tasks else []
            if pending:
                st.selectbox("Working on", [None] + [t["id"] for t in pending], key="dash_task",
                             format_func=lambda i: "Free study" if i is None else D.find_task(state, i)["title"])
            st.button("Start studying", type="primary", on_click=cb_start_from_dashboard, width="stretch", icon=":material/timer:")

    a, b = st.columns(2, gap="large")
    upcoming = [s for s in state["subjects"] if D.days_until(s["exam_date"], today) >= 0]
    with a:
        with T.card():
            if upcoming:
                nxt = min(upcoming, key=lambda s: s["exam_date"])
                days = D.days_until(nxt["exam_date"], today)
                T.section("Next exam")
                st.markdown(f"### {nxt['name']}")
                st.caption(f"{date.fromisoformat(nxt['exam_date']).strftime('%a %d %b')}  ·  "
                           f"{'today' if days == 0 else f'in {days} day' + ('s' if days != 1 else '')}")
            else:
                T.section("Next exam")
                st.caption("No upcoming exams.")
    with b:
        with T.card():
            T.section("Top priority")
            ranked = P.rank_topics(state, today)
            if ranked:
                st.markdown(f"### {ranked[0]['subject']['name']}: {ranked[0]['topic']['name']}")
                st.caption(ranked[0]["reason"])
            else:
                st.caption("No unfinished topics.")

    with T.card():
        T.section("Your last 7 days", "Minutes planned against minutes completed.")
        days7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
        C.show(C.trend(week_df(state, days7), "Day", {"Completed": C.CORAL, "Planned": C.VIOLET}))


# --------------------------------------------------------------------------- #
# Subjects: list -> add subject -> syllabus & notes (one continuous flow)
# --------------------------------------------------------------------------- #
def subject_form(prefix: str, subject: dict | None = None) -> None:
    state, today = S(), date.today()
    editing = subject is not None
    with st.form(f"{prefix}_form", clear_on_submit=not editing, border=False):
        name = st.text_input("Subject name", value=subject["name"] if editing else "", key=f"{prefix}_name")
        c1, c2 = st.columns(2, gap="large")
        exam = c1.date_input("Exam date", key=f"{prefix}_exam",
                             value=date.fromisoformat(subject["exam_date"]) if editing else today + timedelta(days=14))
        method = c2.selectbox("Preferred study method", D.METHODS, key=f"{prefix}_method",
                              index=D.METHODS.index(subject["method"]) if editing and subject["method"] in D.METHODS else 0)
        c3, c4, c5 = st.columns(3, gap="large")
        diff = c3.slider("Difficulty (1–5)", 1, 5, subject["difficulty"] if editing else 3, key=f"{prefix}_diff")
        imp = c4.slider("Importance (1–5)", 1, 5, subject["importance"] if editing else 3, key=f"{prefix}_imp")
        prog = c5.slider("Current progress (%)", 0, 100, int(subject["progress"]) if editing else 0, key=f"{prefix}_prog")
        hours = st.number_input("Estimated total study hours (optional)", 0.0, 500.0,
                                float(subject["est_hours"]) if editing else 0.0, step=1.0, key=f"{prefix}_hours")
        submitted = st.form_submit_button("Save changes" if editing else "Continue to syllabus", type="primary",
                                          icon=":material/check:" if editing else ":material/arrow_forward:")
    if not submitted:
        return
    clean = name.strip()
    others = [s["name"].lower() for s in state["subjects"] if not editing or s["id"] != subject["id"]]
    if not clean:
        st.error("Please enter a subject name.")
    elif clean.lower() in others:
        st.error("You already have a subject with that name.")
    elif exam < today:
        st.error("The exam date is in the past.")
    elif editing:
        subject.update(name=clean, exam_date=exam.isoformat(), difficulty=diff, importance=imp,
                       progress=float(prog), est_hours=float(hours), method=method)
        save()
        flash(f"Updated {clean}.")
        st.rerun()
    else:
        new = D.make_subject(clean, exam, diff, imp, prog, hours, method)
        state["subjects"].append(new)
        save()
        st.session_state.subj_view, st.session_state.subj_sid, st.session_state.subj_new = "detail", new["id"], True
        st.rerun()


def page_subjects() -> None:
    view = st.session_state.get("subj_view", "list")
    sid = st.session_state.get("subj_sid")
    if view == "detail" and D.find_subject(S(), sid):
        return subject_detail(D.find_subject(S(), sid))
    if view == "add":
        return subject_add()
    return subject_list()


def subject_list() -> None:
    state, today = S(), date.today()
    h1, h2 = st.columns([4, 1.4], vertical_alignment="bottom")
    with h1:
        T.page_header("Subjects", "Everything you are studying, ordered by what needs attention first.")
    h2.button("New subject", type="primary", icon=":material/add:", width="stretch", on_click=cb_subject_view, args=("add",))
    if not state["subjects"]:
        with T.card():
            st.markdown("<div class='muted'>No subjects yet. Add your first one to begin.</div>", unsafe_allow_html=True)
        return
    sort = st.selectbox("Sort by", ["Exam urgency", "Priority", "Progress (lowest first)"], key="sel_subject_sort")
    keyfn = {"Exam urgency": lambda s: s["exam_date"], "Priority": lambda s: -P.subject_priority(s, today),
             "Progress (lowest first)": D.subject_progress}[sort]
    for s in sorted(state["subjects"], key=keyfn):
        days = D.days_until(s["exam_date"], today)
        prog = D.subject_progress(s)
        done = sum(1 for t in s["topics"] if t["status"] == "Completed")
        when = "exam passed" if days < 0 else "exam today" if days == 0 else f"{days} day{'s' if days != 1 else ''} to go"
        with T.card():
            c1, c2 = st.columns([4, 1.2], vertical_alignment="center")
            with c1:
                st.markdown(f"### {s['name']}")
                st.caption(f"Exam {date.fromisoformat(s['exam_date']).strftime('%d %b %Y')}  ·  {when}  ·  "
                           f"Difficulty {s['difficulty']}/5  ·  Importance {s['importance']}/5")
                st.progress(min(prog / 100, 1.0), text=f"{prog:.0f}% complete  ·  {done} of {len(s['topics'])} topics")
            c2.button("Open", key=f"open_{s['id']}", width="stretch", icon=":material/arrow_forward:",
                      on_click=cb_open_subject, args=(s["id"],))
            with st.expander("Edit or delete"):
                subject_form(f"ed_{s['id']}", s)
                ok = st.checkbox("Yes, delete this subject and its tasks", key=f"ed_{s['id']}_del")
                st.button("Delete subject", key=f"ed_{s['id']}_delbtn", disabled=not ok, on_click=cb_delete_subject, args=(s["id"],))


def subject_add() -> None:
    st.button("Back to subjects", on_click=cb_subject_view, args=("list",), icon=":material/arrow_back:")
    T.page_header("New subject", "Step 1 of 2: tell me about the subject. Next you will add its syllabus.")
    with T.card():
        subject_form("ns")


def read_upload(up) -> tuple[str, str | None]:
    """Text from any upload. Photos and scanned PDFs (handwriting) go through the AI reader."""
    ext = up.name.rsplit(".", 1)[-1].lower()
    if ext in ai.IMAGE_TYPES:
        return ai.read_handwriting(up.getvalue(), ext)
    text, err = SY.extract_text(up)
    if not text and ext == "pdf":
        if ai.available():
            return ai.read_handwriting(up.getvalue(), "pdf")
        return "", "No typed text found, so this looks like a scan or handwriting. Add an API key under Settings to read it."
    return text, err


def subject_detail(subject: dict) -> None:
    state, today, sid = S(), date.today(), subject["id"]
    is_new = st.session_state.get("subj_new", False)
    st.button("Back to subjects", on_click=cb_subject_view, args=("list",), icon=":material/arrow_back:")
    T.page_header(subject["name"], "Step 2 of 2: add the syllabus. You can also add your notes so flashcards and quizzes match what you study."
                  if is_new else "Syllabus, topics and notes for this subject.")

    prog = D.subject_progress(subject)
    c = st.columns(3, gap="medium")
    with c[0]:
        T.stat("Progress", f"{prog:.0f}%", f"{len(subject['topics'])} topics")
    with c[1]:
        T.stat("Exam in", f"{D.days_until(subject['exam_date'], today)} days", date.fromisoformat(subject["exam_date"]).strftime("%d %b %Y"))
    with c[2]:
        T.stat("Syllabus time", D.fmt_minutes(sum(t["est_minutes"] for t in subject["topics"])), "estimated")

    view = tab_control("tp_view", ["Add syllabus", "Topics", "Notes"])

    if view == "Add syllabus":
        auto_key = f"tp_auto_{sid}"
        with T.card():
            T.section("Type or paste topics", "One topic or chapter per line.")
            st.text_area("Topics", key=f"tp_manual_{sid}", height=160, label_visibility="collapsed",
                         placeholder="Limits and Continuity\nDifferentiation\nIntegration")
            m1, m2 = st.columns(2, gap="large")
            m1.number_input("Minutes per topic", 5, 600, D.default_topic_minutes(subject), step=5, key=f"tp_manual_min_{sid}")
            if subject["est_hours"] > 0:
                m2.checkbox(f"Spread my {subject['est_hours']:g} estimated hours across topics", value=True, key=auto_key)
            st.button("Add topics", type="primary", key=f"tp_manual_btn_{sid}", on_click=cb_add_topics,
                      args=(sid, f"tp_manual_{sid}", f"tp_manual_min_{sid}", auto_key))
        with T.card():
            T.section("Upload a syllabus", "PDF, Word, text, or a photo of a printed or handwritten syllabus.")
            up = st.file_uploader("Syllabus file", type=UPLOAD_TYPES, key=f"tp_file_{sid}", label_visibility="collapsed")
            if up is not None:
                sig = f"{up.name}-{up.size}"
                if st.session_state.get(f"tp_sig_{sid}") != sig:
                    with st.spinner("Reading your file..."):
                        text, err = read_upload(up)
                    st.session_state[f"tp_sig_{sid}"] = sig
                    st.session_state[f"tp_err_{sid}"] = err
                    st.session_state[f"tp_extracted_{sid}"] = "\n".join(SY.parse_topics(text))
                if st.session_state.get(f"tp_err_{sid}"):
                    st.warning(st.session_state[f"tp_err_{sid}"] + " You can still type the topics above.")
                else:
                    st.caption("Check the detected topics, fix anything that looks wrong, then confirm.")
                st.text_area("Detected topics (editable)", key=f"tp_extracted_{sid}", height=200)
                st.number_input("Minutes per topic", 5, 600, D.default_topic_minutes(subject), step=5, key=f"tp_file_min_{sid}")
                st.button("Confirm and add topics", type="primary", key=f"tp_file_btn_{sid}", on_click=cb_add_topics,
                          args=(sid, f"tp_extracted_{sid}", f"tp_file_min_{sid}", auto_key))
        if is_new and subject["topics"]:
            st.button("Done, generate my plan", type="primary", icon=":material/auto_awesome:", on_click=cb_generate_and_open)

    elif view == "Topics":
        with T.card():
            if not subject["topics"]:
                st.markdown("<div class='muted'>No topics yet. Add some under Add syllabus.</div>", unsafe_allow_html=True)
            changed = False
            for i, t in enumerate(subject["topics"]):
                cc = st.columns([4, 1.5, 2.2, 0.7, 0.7, 0.7, 1.3], vertical_alignment="center")
                name = cc[0].text_input("Topic", t["name"], key=f"tp_name_{t['id']}", label_visibility="collapsed")
                mins = cc[1].number_input("Minutes", 5, 600, int(t["est_minutes"]), step=5, key=f"tp_min_{t['id']}", label_visibility="collapsed")
                status = cc[2].selectbox("Status", D.STATUSES, index=D.STATUSES.index(t["status"]), key=f"tp_status_{t['id']}",
                                         label_visibility="collapsed")
                cc[3].button(":material/arrow_upward:", key=f"tp_up_{t['id']}", on_click=cb_move_topic, args=(sid, i, -1), disabled=i == 0, help="Move up")
                cc[4].button(":material/arrow_downward:", key=f"tp_dn_{t['id']}", on_click=cb_move_topic, args=(sid, i, 1),
                             disabled=i == len(subject["topics"]) - 1, help="Move down")
                cc[5].button(":material/delete:", key=f"tp_del_{t['id']}", on_click=cb_delete_topic, args=(sid, t["id"]), help="Delete topic")
                cc[6].button("Study", key=f"tp_learn_{t['id']}", on_click=focus_topic, args=(sid, t["id"], "Learn"))
                if (name.strip() and name.strip() != t["name"]) or mins != t["est_minutes"] or status != t["status"]:
                    t["name"], t["est_minutes"], t["status"] = name.strip() or t["name"], int(mins), status
                    changed = True
            if changed:
                save()

    else:
        notes = state["notes"].setdefault(sid, [])
        k = len(notes)          # new widget keys after every save, so the boxes come back empty
        with T.card():
            T.section("Add your notes", "Flashcards and quizzes are built from these first. If a topic is not in your notes, the app searches the web by its name.")
            st.text_area("Paste or type notes", key=f"tp_note_text_{sid}_{k}", height=150, label_visibility="collapsed",
                         placeholder="Integration: the reverse of differentiation...\nDefinite integral is the area under a curve...")
            up = st.file_uploader("Notes file, scan or handwritten photo", type=UPLOAD_TYPES, key=f"tp_note_file_{sid}_{k}")
            if st.button("Save notes", type="primary", key=f"tp_note_btn_{sid}"):
                typed = st.session_state.get(f"tp_note_text_{sid}_{k}", "").strip()
                added = 0
                if typed:
                    notes.append({"name": "Typed notes", "text": typed})
                    added += 1
                if up is not None:
                    with st.spinner("Reading your file. Handwriting can take a few seconds..."):
                        text, err = read_upload(up)
                    if text:
                        notes.append({"name": up.name, "text": text})
                        added += 1
                    else:
                        flash(err or "Nothing readable in that file.", "warning")
                if added:
                    save()
                    flash("Notes saved. Open Study and build flashcards and a quiz for any topic.")
                elif typed == "" and up is None:
                    flash("Type some notes or choose a file first.", "warning")
                st.rerun()
        if notes:
            T.section("Saved notes")
            for i, n in enumerate(notes):
                with st.expander(f"{n['name']}  ·  {len(n['text'].split())} words"):
                    st.text(n["text"][:3000] + ("..." if len(n["text"]) > 3000 else ""))
                    st.button("Remove", key=f"tp_note_rm_{sid}_{i}", on_click=cb_remove_note, args=(sid, i))


# --------------------------------------------------------------------------- #
# Planner: Today / Week plan / Schedule
# --------------------------------------------------------------------------- #
def page_planner() -> None:
    T.page_header("Planner", "Your tasks for the day, the full plan, and the hours you have available.")
    view = tab_control("planner_tab", ["Today", "Week plan", "Schedule"])
    {"Today": view_today, "Week plan": view_plan, "Schedule": view_schedule}[view]()


def view_today() -> None:
    state, today = S(), date.today()
    day = st.date_input("Day", value=today, key="sel_task_day")
    tasks = sorted((t for t in state["tasks"] if t["date"] == day.isoformat()), key=lambda t: t["start"])
    real = [t for t in tasks if t["type"] != "break"]
    if not real:
        with T.card():
            st.markdown("<div class='muted'>No tasks for this day. Generate a plan under Week plan.</div>", unsafe_allow_html=True)
    else:
        stats = G.day_stats(state, day)
        st.progress(min(stats["pct"] / 100, 1.0), text=f"{stats['n_done']} of {stats['n_total']} tasks  ·  {stats['pct']:.0f}% of planned time done")
        for t in tasks:
            if t["type"] == "break":
                st.caption(f"{t['start']} – {t['end']}  ·  Break")
                continue
            with T.card():
                c1, c2 = st.columns([5, 3], vertical_alignment="center", gap="large")
                meta = f"{TYPE_LABEL[t['type']]} · {t['duration']} min · {t['reason']}" + (f" · +{t['points']} pts" if t["status"] == "done" else "")
                c1.markdown(T.row(f"{t['start']} – {t['end']}", t["title"], meta, t["status"]), unsafe_allow_html=True)
                with c2:
                    b = st.columns(4)
                    if t["status"] == "pending":
                        b[0].button(":material/play_arrow:", key=f"start_{t['id']}", help="Start focus timer", on_click=cb_start_task, args=(t["id"],), width="stretch")
                        b[1].button(":material/check:", key=f"done_{t['id']}", help="Mark complete", type="primary", on_click=cb_complete, args=(t["id"],), width="stretch")
                        b[2].button(":material/skip_next:", key=f"skip_{t['id']}", help="Skip and reschedule", on_click=cb_miss, args=(t["id"], "skipped"), width="stretch")
                        b[3].button(":material/close:", key=f"miss_{t['id']}", help="Missed, reschedule", on_click=cb_miss, args=(t["id"], "missed"), width="stretch")
                    elif t["status"] == "done":
                        b[0].button("Undo", key=f"undo_{t['id']}", on_click=cb_undo, args=(t["id"],))
                    else:
                        st.caption("Rescheduled automatically")
                if t["topic_id"] and t["status"] == "pending":
                    tab = {"study": "Learn", "revision": "Flashcards", "quiz": "Quiz"}[t["type"]]
                    st.button({"study": "Open topic", "revision": "Open flashcards", "quiz": "Open quiz"}[t["type"]], key=f"open_{t['id']}",
                              on_click=focus_topic, args=(t["subject_id"], t["topic_id"], tab))

    # Quizzes and flashcards unlock for anything studied that day
    T.section("Test what you studied", "Finish a study session and its quiz and flashcards appear here.")
    studied = studied_topics(state, day)
    if not studied:
        st.markdown("<div class='muted'>Nothing studied yet on this day.</div>", unsafe_allow_html=True)
    for subject, topic in studied:
        taken = [q for q in state["quiz_history"] if q["topic_id"] == topic["id"] and q["date"] == day.isoformat()]
        with T.card():
            c1, c2, c3 = st.columns([4, 1.2, 1.4], vertical_alignment="center")
            c1.markdown(f"**{topic['name']}**  \n<span class='muted'>{T.esc(subject['name'])}"
                        + (f" · quiz today: {taken[-1]['score']}/{taken[-1]['total']}" if taken else " · quiz not taken yet") + "</span>",
                        unsafe_allow_html=True)
            c2.button("Flashcards", key=f"ts_c_{topic['id']}", on_click=focus_topic, args=(subject["id"], topic["id"], "Flashcards"), width="stretch")
            c3.button("Take quiz", key=f"ts_q_{topic['id']}", type="primary", on_click=focus_topic, args=(subject["id"], topic["id"], "Quiz"), width="stretch")


def plan_table(tasks: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Time": f"{t['start']} – {t['end']}", "Task": t["title"], "Type": TYPE_LABEL[t["type"]],
        "Duration": f"{t['duration']} min", "Why": t["reason"],
        "Status": "" if t["type"] == "break" else {"pending": "Upcoming", "done": "Done", "missed": "Missed", "skipped": "Skipped"}[t["status"]],
    } for t in sorted(tasks, key=lambda t: t["start"])])


def view_plan() -> None:
    state, today = S(), date.today()
    if not state["subjects"]:
        st.info("Add subjects and topics first.")
        return
    with T.card():
        c1, c2, c3 = st.columns([2, 3, 1.4], vertical_alignment="center", gap="large")
        horizon = c1.radio("Plan for", ["Today", "This week"], index=1, horizontal=True, key="sel_horizon")
        from_now = c2.checkbox("Skip time that has already passed today", key="sel_from_now")
        c3.button("Generate plan", type="primary", on_click=cb_generate, args=(1 if horizon == "Today" else 7, from_now),
                  width="stretch", icon=":material/auto_awesome:")
        st.caption("Generating replaces upcoming pending tasks. Completed and missed tasks stay as history.")
    summary = st.session_state.get("last_summary")
    if summary:
        for name in summary["no_topics"]:
            st.warning(f"{name} has no syllabus topics yet. Add some under Subjects.")
        for name in summary["expired"]:
            st.warning(f"{name}: the exam date is today or in the past, so it was not planned.")
        for u in summary["unscheduled"]:
            st.warning(f"Not enough free time before the exam for {u['subject']}: {u['topic']} ({u['minutes']} min unplanned). "
                       "Add study windows or raise the daily capacity.")
    upcoming = sorted({t["date"] for t in state["tasks"] if t["date"] >= today.isoformat() and t["type"] != "break"})
    if not upcoming:
        st.info("No plan yet. Press Generate plan.")
    for iso in upcoming[:7]:
        day_tasks = [t for t in state["tasks"] if t["date"] == iso]
        mins = sum(t["duration"] for t in day_tasks if t["type"] != "break")
        with st.expander(f"{date.fromisoformat(iso).strftime('%A, %d %B')}  ·  {D.fmt_minutes(mins)} planned", expanded=(iso == upcoming[0])):
            st.dataframe(plan_table(day_tasks), hide_index=True, width="stretch")
    with st.expander("Why this order? (priority ranking)"):
        ranked = P.rank_topics(state, today)
        if ranked:
            st.dataframe(pd.DataFrame([{"Subject": r["subject"]["name"], "Topic": r["topic"]["name"], "Priority": round(r["score"], 1),
                                        "Exam in (days)": r["days_left"], "Why": r["reason"]} for r in ranked]),
                         hide_index=True, width="stretch")
        else:
            st.write("No unfinished topics.")
        st.caption(f"Weights: urgency up to {P.W['urgency_max']}, difficulty ×{P.W['difficulty']}, importance ×{P.W['importance']}, "
                   f"progress gap ×{P.W['gap']}, weak topic +{P.W['weak']}, in-progress +{P.W['in_progress']}. Edit W in planner.py to tune.")


def window_editor(key: str, windows: list, rows: int, default: tuple[str, str]) -> list:
    out = []
    for i in range(rows):
        cur = windows[i] if i < len(windows) else None
        a, b = (cur or default)
        c1, c2, c3 = st.columns([1, 2, 2], vertical_alignment="center")
        on = c1.checkbox("On", value=cur is not None, key=f"{key}_on{i}")
        s = c2.time_input("Start", dtime(*map(int, a.split(":"))), key=f"{key}_s{i}", step=900, label_visibility="collapsed")
        e = c3.time_input("End", dtime(*map(int, b.split(":"))), key=f"{key}_e{i}", step=900, label_visibility="collapsed")
        if on:
            out.append([s.strftime("%H:%M"), e.strftime("%H:%M")])
    return out


def view_schedule() -> None:
    state, today = S(), date.today()
    av = state["availability"]
    st.caption("Tell the planner when you can study. Blocked periods such as college or travel are removed from your study windows.")
    labels = {"weekday": "Mon–Fri", "saturday": "Saturday", "sunday": "Sunday", "holiday": "Holiday"}
    with T.card():
        with st.form("av_form", border=False):
            tabs = st.tabs([labels[d] for d in D.DAY_TYPES])
            new_w, new_b = {}, {}
            for tab, dt in zip(tabs, D.DAY_TYPES):
                with tab:
                    st.markdown("**Study windows**")
                    new_w[dt] = window_editor(f"av_{dt}_study", av["windows"][dt], 3, ("18:00", "21:00"))
                    st.markdown("**Blocked time** (college, travel, commitments)")
                    new_b[dt] = window_editor(f"av_{dt}_block", av["blocked"][dt], 3, ("09:00", "16:00"))
            c1, c2 = st.columns(2, gap="large")
            max_s = c1.slider("Max session (min)", 20, 120, av["max_session_min"], step=5, key="av_max")
            brk = c2.slider("Break (min)", 0, 30, av["break_min"], step=5, key="av_break")
            c3, c4 = st.columns(2, gap="large")
            cap = c3.slider("Daily capacity (hours)", 1.0, 12.0, av["daily_cap_min"] / 60, step=0.5, key="av_cap")
            target = c4.slider("Daily target for streak (%)", 30, 100, state["settings"]["daily_target_pct"], step=10, key="av_target")
            holiday_mode = st.toggle("Holiday mode: use the Holiday windows every day", value=av["holiday_mode"], key="av_holmode")
            submitted = st.form_submit_button("Save schedule", type="primary", icon=":material/save:")
    if submitted:
        av["windows"], av["blocked"] = new_w, new_b
        av.update(max_session_min=max_s, break_min=brk, daily_cap_min=int(cap * 60), holiday_mode=holiday_mode)
        state["settings"]["daily_target_pct"] = target
        save()
        flash("Schedule saved. Regenerate your plan to apply it.")
        st.rerun()

    with T.card():
        T.section("Holiday dates")
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        c1.date_input("Add a holiday", value=today, key="av_new_holiday")
        c2.button("Add holiday", on_click=cb_add_holiday, width="stretch")
        for iso in av["holiday_dates"]:
            h1, h2 = st.columns([4, 1], vertical_alignment="center")
            h1.write(date.fromisoformat(iso).strftime("%A, %d %B %Y"))
            h2.button("Remove", key=f"av_rm_{iso}", on_click=cb_remove_holiday, args=(iso,))
    with T.card():
        T.section("The next 7 days, as the planner sees them")
        rows = []
        for i in range(7):
            d = today + timedelta(days=i)
            wins = P.get_windows(av, d)
            rows.append({"Day": d.strftime("%a %d %b"), "Type": P.day_type(av, d).title(),
                         "Free windows": ", ".join(f"{D.to_hhmm(a)}–{D.to_hhmm(b)}" for a, b in wins) or "None",
                         "Usable": D.fmt_minutes(P.available_minutes(state, d))})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# --------------------------------------------------------------------------- #
# Study: Learn / Flashcards / Quiz for one topic
# --------------------------------------------------------------------------- #
def page_study() -> None:
    state = S()
    T.page_header("Study", "Learn a topic, drill it with flashcards, then test yourself.")
    subject, topic = pick_topic("study")
    if not topic:
        return
    mat = L.get_material(state, topic)
    notes = state["notes"].get(subject["id"], [])
    with T.card():
        c1, c2 = st.columns([3, 1.6], vertical_alignment="center", gap="large")
        source = mat["source"] if mat else ("built-in" if L.find_entry(subject["name"], topic["name"]) else "basic checklist")
        c1.markdown(f"**Material source:** <span class='chip info'>{T.esc(source)}</span><br>"
                    f"<span class='muted'>{'Built from your notes where they cover this topic, otherwise from a web search on the topic name.' if (notes or ai.available()) else 'Add notes under Subjects, or an API key under Settings, to get flashcards and quizzes tailored to this topic.'}</span>",
                    unsafe_allow_html=True)
        if c2.button("Rebuild from notes or web" if mat else "Build flashcards and quiz", type="primary", width="stretch",
                     icon=":material/auto_awesome:", key="study_build"):
            with st.spinner("Building your flashcards and quiz..."):
                new, err = ai.build_material(subject["name"], topic["name"], notes)
            if new:
                state["materials"][topic["id"]] = new
                st.session_state.pop("card_session", None)
                save()
                flash(f"Created {len(new['cards'])} flashcards and {len(new['quiz'])} quiz questions from {new['source']}.")
            else:
                flash(err or "Could not build material.", "warning")
            st.rerun()
    view = tab_control("study_tab", ["Learn", "Flashcards", "Quiz"])
    {"Learn": study_learn, "Flashcards": study_cards, "Quiz": study_quiz}[view](subject, topic)


def study_learn(subject: dict, topic: dict) -> None:
    content = L.get_content(subject, topic, S())
    with T.card():
        st.markdown(f"## {topic['name']}")
        st.caption(f"{subject['name']}  ·  {topic['status']}  ·  {content['source']} content")
        st.markdown(content["summary"])
        T.section("Key points")
        for p in content["points"]:
            st.markdown(f"- {p}")
        if content["definitions"]:
            T.section("Definitions and formulas")
            for term, text in content["definitions"]:
                st.markdown(f"- **{term}**: {text}")
        if topic.get("weak"):
            st.warning("This topic was flagged as a weak area after a quiz. Review it, then retake the quiz.")
    c1, c2, c3 = st.columns(3, gap="medium")
    c1.button("Flashcards", on_click=focus_topic, args=(subject["id"], topic["id"], "Flashcards"), width="stretch")
    c2.button("Take a quiz", on_click=focus_topic, args=(subject["id"], topic["id"], "Quiz"), width="stretch")
    c3.button("Mark as understood", on_click=cb_mark_understood, args=(topic["id"],), disabled=topic["status"] == "Completed",
              type="primary", width="stretch", icon=":material/check:")


def study_cards(subject: dict, topic: dict) -> None:
    state, today = S(), date.today()
    target = state["settings"]["daily_card_target"]
    reviewed = state["card_log"].get(today.isoformat(), 0)
    st.progress(min(reviewed / target, 1.0), text=f"Daily target: {reviewed} of {target} cards reviewed")
    sess = st.session_state.get("card_session")
    if sess and sess["topic_id"] != topic["id"]:
        st.session_state.pop("card_session")
        sess = None
    cards = L.get_cards(state, subject, topic)
    by_front = {c["front"]: c for c in cards}

    if not sess:
        prog = state["flashcards"].get(topic["id"], {})
        known = sum(1 for c in cards if prog.get(c["front"], {}).get("known"))
        with T.card():
            st.markdown(f"**{len(cards)}** cards  ·  **{known}** known  ·  **{len(cards) - known}** to learn. Missed cards come first.")
            n = st.number_input("Cards in this session", 1, max(len(cards), 1), min(target, len(cards)), key="sel_cards_n")
            st.button("Start review", type="primary", icon=":material/play_arrow:", on_click=cb_start_cards,
                      args=(subject["id"], topic["id"], int(n)))
    elif sess["idx"] >= len(sess["queue"]):
        with T.card():
            st.success(f"Session complete: {sess['known']} known, {sess['review']} to review.")
            st.button("Done", on_click=cb_end_cards, type="primary")
    else:
        key = sess["queue"][sess["idx"]]
        card = by_front.get(key)
        if card is None:
            cb_rate_card(True)
            st.rerun()
        p = state["flashcards"].get(topic["id"], {}).get(key, {})
        st.progress(sess["idx"] / len(sess["queue"]), text=f"Card {sess['idx'] + 1} of {len(sess['queue'])}  ·  seen {p.get('reviews', 0)} times before")
        with T.card():
            st.markdown(f"<div style='text-align:center;padding:2.2rem 1rem'><div style='font-family:Fraunces,serif;font-size:1.7rem'>{T.esc(card['front'])}</div>"
                        + (f"<hr style='border:0;border-top:1px solid var(--line);margin:1.6rem auto;width:40%'><div style='font-size:1.2rem;color:var(--coral)'>{T.esc(card['back'])}</div>"
                           if sess["flipped"] else "") + "</div>", unsafe_allow_html=True)
        if not sess["flipped"]:
            st.button("Flip card", on_click=cb_flip, width="stretch", type="primary", icon=":material/flip:")
        else:
            a, b = st.columns(2, gap="medium")
            a.button("I knew it", on_click=cb_rate_card, args=(True,), width="stretch", type="primary", icon=":material/check:")
            b.button("Needs review", on_click=cb_rate_card, args=(False,), width="stretch", icon=":material/replay:")
        st.button("End session", on_click=cb_end_cards)

    with st.expander("Add your own card"):
        with st.form(f"tp_card_form_{topic['id']}", clear_on_submit=True, border=False):
            front = st.text_input("Front (question)")
            back = st.text_input("Back (answer)")
            if st.form_submit_button("Add card"):
                if L.add_custom_card(state, topic["id"], front, back):
                    save()
                    flash("Card added.")
                    st.rerun()
                else:
                    st.error("Fill in both sides.")


def study_quiz(subject: dict, topic: dict) -> None:
    state = S()
    run = st.session_state.get("quiz_run")
    if run is not None and run["topic_id"] != topic["id"] and not run["finished"]:
        st.session_state.pop("quiz_run")
        run = None

    if run is None:
        pool = L.quiz_pool(state, subject, topic)
        with T.card():
            if not pool:
                st.markdown("<div class='muted'>No quiz for this topic yet. Press Build flashcards and quiz above, or add 4 or more of your own flashcards.</div>",
                            unsafe_allow_html=True)
                return
            n = len(pool) if len(pool) <= 3 else st.slider("Number of questions", 3, min(10, len(pool)), min(5, len(pool)), key="sel_quiz_n")
            st.button("Start quiz", type="primary", icon=":material/play_arrow:", on_click=cb_start_quiz, args=(subject["id"], topic["id"], n))
            history = [q for q in state["quiz_history"] if q["topic_id"] == topic["id"]]
            if history:
                st.caption("Previous scores: " + ", ".join(f"{q['score']}/{q['total']}" for q in history[-5:]))
        return

    questions = run["questions"]
    if run["finished"]:
        res = run["result"]
        with T.card():
            st.markdown(f"## Score: {run['correct']} of {len(questions)}  ({res['pct']:.0f}%)")
            for m in res["messages"]:
                st.success(m)
            _, qt = D.find_topic(state, run["topic_id"])
            if res["weak"]:
                st.warning(f"Weak area: {qt['name']}. It has been flagged and the planner will add revision for it.")
                c1, c2 = st.columns(2)
                c1.button("Review weak topic", on_click=focus_topic, args=(run["subject_id"], run["topic_id"], "Learn"))
                c2.button("Update my plan now", on_click=cb_generate)
            elif res["pct"] >= 80:
                st.balloons()
                st.success("Excellent. You are exam-ready on this topic.")
            else:
                st.info("Good effort. One more pass through the flashcards should lock it in.")
            st.button("Finish", on_click=cb_end_quiz, type="primary")
        return

    idx = run["idx"]
    q = questions[idx]
    key = f"quizrun_{run['nonce']}_{idx}"
    st.progress(idx / len(questions), text=f"Question {idx + 1} of {len(questions)}")
    with T.card():
        st.radio(q["q"], q["options"], index=None, key=key, disabled=run["checked"])
        if not run["checked"]:
            st.button("Check answer", on_click=cb_check_answer, args=(key,), disabled=st.session_state.get(key) is None, type="primary")
        else:
            if run["last_correct"]:
                st.success("Correct.")
            else:
                st.error(f"Not quite. The answer is: {q['options'][q['answer']]}")
            st.caption(q["explanation"])
            st.button("See results" if idx + 1 >= len(questions) else "Next question", on_click=cb_next_question, type="primary")
    st.button("Quit quiz", on_click=cb_end_quiz)


# --------------------------------------------------------------------------- #
# Progress: Overview / Subjects / Rewards
# --------------------------------------------------------------------------- #
def page_progress() -> None:
    T.page_header("Progress", "How far you have come, subject by subject.")
    view = tab_control("progress_tab", ["Overview", "Subjects", "Rewards"])
    {"Overview": progress_overview, "Subjects": progress_subjects, "Rewards": progress_rewards}[view]()


def progress_overview() -> None:
    state, today = S(), date.today()
    if not state["subjects"]:
        st.info("Nothing to show yet.")
        return
    all_topics = [t for s in state["subjects"] for t in s["topics"]]
    total_min = sum(t["est_minutes"] for t in all_topics) or 1
    overall = sum(D.topic_fraction(t) * t["est_minutes"] for t in all_topics) / total_min * 100
    real = [t for t in state["tasks"] if t["type"] != "break"]
    done = [t for t in real if t["status"] == "done"]
    quizzes = state["quiz_history"]

    c = st.columns(4, gap="medium")
    with c[0]:
        T.stat("Syllabus completed", f"{overall:.0f}%")
    with c[1]:
        T.stat("Study time done", D.fmt_minutes(sum(t["duration"] for t in done if t["type"] == "study")))
    with c[2]:
        T.stat("Tasks done", f"{len(done)} of {len(real)}")
    with c[3]:
        T.stat("Average quiz score", f"{sum(q['pct'] for q in quizzes) / len(quizzes):.0f}%" if quizzes else "None yet")

    left, right = st.columns([2, 3], gap="large")
    with left, T.card():
        T.section("Overall")
        C.show(C.donut(overall))
    with right, T.card():
        T.section("By subject")
        df = pd.DataFrame({"Subject": [s["name"] for s in state["subjects"]], "Progress": [round(D.subject_progress(s)) for s in state["subjects"]], "full": 100})
        C.show(C.hbars(df, "Subject", "Progress", height=max(120, 54 * len(df))))

    with T.card():
        T.section("Study time, last 14 days", "Minutes planned against minutes completed.")
        days14 = [today - timedelta(days=i) for i in range(13, -1, -1)]
        C.show(C.trend(week_df(state, days14), "Day", {"Completed": C.CORAL, "Planned": C.VIOLET}, height=280))
    a, b = st.columns(2, gap="large")
    with a, T.card():
        T.section("Workload ahead")
        ahead = [today + timedelta(days=i) for i in range(7)]
        wl = pd.DataFrame({"Day": [d.strftime("%a %d") for d in ahead],
                           "Minutes": [sum(t["duration"] for t in real if t["date"] == d.isoformat() and t["status"] == "pending") for d in ahead]})
        C.show(C.bars(wl, "Day", "Minutes", C.TEAL))
    with b, T.card():
        T.section("Quiz scores")
        if quizzes:
            qdf = pd.DataFrame({"Quiz": [f"#{i + 1}" for i in range(len(quizzes[-10:]))], "Score": [round(q["pct"]) for q in quizzes[-10:]]})
            C.show(C.bars(qdf, "Quiz", "Score", C.ROSE))
        else:
            st.markdown("<div class='muted'>Take a quiz to see your scores here.</div>", unsafe_allow_html=True)

    weak = L.weak_topics(state)
    with T.card():
        T.section("Weak topics", "Quiz scores below 60% show up here.")
        if weak:
            for s, t in weak:
                c1, c2 = st.columns([4, 1], vertical_alignment="center")
                c1.markdown(f"**{t['name']}**  \n<span class='muted'>{T.esc(s['name'])}</span>", unsafe_allow_html=True)
                c2.button("Review", key=f"tp_weak_{t['id']}", on_click=focus_topic, args=(s["id"], t["id"], "Learn"), width="stretch")
        else:
            st.markdown("<div class='muted'>No weak topics flagged.</div>", unsafe_allow_html=True)


def progress_subjects() -> None:
    """One expandable section per subject: the subject name appears once, topics sit inside."""
    state = S()
    if not state["subjects"]:
        st.info("Nothing to show yet.")
        return
    for s in state["subjects"]:
        prog = D.subject_progress(s)
        done = sum(1 for t in s["topics"] if t["status"] == "Completed")
        with st.expander(f"{s['name']}  ·  {prog:.0f}%  ·  {done} of {len(s['topics'])} topics"):
            if not s["topics"]:
                st.markdown("<div class='muted'>No topics yet.</div>", unsafe_allow_html=True)
                continue
            c1, c2 = st.columns([1, 3], vertical_alignment="center", gap="large")
            with c1:
                C.show(C.donut(prog))
            with c2:
                st.dataframe(pd.DataFrame([{
                    "Topic": t["name"], "Status": t["status"],
                    "Studied": min(100, round(t["done_min"] / max(t["est_minutes"], 1) * 100)),
                    "Minutes": f"{t['done_min']} of {t['est_minutes']}",
                    "Note": "Needs review" if t.get("weak") else ""} for t in s["topics"]]),
                    hide_index=True, width="stretch",
                    column_config={"Studied": st.column_config.ProgressColumn("Studied", min_value=0, max_value=100, format="%d%%")})


def progress_rewards() -> None:
    state, today = S(), date.today()
    g = state["gamification"]
    lvl = G.level_info(g["points"])
    c = st.columns(3, gap="medium")
    with c[0]:
        T.stat("Level", lvl["level"], f"{g['points']} points in total")
    with c[1]:
        T.stat("Current streak", f"{G.current_streak(state, today)} days", G.streak_message(state, today) or "")
    with c[2]:
        T.stat("Best streak", f"{G.best_streak(state)} days")
    st.progress(lvl["xp"] / lvl["needed"], text=f"{lvl['xp']} of {lvl['needed']} XP to level {lvl['level'] + 1}")
    T.section("Badges")
    cols = st.columns(len(G.BADGES), gap="medium")
    for col, (name, desc) in zip(cols, G.BADGES.items()):
        with col:
            T.badge(name, desc, name in g["badges"])
    with T.card():
        T.section("How points work")
        st.dataframe(pd.DataFrame([
            ("Complete a normal study task", f"+{G.POINTS['study']}"),
            ("Complete a difficult or high-priority task", f"+{G.POINTS['study_high']}"),
            ("Complete the whole daily plan", f"+{G.POINTS['daily_bonus']} bonus"),
            ("Complete a quiz", f"+{G.POINTS['quiz']}"),
            ("Score 80% or more in a quiz", f"+{G.POINTS['quiz_bonus']} bonus"),
            (f"Reach your daily target ({state['settings']['daily_target_pct']}% of planned time)", "Streak +1 day"),
            ("7-day streak badge", f"+{G.POINTS['streak7']} bonus"),
        ], columns=["Action", "Reward"]), hide_index=True, width="stretch")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
PAGE_FUNCS = {PAGE_DASH: page_dashboard, PAGE_SUBJECTS: page_subjects, PAGE_PLANNER: page_planner,
              PAGE_STUDY: page_study, PAGE_PROGRESS: page_progress}

init()
if st.session_state.get("focus"):
    T.inject(focus=True)
    page_focus()
    st.stop()
T.inject()
sidebar()
show_flash()
PAGE_FUNCS[st.session_state.page]()

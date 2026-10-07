"""app.py — Smart Study Planner (Streamlit front-end).

Run with:  streamlit run app.py

The app is one loop:  INPUT → SYLLABUS → PLAN → STUDY → TEST → COMPLETE → POINTS → ADAPT
Each page below supports one step of that loop; all logic lives in planner.py / learning.py / etc.
"""
from __future__ import annotations

import random
import time
from datetime import date, datetime, time as dtime, timedelta

import pandas as pd
import streamlit as st

import data as D
import gamification as G
import learning as L
import planner as P
import syllabus as SY

st.set_page_config(page_title="Smart Study Planner", page_icon="🎓", layout="wide")

PAGE_DASH = "🏠 Dashboard"
PAGE_SUBJECTS = "📚 Subjects"
PAGE_DETAIL = "📖 Subject Details"
PAGE_SCHEDULE = "⏰ My Schedule"
PAGE_PLAN = "🧠 Smart Plan"
PAGE_TASKS = "✅ Daily Tasks"
PAGE_LEARN = "🎓 Learn"
PAGE_CARDS = "🃏 Flashcards"
PAGE_QUIZ = "🧪 Quizzes"
PAGE_PROGRESS = "📊 Progress"
PAGE_REWARDS = "🏆 Rewards"
PAGES = [PAGE_DASH, PAGE_SUBJECTS, PAGE_DETAIL, PAGE_SCHEDULE, PAGE_PLAN, PAGE_TASKS,
         PAGE_LEARN, PAGE_CARDS, PAGE_QUIZ, PAGE_PROGRESS, PAGE_REWARDS]

TYPE_ICON = {"study": "📖", "revision": "🃏", "quiz": "🧪", "break": "☕"}
STATUS_ICON = {"pending": "⏳", "done": "✅", "missed": "❌", "skipped": "⏭️", "break": "☕"}
WIDGET_PREFIXES = ("av_", "ns_", "ed_", "tp_", "sel_", "quizrun_")


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


def focus_topic(subject_id: str, topic_id: str, page: str) -> None:
    """Pre-select a topic on the Learn / Flashcards / Quiz pages, then navigate."""
    for prefix in ("learn", "cards", "quiz"):
        st.session_state[f"sel_{prefix}_subject"] = subject_id
        st.session_state[f"sel_{prefix}_topic"] = topic_id
    st.session_state.page = page


def reset_widget_state() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(WIDGET_PREFIXES) or key in ("card_session", "quiz_run", "active_task"):
            del st.session_state[key]


def pick_topic(prefix: str):
    """Subject + topic selectors shared by Learn / Flashcards / Quizzes. Returns (subject, topic)."""
    state = S()
    subjects = state["subjects"]
    if not subjects:
        st.info("Add a subject first (📚 Subjects).")
        return None, None
    ids = [s["id"] for s in subjects]
    names = {s["id"]: s["name"] for s in subjects}
    sk, tk = f"sel_{prefix}_subject", f"sel_{prefix}_topic"
    if st.session_state.get(sk) not in ids:
        st.session_state.pop(sk, None)
    c1, c2 = st.columns(2)
    sid = c1.selectbox("Subject", ids, format_func=names.get, key=sk)
    subject = D.find_subject(state, sid)
    if not subject["topics"]:
        c2.info("This subject has no topics yet. Add some in 📖 Subject Details.")
        return subject, None
    tids = [t["id"] for t in subject["topics"]]
    tnames = {t["id"]: t["name"] for t in subject["topics"]}
    if st.session_state.get(tk) not in tids:
        st.session_state.pop(tk, None)
    tid = c2.selectbox("Topic", tids, format_func=tnames.get, key=tk)
    return subject, next(t for t in subject["topics"] if t["id"] == tid)


def task_line(t: dict) -> str:
    return f"`{t['start']}–{t['end']}` {TYPE_ICON.get(t['type'], '')} **{t['title']}** · {t['duration']} min"


# --------------------------------------------------------------------------- #
# Callbacks (run BEFORE the next rerun, so state is always fresh when the page redraws)
# --------------------------------------------------------------------------- #
def cb_load_demo() -> None:
    D.load_demo(S())
    reset_widget_state()
    G.update_badges(S(), date.today())
    save()
    flash("Demo data loaded: Mathematics, Physics and Python. Next: open 🧠 Smart Plan and generate the plan.", "info")


def cb_reset() -> None:
    S().clear()
    S().update(D.default_state())
    reset_widget_state()
    save()
    flash("All data erased.", "info")


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


def cb_complete(task_id: str) -> None:
    msgs = P.complete_task(S(), task_id)
    save()
    for m in msgs:
        flash(m, "success")
    active = st.session_state.get("active_task")
    if active and active["task_id"] == task_id:
        st.session_state.pop("active_task")


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
        flash(f"“{t['title']}” {verb}. Rescheduled → {when}, {moved['start']}–{moved['end']}. The rest of your plan was rebalanced.", "warning")
    else:
        flash(f"“{t['title']}” {verb}. There was no free slot before the exam — check the Smart Plan page for details.", "warning")
    if st.session_state.get("active_task", {}).get("task_id") == task_id:
        st.session_state.pop("active_task")


def cb_start(task_id: str) -> None:
    t = D.find_task(S(), task_id)
    if t:
        st.session_state.active_task = {"task_id": task_id, "title": t["title"],
                                        "minutes": t["duration"], "start": time.time()}


def cb_start_next() -> None:
    t = P.next_task(S(), date.today())
    if t:
        cb_start(t["id"])
        go(PAGE_TASKS)


def cb_stop_timer() -> None:
    st.session_state.pop("active_task", None)


def cb_open_subject(sid: str) -> None:
    st.session_state.sel_detail_subject = sid
    st.session_state.page = PAGE_DETAIL


def cb_delete_subject(sid: str) -> None:
    state = S()
    state["subjects"] = [s for s in state["subjects"] if s["id"] != sid]
    state["tasks"] = [t for t in state["tasks"] if t["subject_id"] != sid]
    save()
    flash("Subject deleted.", "info")


def cb_add_topics(sid: str, text_key: str, minutes_key: str, auto_key: str) -> None:
    state = S()
    subject = D.find_subject(state, sid)
    names = SY.parse_topics(st.session_state.get(text_key, ""))
    existing = {t["name"].lower() for t in subject["topics"]}
    names = [n for n in names if n.lower() not in existing]
    if not names:
        flash("No new topics found — type one topic per line.", "warning")
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
    flash("Marked as understood ✅ — a quiz and a revision session will be added next time you generate the plan.")


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
            flash(f"{overdue} task(s) from earlier days were missed — your remaining work was rescheduled automatically.", "warning")
        save()


def sidebar() -> None:
    state, today = S(), date.today()
    st.sidebar.title("🎓 Smart Study Planner")
    st.sidebar.radio("Go to", PAGES, key="page", label_visibility="collapsed")
    lvl = G.level_info(state["gamification"]["points"])
    st.sidebar.markdown(f"🔥 **{G.current_streak(state, today)}**-day streak  \n"
                        f"⭐ **{state['gamification']['points']}** points · Level {lvl['level']}")
    with st.sidebar.expander("Demo & data"):
        st.button("Load demo data", on_click=cb_load_demo, width="stretch")
        st.caption("Demo: Mathematics, Physics, Python + a 4-day starting streak.")
        confirm = st.checkbox("I want to erase everything", key="sel_confirm_reset")
        st.button("Reset all data", on_click=cb_reset, disabled=not confirm, width="stretch")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
def page_dashboard() -> None:
    state, today = S(), date.today()
    hour = datetime.now().hour
    greeting = "Good Morning" if hour < 12 else "Good Afternoon" if hour < 17 else "Good Evening"
    st.title(f"{greeting} 👋")
    st.caption(today.strftime("%A, %d %B %Y"))

    if not state["subjects"]:
        with st.container(border=True):
            st.subheader("Let's get you started")
            st.markdown("1. **Add subjects** with exam dates  \n2. **Add syllabus topics**  \n"
                        "3. **Set your free hours**  \n4. **Generate your plan**")
            c1, c2 = st.columns(2)
            c1.button("➕ Add my first subject", on_click=go, args=(PAGE_SUBJECTS,))
            c2.button("✨ Try with demo data", on_click=cb_load_demo)
        return

    stats = G.day_stats(state, today)
    avail = P.available_minutes(state, today)
    streak = G.current_streak(state, today)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Planned today", D.fmt_minutes(stats["planned_min"]), help=f"Free study time today: {D.fmt_minutes(avail)}")
    c2.metric("Done today", f"{stats['pct']:.0f}%", f"{stats['n_done']}/{stats['n_total']} tasks")
    c3.metric("🔥 Streak", f"{streak} days")
    c4.metric("⭐ Points", state["gamification"]["points"])
    st.progress(min(stats["pct"] / 100, 1.0))
    msg = G.streak_message(state, today)
    if msg:
        st.info(msg)

    left, right = st.columns([3, 2])
    with left:
        st.subheader("Today's schedule")
        tasks = sorted((t for t in state["tasks"] if t["date"] == today.isoformat() and t["type"] != "break"),
                       key=lambda t: t["start"])
        if tasks:
            for t in tasks:
                st.markdown(f"{STATUS_ICON[t['status']]} {task_line(t)}")
        else:
            st.info(f"Nothing planned for today. Free study time today: {D.fmt_minutes(avail)}.")
    with right:
        upcoming = [s for s in state["subjects"] if D.days_until(s["exam_date"], today) >= 0]
        if upcoming:
            nxt = min(upcoming, key=lambda s: s["exam_date"])
            days = D.days_until(nxt["exam_date"], today)
            with st.container(border=True):
                st.markdown("**📅 Next exam**")
                st.markdown(f"### {nxt['name']}")
                st.caption(f"{date.fromisoformat(nxt['exam_date']).strftime('%a %d %b')} — "
                           f"{'today!' if days == 0 else f'in {days} day' + ('s' if days != 1 else '')}")
        ranked = P.rank_topics(state, today)
        if ranked:
            top = ranked[0]
            with st.container(border=True):
                st.markdown("**🎯 Top priority**")
                st.markdown(f"### {top['subject']['name']} — {top['topic']['name']}")
                st.caption(top["reason"])

    st.subheader("Quick actions")
    a, b, c = st.columns(3)
    a.button("➕ Add Subject", on_click=go, args=(PAGE_SUBJECTS,), width="stretch")
    b.button("🧠 Generate Plan", on_click=cb_generate, width="stretch")
    c.button("▶️ Start Next Task", on_click=cb_start_next, disabled=P.next_task(state, today) is None,
             width="stretch")

    if stats["pct"] >= 100:
        st.success("Plan complete! Rest up — you earned it. 🌟")
    elif stats["pct"] > 0:
        st.caption("💬 You're moving! One focused session at a time.")
    else:
        st.caption("💬 A 25-minute start beats a perfect plan. Pick the first task and begin.")


# ---------------- Subjects ---------------- #
def subject_form(prefix: str, subject: dict | None = None) -> None:
    state, today = S(), date.today()
    editing = subject is not None
    with st.form(f"{prefix}_form", clear_on_submit=not editing):
        name = st.text_input("Subject name", value=subject["name"] if editing else "", key=f"{prefix}_name")
        c1, c2 = st.columns(2)
        exam = c1.date_input("Exam date", key=f"{prefix}_exam",
                             value=date.fromisoformat(subject["exam_date"]) if editing else today + timedelta(days=14))
        method = c2.selectbox("Preferred study method", D.METHODS, key=f"{prefix}_method",
                              index=D.METHODS.index(subject["method"]) if editing and subject["method"] in D.METHODS else 0)
        c3, c4, c5 = st.columns(3)
        diff = c3.slider("Difficulty (1–5)", 1, 5, subject["difficulty"] if editing else 3, key=f"{prefix}_diff")
        imp = c4.slider("Importance (1–5)", 1, 5, subject["importance"] if editing else 3, key=f"{prefix}_imp")
        prog = c5.slider("Current progress (%)", 0, 100, int(subject["progress"]) if editing else 0, key=f"{prefix}_prog")
        hours = st.number_input("Estimated total study hours (optional)", 0.0, 500.0,
                                float(subject["est_hours"]) if editing else 0.0, step=1.0, key=f"{prefix}_hours")
        submitted = st.form_submit_button("💾 Save changes" if editing else "➕ Add subject")
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
        state["subjects"].append(D.make_subject(clean, exam, diff, imp, prog, hours, method))
        save()
        flash(f"Added {clean}. Next: add its syllabus topics in 📖 Subject Details.")
        st.rerun()


def page_subjects() -> None:
    state, today = S(), date.today()
    st.title("📚 Subjects")
    with st.expander("➕ Add a subject", expanded=not state["subjects"]):
        subject_form("ns")
    if not state["subjects"]:
        return
    sort = st.selectbox("Sort by", ["Exam urgency", "Priority", "Progress (lowest first)"], key="sel_subject_sort")
    keyfn = {"Exam urgency": lambda s: s["exam_date"],
             "Priority": lambda s: -P.subject_priority(s, today),
             "Progress (lowest first)": D.subject_progress}[sort]
    for s in sorted(state["subjects"], key=keyfn):
        days = D.days_until(s["exam_date"], today)
        prog = D.subject_progress(s)
        done = sum(1 for t in s["topics"] if t["status"] == "Completed")
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.subheader(s["name"])
            when = "exam passed" if days < 0 else "exam today" if days == 0 else f"{days} day{'s' if days != 1 else ''} left"
            c1.caption(f"Exam {date.fromisoformat(s['exam_date']).strftime('%d %b %Y')} ({when}) · "
                       f"Difficulty {'★' * s['difficulty']}{'☆' * (5 - s['difficulty'])} · "
                       f"Importance {'★' * s['importance']}{'☆' * (5 - s['importance'])}")
            c1.progress(min(prog / 100, 1.0), text=f"{prog:.0f}% complete · {done}/{len(s['topics'])} topics")
            c2.button("Open →", key=f"open_{s['id']}", width="stretch",
                      on_click=cb_open_subject, args=(s["id"],))
            with st.expander("✏️ Edit / delete"):
                subject_form(f"ed_{s['id']}", s)
                ok = st.checkbox("Yes, delete this subject and its tasks", key=f"ed_{s['id']}_del")
                st.button("🗑 Delete subject", key=f"ed_{s['id']}_delbtn", disabled=not ok,
                          on_click=cb_delete_subject, args=(s["id"],))


# ---------------- Subject details + syllabus ---------------- #
def page_detail() -> None:
    state = S()
    st.title("📖 Subject Details & Syllabus")
    if not state["subjects"]:
        st.info("Add a subject first.")
        return
    ids = [s["id"] for s in state["subjects"]]
    names = {s["id"]: s["name"] for s in state["subjects"]}
    if st.session_state.get("sel_detail_subject") not in ids:
        st.session_state.pop("sel_detail_subject", None)
    sid = st.selectbox("Subject", ids, format_func=names.get, key="sel_detail_subject")
    subject = D.find_subject(state, sid)
    today = date.today()

    prog = D.subject_progress(subject)
    total_min = sum(t["est_minutes"] for t in subject["topics"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Progress", f"{prog:.0f}%")
    c2.metric("Exam in", f"{D.days_until(subject['exam_date'], today)} days")
    c3.metric("Syllabus study time", D.fmt_minutes(total_min))
    st.progress(min(prog / 100, 1.0))

    st.subheader("Topics")
    if not subject["topics"]:
        st.info("No topics yet — add them below (type them or upload a syllabus file).")
    changed = False
    for i, t in enumerate(subject["topics"]):
        c = st.columns([4, 1.5, 2, 0.6, 0.6, 0.6, 1.4])
        name = c[0].text_input("Topic", t["name"], key=f"tp_name_{t['id']}", label_visibility="collapsed")
        mins = c[1].number_input("Minutes", 5, 600, int(t["est_minutes"]), step=5, key=f"tp_min_{t['id']}",
                                 label_visibility="collapsed")
        status = c[2].selectbox("Status", D.STATUSES, index=D.STATUSES.index(t["status"]), key=f"tp_status_{t['id']}",
                                label_visibility="collapsed")
        c[3].button("↑", key=f"tp_up_{t['id']}", on_click=cb_move_topic, args=(sid, i, -1), disabled=i == 0)
        c[4].button("↓", key=f"tp_dn_{t['id']}", on_click=cb_move_topic, args=(sid, i, 1),
                    disabled=i == len(subject["topics"]) - 1)
        c[5].button("🗑", key=f"tp_del_{t['id']}", on_click=cb_delete_topic, args=(sid, t["id"]))
        c[6].button("Learn", key=f"tp_learn_{t['id']}", on_click=focus_topic, args=(sid, t["id"], PAGE_LEARN))
        if (name.strip() and name.strip() != t["name"]) or mins != t["est_minutes"] or status != t["status"]:
            t["name"] = name.strip() or t["name"]
            t["est_minutes"] = int(mins)
            t["status"] = status
            changed = True
    if changed:
        save()

    st.subheader("Add syllabus")
    tab_manual, tab_file = st.tabs(["✍️ Type or paste topics", "📄 Upload PDF / DOCX / TXT"])
    auto_key = f"tp_auto_{sid}"
    with tab_manual:
        st.text_area("One topic or chapter per line", key=f"tp_manual_{sid}", height=150,
                     placeholder="Limits and Continuity\nDifferentiation\nIntegration")
        m1, m2 = st.columns(2)
        m1.number_input("Minutes per topic", 5, 600, D.default_topic_minutes(subject), step=5, key=f"tp_manual_min_{sid}")
        if subject["est_hours"] > 0:
            m2.checkbox(f"Spread my {subject['est_hours']:g} estimated hours across topics", value=True, key=auto_key)
        st.button("Add topics", key=f"tp_manual_btn_{sid}", on_click=cb_add_topics,
                  args=(sid, f"tp_manual_{sid}", f"tp_manual_min_{sid}", auto_key))
    with tab_file:
        up = st.file_uploader("Syllabus file", type=["pdf", "docx", "txt"], key=f"tp_file_{sid}")
        if up is not None:
            sig = f"{up.name}-{up.size}"
            if st.session_state.get(f"tp_sig_{sid}") != sig:
                text, err = SY.extract_text(up)
                st.session_state[f"tp_sig_{sid}"] = sig
                st.session_state[f"tp_err_{sid}"] = err
                st.session_state[f"tp_extracted_{sid}"] = "\n".join(SY.parse_topics(text))
            if st.session_state.get(f"tp_err_{sid}"):
                st.warning(st.session_state[f"tp_err_{sid}"] + " You can still use the ✍️ tab.")
            else:
                st.caption("Check the detected topics, edit anything that looks wrong, then confirm.")
            st.text_area("Detected topics (editable)", key=f"tp_extracted_{sid}", height=200)
            st.number_input("Minutes per topic", 5, 600, D.default_topic_minutes(subject), step=5, key=f"tp_file_min_{sid}")
            st.button("✅ Confirm & add topics", key=f"tp_file_btn_{sid}", on_click=cb_add_topics,
                      args=(sid, f"tp_extracted_{sid}", f"tp_file_min_{sid}", auto_key))


# ---------------- Schedule ---------------- #
def window_editor(key: str, windows: list, rows: int, default: tuple[str, str]) -> list:
    out = []
    for i in range(rows):
        cur = windows[i] if i < len(windows) else None
        a, b = (cur or default)
        c1, c2, c3 = st.columns([1, 2, 2])
        on = c1.checkbox("On", value=cur is not None, key=f"{key}_on{i}")
        s = c2.time_input("Start", dtime(*map(int, a.split(":"))), key=f"{key}_s{i}", step=900, label_visibility="collapsed")
        e = c3.time_input("End", dtime(*map(int, b.split(":"))), key=f"{key}_e{i}", step=900, label_visibility="collapsed")
        if on:
            out.append([s.strftime("%H:%M"), e.strftime("%H:%M")])
    return out


def page_schedule() -> None:
    state, today = S(), date.today()
    av = state["availability"]
    st.title("⏰ My Schedule")
    st.caption("Tell the planner when you can study. Blocked periods (college, travel…) are removed from your study windows.")
    labels = {"weekday": "Mon–Fri", "saturday": "Saturday", "sunday": "Sunday", "holiday": "Holiday"}
    with st.form("av_form"):
        tabs = st.tabs([labels[d] for d in D.DAY_TYPES])
        new_w, new_b = {}, {}
        for tab, dt in zip(tabs, D.DAY_TYPES):
            with tab:
                st.markdown("**Study windows**")
                new_w[dt] = window_editor(f"av_{dt}_study", av["windows"][dt], 3, ("18:00", "21:00"))
                st.markdown("**Blocked time** (college, travel, commitments)")
                new_b[dt] = window_editor(f"av_{dt}_block", av["blocked"][dt], 3, ("09:00", "16:00"))
        c1, c2, c3, c4 = st.columns(4)
        max_s = c1.slider("Max session (min)", 20, 120, av["max_session_min"], step=5, key="av_max")
        brk = c2.slider("Break (min)", 0, 30, av["break_min"], step=5, key="av_break")
        cap = c3.slider("Daily capacity (hours)", 1.0, 12.0, av["daily_cap_min"] / 60, step=0.5, key="av_cap")
        target = c4.slider("Daily target for streak (%)", 30, 100, state["settings"]["daily_target_pct"], step=10, key="av_target")
        holiday_mode = st.toggle("🏖 Holiday mode — use the Holiday windows every day", value=av["holiday_mode"], key="av_holmode")
        submitted = st.form_submit_button("💾 Save schedule")
    if submitted:
        av["windows"], av["blocked"] = new_w, new_b
        av.update(max_session_min=max_s, break_min=brk, daily_cap_min=int(cap * 60), holiday_mode=holiday_mode)
        state["settings"]["daily_target_pct"] = target
        save()
        flash("Schedule saved. Regenerate your plan to apply it.")
        st.rerun()

    st.subheader("Holiday dates")
    c1, c2 = st.columns([2, 1])
    c1.date_input("Add a holiday", value=today, key="av_new_holiday")
    c2.button("Add holiday", on_click=cb_add_holiday)
    for iso in av["holiday_dates"]:
        h1, h2 = st.columns([4, 1])
        h1.write(date.fromisoformat(iso).strftime("%A, %d %B %Y"))
        h2.button("Remove", key=f"av_rm_{iso}", on_click=cb_remove_holiday, args=(iso,))

    st.subheader("Next 7 days — what the planner sees")
    rows = []
    for i in range(7):
        d = today + timedelta(days=i)
        wins = P.get_windows(av, d)
        rows.append({"Day": d.strftime("%a %d %b"), "Type": P.day_type(av, d),
                     "Free windows": ", ".join(f"{D.to_hhmm(a)}–{D.to_hhmm(b)}" for a, b in wins) or "—",
                     "Usable": D.fmt_minutes(P.available_minutes(state, d))})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---------------- Smart plan ---------------- #
def plan_table(tasks: list[dict]) -> pd.DataFrame:
    return pd.DataFrame([{
        "Time": f"{t['start']}–{t['end']}",
        "Task": f"{TYPE_ICON.get(t['type'], '')} {t['title']}",
        "Type": t["type"].capitalize(),
        "Duration": f"{t['duration']} min",
        "Reason": t["reason"],
        "Status": STATUS_ICON[t["status"]] if t["type"] != "break" else "",
    } for t in sorted(tasks, key=lambda t: t["start"])])


def page_plan() -> None:
    state, today = S(), date.today()
    st.title("🧠 Smart Plan")
    st.caption("Exam urgency + difficulty + importance + progress gap + topic urgency → priority → time slots.")
    if not state["subjects"]:
        st.info("Add subjects and topics first.")
        return
    c1, c2, c3 = st.columns([2, 2, 1])
    horizon = c1.radio("Plan for", ["Today", "This week"], index=1, horizontal=True, key="sel_horizon")
    from_now = c2.checkbox("Skip time that has already passed today", key="sel_from_now")
    c3.button("⚡ Generate", type="primary", on_click=cb_generate, args=(1 if horizon == "Today" else 7, from_now),
              width="stretch")
    st.caption("Generating replaces all upcoming pending tasks. Completed and missed tasks are kept as history.")

    summary = st.session_state.get("last_summary")
    if summary:
        for name in summary["no_topics"]:
            st.warning(f"**{name}** has no syllabus topics yet — add some in 📖 Subject Details.")
        for name in summary["expired"]:
            st.warning(f"**{name}**: exam date is today or in the past, so it was not planned.")
        for u in summary["unscheduled"]:
            st.warning(f"Not enough free time before the exam for **{u['subject']} — {u['topic']}** "
                       f"({u['minutes']} min unplanned). Add study windows or raise the daily capacity.")

    upcoming = sorted({t["date"] for t in state["tasks"] if t["date"] >= today.isoformat() and t["type"] != "break"})
    if not upcoming:
        st.info("No plan yet — click **Generate**.")
    for iso in upcoming[:7]:
        day_tasks = [t for t in state["tasks"] if t["date"] == iso]
        real = [t for t in day_tasks if t["type"] != "break"]
        label = date.fromisoformat(iso).strftime("%A, %d %B")
        with st.expander(f"{label} — {D.fmt_minutes(sum(t['duration'] for t in real))} planned", expanded=(iso == upcoming[0])):
            st.dataframe(plan_table(day_tasks), hide_index=True, width="stretch")

    with st.expander("🔍 Why this order? (priority ranking)"):
        ranked = P.rank_topics(state, today)
        if ranked:
            st.dataframe(pd.DataFrame([{
                "Subject": r["subject"]["name"], "Topic": r["topic"]["name"], "Priority score": round(r["score"], 1),
                "Exam in (days)": r["days_left"], "Why": r["reason"]} for r in ranked]),
                hide_index=True, width="stretch")
        else:
            st.write("No unfinished topics.")
        st.caption(f"Weights: urgency up to {P.W['urgency_max']}, difficulty ×{P.W['difficulty']}, importance ×{P.W['importance']}, "
                   f"progress gap ×{P.W['gap']}, weak topic +{P.W['weak']}, in-progress +{P.W['in_progress']}. Edit `W` in planner.py to tune.")


# ---------------- Daily tasks ---------------- #
@st.fragment(run_every=1)
def timer_panel() -> None:
    active = st.session_state.get("active_task")
    if not active:
        return
    total = max(active["minutes"] * 60, 1)
    elapsed = time.time() - active["start"]
    remaining = max(0, total - elapsed)
    with st.container(border=True):
        st.markdown(f"⏱️ **Focus timer — {active['title']}**")
        st.progress(min(elapsed / total, 1.0), text=f"{int(remaining // 60):02d}:{int(remaining % 60):02d} remaining")
        if remaining <= 0:
            st.success("Time's up! Mark the task complete below. 🎉")
        st.button("Stop timer", key="stop_timer_btn", on_click=cb_stop_timer)


def page_tasks() -> None:
    state, today = S(), date.today()
    st.title("✅ Daily Tasks")
    day = st.date_input("Day", value=today, key="sel_task_day")
    if st.session_state.get("active_task"):
        timer_panel()
    tasks = sorted((t for t in state["tasks"] if t["date"] == day.isoformat()), key=lambda t: t["start"])
    if not [t for t in tasks if t["type"] != "break"]:
        st.info("No tasks for this day. Generate a plan in 🧠 Smart Plan.")
        return
    stats = G.day_stats(state, day)
    st.progress(min(stats["pct"] / 100, 1.0), text=f"{stats['n_done']}/{stats['n_total']} tasks · {stats['pct']:.0f}% of planned time done")

    for t in tasks:
        if t["type"] == "break":
            st.caption(f"☕ {t['start']}–{t['end']} · Break")
            continue
        with st.container(border=True):
            c1, c2 = st.columns([5, 3])
            c1.markdown(f"{STATUS_ICON[t['status']]} {task_line(t)}")
            c1.caption(f"Why: {t['reason']}" + (f" · +{t['points']} pts" if t["status"] == "done" else ""))
            with c2:
                b = st.columns(4)
                if t["status"] == "pending":
                    b[0].button("▶", key=f"start_{t['id']}", help="Start focus timer", on_click=cb_start, args=(t["id"],))
                    b[1].button("✓", key=f"done_{t['id']}", help="Mark complete", type="primary", on_click=cb_complete, args=(t["id"],))
                    b[2].button("↷", key=f"skip_{t['id']}", help="Skip & reschedule", on_click=cb_miss, args=(t["id"], "skipped"))
                    b[3].button("✗", key=f"miss_{t['id']}", help="Missed — reschedule", on_click=cb_miss, args=(t["id"], "missed"))
                elif t["status"] == "done":
                    b[0].button("↩ Undo", key=f"undo_{t['id']}", on_click=cb_undo, args=(t["id"],))
                else:
                    c2.caption("Rescheduled automatically" if t["status"] in ("missed", "skipped") else "")
                if t["topic_id"]:
                    target = {"study": PAGE_LEARN, "revision": PAGE_CARDS, "quiz": PAGE_QUIZ}[t["type"]]
                    label = {"study": "📘 Open topic", "revision": "🃏 Open cards", "quiz": "🧪 Open quiz"}[t["type"]]
                    st.button(label, key=f"open_{t['id']}", on_click=focus_topic, args=(t["subject_id"], t["topic_id"], target))


# ---------------- Learn ---------------- #
def page_learn() -> None:
    state = S()
    st.title("🎓 Learn")
    subject, topic = pick_topic("learn")
    if not topic:
        return
    content = L.get_content(subject, topic)
    st.header(topic["name"])
    st.caption(f"{subject['name']} · {topic['status']} · {content['source']} content")
    st.info(content["summary"])
    st.markdown("**Key points**")
    for p in content["points"]:
        st.markdown(f"- {p}")
    if content["definitions"]:
        st.markdown("**Important definitions & formulas**")
        for term, text in content["definitions"]:
            st.markdown(f"- **{term}** — {text}")
    if topic.get("weak"):
        st.warning("This topic was flagged as a weak area after a quiz. Review it, then retake the quiz.")
    c1, c2, c3 = st.columns(3)
    c1.button("🃏 Flashcards", on_click=focus_topic, args=(subject["id"], topic["id"], PAGE_CARDS), width="stretch")
    c2.button("🧪 Take a quiz", on_click=focus_topic, args=(subject["id"], topic["id"], PAGE_QUIZ), width="stretch")
    c3.button("✅ Mark as understood", on_click=cb_mark_understood, args=(topic["id"],),
              disabled=topic["status"] == "Completed", width="stretch")


# ---------------- Flashcards ---------------- #
def page_cards() -> None:
    state, today = S(), date.today()
    st.title("🃏 Flashcards")
    subject, topic = pick_topic("cards")
    if not topic:
        return
    target = state["settings"]["daily_card_target"]
    reviewed = state["card_log"].get(today.isoformat(), 0)
    st.progress(min(reviewed / target, 1.0), text=f"Daily target: {reviewed}/{target} cards reviewed")

    sess = st.session_state.get("card_session")
    if sess and sess["topic_id"] != topic["id"]:
        st.session_state.pop("card_session")
        sess = None
    cards = L.get_cards(state, subject, topic)
    by_front = {c["front"]: c for c in cards}

    if not sess:
        prog = state["flashcards"].get(topic["id"], {})
        known = sum(1 for c in cards if prog.get(c["front"], {}).get("known"))
        st.write(f"**{len(cards)}** cards · **{known}** known · **{len(cards) - known}** to learn. Missed cards come first.")
        n = st.number_input("Cards in this session", 1, max(len(cards), 1), min(target, len(cards)), key="sel_cards_n")
        st.button("▶ Start review", type="primary", on_click=cb_start_cards, args=(subject["id"], topic["id"], int(n)))
    elif sess["idx"] >= len(sess["queue"]):
        st.success(f"Session complete — ✅ {sess['known']} known · 🔁 {sess['review']} to review.")
        st.button("Done", on_click=cb_end_cards)
    else:
        key = sess["queue"][sess["idx"]]
        card = by_front.get(key)
        if card is None:
            cb_rate_card(True)
            st.rerun()
        p = state["flashcards"].get(topic["id"], {}).get(key, {})
        st.progress(sess["idx"] / len(sess["queue"]), text=f"Card {sess['idx'] + 1} of {len(sess['queue'])} · seen {p.get('reviews', 0)}× before")
        with st.container(border=True):
            st.markdown(f"### {card['front']}")
            if sess["flipped"]:
                st.divider()
                st.markdown(f"#### {card['back']}")
        if not sess["flipped"]:
            st.button("🔄 Flip", on_click=cb_flip, width="stretch")
        else:
            a, b = st.columns(2)
            a.button("✅ Known", on_click=cb_rate_card, args=(True,), width="stretch")
            b.button("🔁 Needs review", on_click=cb_rate_card, args=(False,), width="stretch")
        st.button("End session", on_click=cb_end_cards)

    with st.expander("➕ Add your own card"):
        with st.form(f"tp_card_form_{topic['id']}", clear_on_submit=True):
            front = st.text_input("Front (question)")
            back = st.text_input("Back (answer)")
            if st.form_submit_button("Add card"):
                if L.add_custom_card(state, topic["id"], front, back):
                    save()
                    flash("Card added. With 4+ custom cards you also unlock a quiz for this topic.")
                    st.rerun()
                else:
                    st.error("Fill in both sides.")


# ---------------- Quizzes ---------------- #
def page_quiz() -> None:
    state = S()
    st.title("🧪 Quizzes")
    run = st.session_state.get("quiz_run")

    if run is None:
        subject, topic = pick_topic("quiz")
        if not topic:
            return
        pool = L.quiz_pool(state, subject, topic)
        if not pool:
            st.info("No built-in quiz for this topic yet. Add 4 or more of your own flashcards (🃏 Flashcards) to unlock one.")
            return
        n = len(pool) if len(pool) <= 3 else st.slider("Number of questions", 3, min(10, len(pool)), min(5, len(pool)), key="sel_quiz_n")
        st.button("▶ Start quiz", type="primary", on_click=cb_start_quiz, args=(subject["id"], topic["id"], n))
        history = [q for q in state["quiz_history"] if q["topic_id"] == topic["id"]]
        if history:
            st.caption("Previous scores: " + ", ".join(f"{q['score']}/{q['total']}" for q in history[-5:]))
        return

    questions = run["questions"]
    if run["finished"]:
        res = run["result"]
        st.header(f"Score: {run['correct']}/{len(questions)} ({res['pct']:.0f}%)")
        for m in res["messages"]:
            st.success(m)
        _, topic = D.find_topic(state, run["topic_id"])
        if res["weak"]:
            st.warning(f"⚠️ Weak area: **{topic['name']}**. It has been flagged, and the planner will add revision for it.")
            c1, c2 = st.columns(2)
            c1.button("📘 Review weak topic", on_click=focus_topic, args=(run["subject_id"], run["topic_id"], PAGE_LEARN))
            c2.button("🧠 Update my plan now", on_click=cb_generate)
        elif res["pct"] >= 80:
            st.balloons()
            st.success("Excellent! You're exam-ready on this topic. 🌟")
        else:
            st.info("Good effort. One more pass through the flashcards should lock it in.")
        st.button("Finish", on_click=cb_end_quiz)
        return

    idx = run["idx"]
    q = questions[idx]
    key = f"quizrun_{run['nonce']}_{idx}"
    st.progress(idx / len(questions), text=f"Question {idx + 1} of {len(questions)}")
    st.radio(q["q"], q["options"], index=None, key=key, disabled=run["checked"])
    if not run["checked"]:
        st.button("Check answer", on_click=cb_check_answer, args=(key,), disabled=st.session_state.get(key) is None)
    else:
        if run["last_correct"]:
            st.success("Correct! ✅")
        else:
            st.error(f"Not quite. Correct answer: **{q['options'][q['answer']]}**")
        st.caption(q["explanation"])
        st.button("See results" if idx + 1 >= len(questions) else "Next →", on_click=cb_next_question, type="primary")
    st.button("Quit quiz", on_click=cb_end_quiz)


# ---------------- Progress ---------------- #
def page_progress() -> None:
    state, today = S(), date.today()
    st.title("📊 Progress")
    if not state["subjects"]:
        st.info("Nothing to show yet.")
        return
    all_topics = [t for s in state["subjects"] for t in s["topics"]]
    total_min = sum(t["est_minutes"] for t in all_topics) or 1
    overall = sum(D.topic_fraction(t) * t["est_minutes"] for t in all_topics) / total_min * 100
    real = [t for t in state["tasks"] if t["type"] != "break"]
    done = [t for t in real if t["status"] == "done"]
    quizzes = state["quiz_history"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Syllabus completed", f"{overall:.0f}%")
    c2.metric("Study hours done", D.fmt_minutes(sum(t["duration"] for t in done if t["type"] == "study")))
    c3.metric("Tasks done / planned", f"{len(done)}/{len(real)}")
    c4.metric("Avg quiz score", f"{sum(q['pct'] for q in quizzes) / len(quizzes):.0f}%" if quizzes else "—")

    st.subheader("Per subject")
    for s in state["subjects"]:
        st.progress(min(D.subject_progress(s) / 100, 1.0), text=f"{s['name']} — {D.subject_progress(s):.0f}%")

    st.subheader("Per topic")
    rows = [{"Subject": s["name"], "Topic": t["name"], "Status": t["status"],
             "Studied": f"{t['done_min']}/{t['est_minutes']} min", "Weak": "⚠️" if t.get("weak") else ""}
            for s in state["subjects"] for t in s["topics"]]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("Last 7 days")
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        df = pd.DataFrame({
            "Planned (min)": [sum(t["duration"] for t in real if t["date"] == d.isoformat()) for d in days],
            "Completed (min)": [sum(t["duration"] for t in done if t["date"] == d.isoformat()) for d in days],
        }, index=[d.strftime("%a %d") for d in days])
        st.bar_chart(df)
    with right:
        st.subheader("Upcoming workload")
        ahead = [today + timedelta(days=i) for i in range(7)]
        wl = pd.DataFrame({"Planned (min)": [sum(t["duration"] for t in real if t["date"] == d.isoformat() and t["status"] == "pending")
                                              for d in ahead]}, index=[d.strftime("%a %d") for d in ahead])
        st.bar_chart(wl)

    st.subheader("Weak topics")
    weak = L.weak_topics(state)
    if weak:
        for s, t in weak:
            c1, c2 = st.columns([4, 1])
            c1.warning(f"{s['name']} — {t['name']}")
            c2.button("Review", key=f"tp_weak_{t['id']}", on_click=focus_topic, args=(s["id"], t["id"], PAGE_LEARN))
    else:
        st.success("No weak topics flagged. Quiz scores below 60% will show up here.")

    if quizzes:
        st.subheader("Quiz performance")
        qdf = pd.DataFrame([{"Date": q["date"], "Topic": (D.find_topic(state, q["topic_id"])[1] or {"name": "(deleted)"})["name"],
                             "Score": f"{q['score']}/{q['total']}", "Percent": round(q["pct"])} for q in quizzes])
        st.dataframe(qdf, hide_index=True, width="stretch")


# ---------------- Rewards ---------------- #
def page_rewards() -> None:
    state, today = S(), date.today()
    g = state["gamification"]
    st.title("🏆 Rewards")
    lvl = G.level_info(g["points"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Level", lvl["level"])
    c2.metric("🔥 Current streak", f"{G.current_streak(state, today)} days")
    c3.metric("Best streak", f"{G.best_streak(state)} days")
    st.progress(lvl["xp"] / lvl["needed"], text=f"{lvl['xp']}/{lvl['needed']} XP to level {lvl['level'] + 1} · {g['points']} points total")
    msg = G.streak_message(state, today)
    if msg:
        st.info(msg)

    st.subheader("Badges")
    cols = st.columns(len(G.BADGES))
    for col, (name, desc) in zip(cols, G.BADGES.items()):
        with col, st.container(border=True):
            earned = name in g["badges"]
            st.markdown(f"### {'🏅' if earned else '🔒'}")
            st.markdown(f"**{name}**")
            st.caption(desc)

    st.subheader("How points work")
    st.table(pd.DataFrame([
        ("Complete a normal study task", f"+{G.POINTS['study']}"),
        ("Complete a difficult / high-priority task", f"+{G.POINTS['study_high']}"),
        ("Complete the whole daily plan", f"+{G.POINTS['daily_bonus']} bonus"),
        ("Complete a quiz", f"+{G.POINTS['quiz']}"),
        ("Score 80%+ in a quiz", f"+{G.POINTS['quiz_bonus']} bonus"),
        (f"Reach your daily target ({state['settings']['daily_target_pct']}% of planned time)", "Streak +1 day"),
        ("7-day streak badge", f"+{G.POINTS['streak7']} bonus"),
    ], columns=["Action", "Reward"]).set_index("Action"))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
PAGE_FUNCS = {
    PAGE_DASH: page_dashboard, PAGE_SUBJECTS: page_subjects, PAGE_DETAIL: page_detail,
    PAGE_SCHEDULE: page_schedule, PAGE_PLAN: page_plan, PAGE_TASKS: page_tasks,
    PAGE_LEARN: page_learn, PAGE_CARDS: page_cards, PAGE_QUIZ: page_quiz,
    PAGE_PROGRESS: page_progress, PAGE_REWARDS: page_rewards,
}

init()
sidebar()
show_flash()
PAGE_FUNCS[st.session_state.page]()

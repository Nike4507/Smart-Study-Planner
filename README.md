# 🎓 Smart Study Planner

A personalised study-management app built with **Python + Streamlit**. It turns a student's subjects, syllabus, exam dates, free hours and progress into realistic daily study tasks, **adapts when a task is missed**, and supports learning with summaries, flashcards and quizzes. Points, streaks and badges keep students consistent.

> **The loop:** INPUT → UNDERSTAND SYLLABUS → PLAN → STUDY → TEST → COMPLETE → EARN POINTS → ADAPT

## Features

| Area | What it does |
|---|---|
| Dashboard | Today's plan, % done, streak, points, next exam, top-priority topic, quick actions |
| Subjects | Add / edit / delete subjects (exam date, difficulty, importance, progress), sort by urgency / priority / progress |
| Syllabus | Type or paste topics, **or** upload PDF / DOCX / TXT → preview → edit → confirm. Manual entry always works |
| Schedule | Study windows + blocked time (college, travel) for weekdays / Saturday / Sunday / holidays, break + session limits, holiday mode |
| Smart Plan | Today or weekly plan with a **reason for every task**; splits big topics, interleaves subjects, adds quizzes and revision |
| Daily Tasks | Start (focus timer), complete, skip / missed → automatic rescheduling |
| Learn / Flashcards / Quizzes | Summaries, flip cards (known / needs review, missed cards first), MCQ quizzes with feedback, weak-topic detection |
| Progress | Syllabus %, per-subject / per-topic completion, study hours, planned vs done chart, quiz scores, weak topics |
| Rewards | Points, streak, levels / XP bar, badges |

## Quick start (VS Code)

```bash
git clone <your-repo-url>
cd smart-study-planner

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The app opens at http://localhost:8501. Click **Demo & data → Load demo data** in the sidebar to try the full demo scenario.

Run the tests: `pytest -q`

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit front-end: navigation, forms, all pages |
| `planner.py` | Priority scoring, availability windows, schedule generation, adaptive rescheduling, task events |
| `learning.py` | Summaries, flashcards, quizzes (rule-based knowledge base + custom cards) |
| `gamification.py` | Points, streak, badges, levels |
| `syllabus.py` | PDF / DOCX / TXT extraction and topic cleaning |
| `data.py` | State model, JSON persistence (`study_data.json`), demo data, progress calculation |
| `tests/test_planner.py` | Unit tests for planning, rescheduling, points / streaks, syllabus and quiz logic |

## How the planner works

```
Priority = Exam urgency + Difficulty×4 + Importance×4 + Progress gap×0.2 + Topic urgency
```

- **Exam urgency** = `50 × 7 / (7 + days_left)` — rises sharply as the exam gets close.
- **Topic urgency** = +15 for weak topics (quiz < 60%), +5 for topics already started.
- Tune everything in the `W` dictionary at the top of `planner.py`.

**Scheduling** (greedy):
1. Free windows = study windows − blocked time − already-used slots. Nothing is scheduled on or after exam day.
2. Repeatedly pick the highest-priority item that fits; place it, add a break after.
3. Sessions are capped at the max session length; big topics are split across slots / days.
4. Placing the same subject again is penalised, so subjects interleave.
5. When a topic is fully scheduled, a **quiz** follows and **revision** (flashcards) the next day.
6. The daily capacity is never exceeded. Anything that doesn't fit is reported as a warning.

**Adaptive rescheduling:** a missed / skipped task is marked and the plan is rebuilt from today. Only *completed* study minutes count, so unfinished work is automatically moved to the next suitable window. Tasks left pending from earlier days are marked missed on the next app start.

## Points and streak rules

| Action | Points |
|---|---|
| Normal study task / revision | +10 |
| Difficult (difficulty ≥ 4) or exam within 3 days | +15 |
| Whole daily plan completed | +25 bonus |
| Quiz completed / score ≥ 80% | +10 / +10 bonus |
| 7-day streak badge | +100 |

**Streak:** +1 day when the *daily target* is reached (default: 60% of the day's planned time done; adjustable in My Schedule). A missed day resets it with a friendly message.

## Demo script (for judges)

1. Sidebar → **Load demo data** (Mathematics, Physics, Python; college until 4 PM, study 6–9 PM).
2. **Subject Details** → show the syllabus topics (or paste / upload one).
3. **My Schedule** → show the blocked and study windows.
4. **Smart Plan** → **Generate**; open *Why this order?* to show the explainable priorities.
5. **Daily Tasks** → complete Mathematics (points!), start the focus timer.
6. **Learn → Quizzes** → read the summary, take the quiz.
7. Back in **Daily Tasks** → press ✗ on Physics → see it rescheduled automatically.
8. **Dashboard / Progress / Rewards** → progress, streak and points have updated.

## Limitations and future scope

- Summaries / quizzes are rule-based and built in for the demo topics only. Other topics get a study guide plus student-made flashcards (4+ custom cards unlock a quiz). Swapping in an LLM only touches `learning.py`.
- Scanned (image-only) PDFs can't be read — use manual entry.
- Single user, stored locally in `study_data.json` (no login / cloud sync).
- Future: spaced repetition, calendar sync, adaptive quiz difficulty, leaderboards.

## Team ownership

| Person | Primary | Secondary |
|---|---|---|
| 1 | `app.py` / UI | Integration, polish |
| 2 | `planner.py`, `gamification.py` | `learning.py`, tests |
| 3 | README, requirements, docs | PPT, screenshots, demo flow |

## Push to GitHub

```bash
git init
git add .
git commit -m "Smart Study Planner MVP"
git branch -M main
git remote add origin https://github.com/<your-username>/smart-study-planner.git
git push -u origin main
```

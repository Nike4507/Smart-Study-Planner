"""learning.py — summaries, flashcards and quizzes.

MVP approach (spec §6): rule-based content. A small built-in knowledge base covers the demo
topics (Maths, Physics, Python). Any other topic gets a study-guide template, and students can
write their own flashcards — 4+ custom cards automatically unlock a quiz for that topic.

To plug in an LLM later, replace ``get_content`` / ``quiz_pool`` with API calls; the rest of
the app only depends on the dict shapes returned here.
"""
from __future__ import annotations

import random
from datetime import date

import data as D
import gamification as G
import planner as P

# --------------------------------------------------------------------------- #
# Built-in knowledge base
# quiz tuple: (question, [options], index_of_correct_option, explanation)
# --------------------------------------------------------------------------- #
KB = [
    {
        "keys": ["integration", "integral"],
        "summary": "Integration is the reverse of differentiation. It finds an antiderivative F(x) of f(x) and, for definite integrals, the signed area under a curve between two limits.",
        "points": [
            "Indefinite integrals always carry a constant of integration, + C.",
            "Power rule: ∫ xⁿ dx = xⁿ⁺¹ / (n + 1) + C, for n ≠ −1.",
            "∫ 1/x dx = ln|x| + C, ∫ eˣ dx = eˣ + C, ∫ cos x dx = sin x + C, ∫ sin x dx = −cos x + C.",
            "Fundamental Theorem of Calculus: ∫ₐᵇ f(x) dx = F(b) − F(a).",
            "Substitution undoes the chain rule; integration by parts undoes the product rule.",
        ],
        "definitions": [
            ("Antiderivative", "A function F whose derivative is f, i.e. F′(x) = f(x)."),
            ("Definite integral", "The signed area between f(x) and the x-axis from x = a to x = b."),
        ],
        "cards": [
            ("∫ xⁿ dx (n ≠ −1) = ?", "xⁿ⁺¹ / (n + 1) + C"),
            ("∫ (1/x) dx = ?", "ln|x| + C"),
            ("∫ eˣ dx = ?", "eˣ + C"),
            ("∫ cos x dx = ?", "sin x + C"),
            ("Why do indefinite integrals have + C?", "The derivative of a constant is 0, so many functions share the same derivative."),
            ("State the Fundamental Theorem of Calculus.", "∫ₐᵇ f(x) dx = F(b) − F(a), where F′ = f."),
        ],
        "quiz": [
            ("What is ∫ x² dx?", ["x³/3 + C", "2x + C", "x³ + C", "x²/2 + C"], 0, "Power rule: raise the power by 1 and divide by the new power."),
            ("What is ∫ cos x dx?", ["−sin x + C", "sin x + C", "cos x + C", "−cos x + C"], 1, "d/dx(sin x) = cos x."),
            ("Evaluate ∫₀² x dx.", ["1", "2", "4", "0"], 1, "[x²/2] from 0 to 2 = 4/2 − 0 = 2."),
            ("Why do indefinite integrals include + C?", ["The derivative of a constant is zero, so the antiderivative is not unique", "It keeps the answer positive", "It is the unit of area", "It has no meaning"], 0, "Every constant disappears when differentiated."),
            ("What is ∫ eˣ dx?", ["eˣ + C", "x·eˣ + C", "eˣ⁺¹ + C", "ln|x| + C"], 0, "eˣ is its own derivative and antiderivative."),
        ],
    },
    {
        "keys": ["differentiation", "derivative", "differential"],
        "summary": "Differentiation measures how fast a quantity changes. The derivative of f at x is the slope of the tangent line, or the instantaneous rate of change.",
        "points": [
            "Power rule: d/dx xⁿ = n·xⁿ⁻¹.",
            "Product rule: (uv)′ = u′v + uv′. Quotient rule: (u/v)′ = (u′v − uv′) / v².",
            "Chain rule: d/dx f(g(x)) = f′(g(x)) · g′(x).",
            "d/dx sin x = cos x, d/dx eˣ = eˣ, d/dx ln x = 1/x.",
            "A stationary point occurs where f′(x) = 0.",
        ],
        "definitions": [
            ("Derivative", "lim (h→0) [f(x + h) − f(x)] / h — the instantaneous rate of change."),
            ("Chain rule", "Rule for differentiating a function of a function."),
        ],
        "cards": [
            ("d/dx (xⁿ) = ?", "n·xⁿ⁻¹"),
            ("State the product rule.", "(uv)′ = u′v + uv′"),
            ("State the chain rule.", "d/dx f(g(x)) = f′(g(x)) · g′(x)"),
            ("d/dx (sin x) = ?", "cos x"),
            ("d/dx (ln x) = ?", "1/x"),
            ("What does a derivative represent geometrically?", "The slope of the tangent line to the curve."),
        ],
        "quiz": [
            ("What is d/dx (x³)?", ["3x²", "x²", "3x", "x⁴/4"], 0, "Bring the power down and reduce it by one."),
            ("What is d/dx (sin x)?", ["−cos x", "cos x", "sin x", "−sin x"], 1, "Standard result."),
            ("What is the derivative of a constant?", ["1", "The constant", "0", "Undefined"], 2, "A constant does not change."),
            ("Differentiate (2x + 1)².", ["2(2x + 1)", "4(2x + 1)", "(2x + 1)", "4x"], 1, "Chain rule: 2(2x + 1) × 2."),
            ("What is d/dx (ln x)?", ["ln x / x", "x", "1/x", "eˣ"], 2, "Standard result."),
        ],
    },
    {
        "keys": ["electrostatic", "coulomb", "electric field", "electric charge"],
        "summary": "Electrostatics studies forces and fields produced by charges at rest. Like charges repel, unlike charges attract, and the force falls off with the square of the distance.",
        "points": [
            "Coulomb's law: F = k·q₁q₂ / r², with k ≈ 9 × 10⁹ N·m²/C².",
            "Electric field: E = F/q; for a point charge E = kq / r².",
            "Electric potential of a point charge: V = kq / r.",
            "Charge is quantised (e ≈ 1.6 × 10⁻¹⁹ C) and conserved.",
            "Gauss's law: the net flux through a closed surface = Q_enclosed / ε₀.",
        ],
        "definitions": [
            ("Electric field", "Force per unit positive test charge at a point (unit: N/C or V/m)."),
            ("Electric potential", "Work done per unit charge in bringing a test charge from infinity to a point (unit: volt)."),
        ],
        "cards": [
            ("State Coulomb's law.", "F = k·q₁q₂ / r²"),
            ("Value of k in Coulomb's law?", "≈ 9 × 10⁹ N·m²/C²"),
            ("Electric field of a point charge?", "E = kq / r²"),
            ("SI unit of electric field?", "N/C (equivalently V/m)"),
            ("Magnitude of the electron's charge?", "≈ 1.6 × 10⁻¹⁹ C"),
            ("What does Gauss's law relate?", "Electric flux through a closed surface to the enclosed charge: Φ = Q / ε₀"),
        ],
        "quiz": [
            ("If the distance between two charges doubles, the force…", ["doubles", "halves", "becomes one-quarter", "stays the same"], 2, "F ∝ 1/r²."),
            ("SI unit of electric field?", ["N/C (or V/m)", "N·C", "C/m", "J"], 0, "E = F/q."),
            ("Two positive charges placed near each other will…", ["attract", "repel", "exert no force", "annihilate"], 1, "Like charges repel."),
            ("Electric field at distance r from a point charge q?", ["kq/r", "kq/r²", "kq²/r", "k/(q·r²)"], 1, "E = kq/r²."),
            ("The magnitude of the electron's charge is about…", ["1.6 × 10⁻¹⁹ C", "9 × 10⁹ C", "1.6 × 10¹⁹ C", "6.7 × 10⁻¹¹ C"], 0, "The elementary charge e."),
        ],
    },
    {
        "keys": ["laws of motion", "newton"],
        "summary": "Newton's three laws link force and motion: objects keep their state of motion unless a net force acts (1st), F = ma (2nd), and every action has an equal and opposite reaction (3rd).",
        "points": [
            "1st law (inertia): no net force → constant velocity (or rest).",
            "2nd law: F = m·a; force is measured in newtons (1 N = 1 kg·m/s²).",
            "3rd law: forces always come in equal and opposite pairs acting on different bodies.",
            "Inertia depends only on mass; momentum p = m·v.",
        ],
        "definitions": [
            ("Inertia", "The tendency of a body to resist a change in its state of motion."),
            ("Newton", "The force that gives a 1 kg mass an acceleration of 1 m/s²."),
        ],
        "cards": [
            ("State Newton's second law.", "F = m·a"),
            ("State Newton's third law.", "Every action has an equal and opposite reaction."),
            ("What does the first law describe?", "Inertia — no net force means no change in velocity."),
            ("SI unit of force?", "Newton (kg·m/s²)"),
            ("Formula for momentum?", "p = m·v"),
        ],
        "quiz": [
            ("A 2 kg mass accelerates at 3 m/s². The net force is…", ["5 N", "6 N", "1.5 N", "9 N"], 1, "F = ma = 2 × 3."),
            ("Newton's third law says…", ["Every action has an equal and opposite reaction", "F = ma", "Energy is conserved", "Objects at rest stay at rest only"], 0, "Forces come in pairs."),
            ("The inertia of a body depends on its…", ["mass", "colour", "speed only", "temperature"], 0, "More mass = more inertia."),
            ("The SI unit of force is the…", ["joule", "watt", "newton", "pascal"], 2, "1 N = 1 kg·m/s²."),
            ("A body moving with constant velocity has net force…", ["zero", "equal to its weight", "equal to its momentum", "infinite"], 0, "No acceleration means no net force."),
        ],
    },
    {
        "context": ["python", "programming", "coding"],
        "keys": ["loop", "iteration"],
        "summary": "Loops repeat a block of code. `for` loops iterate over a sequence (like range() or a list); `while` loops repeat as long as a condition stays True.",
        "points": [
            "range(n) gives 0 … n−1; range(a, b, step) controls start, stop and step.",
            "`break` leaves the loop immediately; `continue` skips to the next iteration.",
            "Make sure a `while` condition eventually becomes False, otherwise you get an infinite loop.",
            "Loops can be nested; use `enumerate()` when you need the index and the value.",
        ],
        "definitions": [
            ("Iteration", "One pass through the body of a loop."),
            ("Iterable", "An object you can loop over, e.g. list, string, range."),
        ],
        "cards": [
            ("What does range(3) produce?", "0, 1, 2"),
            ("What does `break` do?", "Exits the loop immediately."),
            ("What does `continue` do?", "Skips the rest of this iteration and moves to the next."),
            ("When does a while loop stop?", "When its condition becomes False."),
            ("Which function gives index and value together?", "enumerate()"),
        ],
        "quiz": [
            ("What is list(range(3))?", ["[0, 1, 2]", "[1, 2, 3]", "[0, 1, 2, 3]", "[1, 2]"], 0, "range stops before the end value."),
            ("What does `break` do inside a loop?", ["Skips one iteration", "Exits the loop", "Restarts the loop", "Raises an error"], 1, "It terminates the loop."),
            ("What does `continue` do?", ["Ends the program", "Exits the loop", "Skips to the next iteration", "Repeats the iteration"], 2, "Remaining statements in that pass are skipped."),
            ("Which loop repeats while a condition is True?", ["for", "while", "if", "def"], 1, "That is the definition of while."),
            ("Values produced by range(2, 10, 3)?", ["2, 5, 8", "2, 4, 6, 8", "3, 6, 9", "2, 5, 8, 10"], 0, "Start 2, step 3, stop before 10."),
        ],
    },
    {
        "context": ["python", "programming", "coding"],
        "keys": ["function"],
        "summary": "Functions package reusable code. Define them with `def`, give them parameters, and send values back with `return`.",
        "points": [
            "Syntax: def name(parameters): … return value.",
            "A function without `return` gives back None.",
            "Parameters are names in the definition; arguments are the values you pass in.",
            "Default values: def f(x, y=2). Use keyword arguments for clarity.",
        ],
        "definitions": [
            ("Parameter", "A variable listed in a function definition."),
            ("Argument", "The actual value passed when calling a function."),
        ],
        "cards": [
            ("Which keyword defines a function?", "def"),
            ("What does a function return if it has no return statement?", "None"),
            ("Parameter vs argument?", "Parameter = name in the definition; argument = value passed in the call."),
            ("How do you give a parameter a default value?", "def f(x, y=2): …"),
        ],
        "quiz": [
            ("Which keyword defines a function in Python?", ["func", "def", "function", "lambda only"], 1, "`def` starts a function definition."),
            ("A function with no return statement returns…", ["0", "an empty string", "None", "an error"], 2, "Implicit return value is None."),
            ("A value you pass when calling a function is a(n)…", ["parameter", "argument", "module", "decorator"], 1, "Parameters are in the definition."),
            ("What is f(3) for `def f(x, y=2): return x*y`?", ["5", "6", "3", "Error"], 1, "y defaults to 2."),
            ("Why use functions?", ["Reuse and organise code", "To make code slower", "To avoid variables", "Only for maths"], 0, "They remove repetition."),
        ],
    },
    {
        "context": ["python", "programming", "coding"],
        "keys": ["list", "dictionar", "data structure"],
        "summary": "Lists are ordered, mutable sequences; dictionaries store key → value pairs. Together they are Python's workhorse data structures.",
        "points": [
            "Lists are indexed from 0 and can be changed (append, remove, slice).",
            "Dictionaries map unique keys to values: d['name'] = 'Asha'.",
            "Tuples are like lists but immutable.",
            "len(x) returns the number of items; `in` tests membership.",
        ],
        "definitions": [
            ("Mutable", "Can be changed after creation (list, dict, set)."),
            ("Key", "The unique label used to look up a value in a dictionary."),
        ],
        "cards": [
            ("Index of the first element of a list?", "0"),
            ("How do you add an item to the end of a list?", "list.append(item)"),
            ("What does a dictionary store?", "Key → value pairs."),
            ("Which is immutable: list or tuple?", "tuple"),
            ("What does len([4, 5, 6]) return?", "3"),
        ],
        "quiz": [
            ("Index of the first element of a Python list?", ["1", "0", "-1", "Depends"], 1, "Python is zero-indexed."),
            ("What is len([4, 5, 6])?", ["2", "3", "4", "15"], 1, "Three items."),
            ("A dictionary stores…", ["Only numbers", "Key–value pairs", "Only strings", "Sorted lists"], 1, "Each key maps to a value."),
            ("Which method adds an item to the end of a list?", ["add()", "push()", "append()", "insert_end()"], 2, "list.append(x)."),
            ("Which of these is immutable?", ["list", "dict", "tuple", "set"], 2, "Tuples cannot be modified."),
        ],
    },
]


# --------------------------------------------------------------------------- #
# Content lookup
# --------------------------------------------------------------------------- #
def find_entry(subject_name: str, topic_name: str) -> dict | None:
    topic_l = topic_name.lower()
    context = f"{subject_name} {topic_name}".lower()
    for entry in KB:
        if entry.get("context") and not any(c in context for c in entry["context"]):
            continue
        if any(k in topic_l for k in entry["keys"]):
            return entry
    return None


def get_material(state: dict | None, topic: dict) -> dict | None:
    """Content generated from the student's notes or the web (see ai.py), if any."""
    return (state or {}).get("materials", {}).get(topic["id"])


def get_content(subject: dict, topic: dict, state: dict | None = None) -> dict:
    """Summary page content for a topic."""
    mat = get_material(state, topic)
    if mat and mat.get("summary"):
        return {"source": mat["source"], "summary": mat["summary"], "points": mat.get("points", []),
                "definitions": mat.get("definitions", [])}
    entry = find_entry(subject["name"], topic["name"])
    if entry:
        return {"source": "built-in", "summary": entry["summary"], "points": entry["points"],
                "definitions": entry["definitions"]}
    name = topic["name"]
    return {
        "source": "generic",
        "summary": f"“{name}” is part of {subject['name']}. There is no built-in summary for this topic yet — "
                   "use the checklist below and add your own flashcards.",
        "points": [
            f"Skim the {name} section of your syllabus / textbook and note the headings.",
            "List every definition, formula and worked example you need to remember.",
            "Solve 3–5 practice questions or past-paper problems on it.",
            "Explain the topic out loud in your own words (the Feynman method).",
        ],
        "definitions": [],
    }


# --------------------------------------------------------------------------- #
# Flashcards
# --------------------------------------------------------------------------- #
def get_cards(state: dict, subject: dict, topic: dict) -> list[dict]:
    entry = find_entry(subject["name"], topic["name"])
    mat = get_material(state, topic)
    if mat and mat.get("cards"):
        base = [{"front": c["front"], "back": c["back"], "custom": False} for c in mat["cards"]]
    elif entry:
        base = [{"front": f, "back": b, "custom": False} for f, b in entry["cards"]]
    else:
        base = [
            {"front": f"Explain the main idea of “{topic['name']}” in one sentence.",
             "back": "Write it from memory, then compare with your notes.", "custom": False},
            {"front": f"List the key terms and formulas of “{topic['name']}”.",
             "back": "Write them from memory, then check your syllabus.", "custom": False},
        ]
    custom = [{**c, "custom": True} for c in state["custom_cards"].get(topic["id"], [])]
    return base + custom


def add_custom_card(state: dict, topic_id: str, front: str, back: str) -> bool:
    front, back = front.strip(), back.strip()
    if not front or not back:
        return False
    state["custom_cards"].setdefault(topic_id, []).append({"front": front, "back": back})
    return True


def review_queue(state: dict, subject: dict, topic: dict, limit: int) -> list[str]:
    """Card keys ordered: previously missed first, then unseen, then known."""
    progress = state["flashcards"].get(topic["id"], {})

    def rank(card: dict):
        p = progress.get(card["front"])
        if p is None:
            return (1, 0)
        return (0, -p.get("missed", 0)) if not p.get("known") else (2, 0)

    ordered = sorted(get_cards(state, subject, topic), key=rank)
    return [c["front"] for c in ordered][:limit]


def record_card(state: dict, topic_id: str, key: str, known: bool, today: date | None = None) -> None:
    today = today or date.today()
    p = state["flashcards"].setdefault(topic_id, {}).setdefault(key, {"known": False, "reviews": 0, "missed": 0})
    p["reviews"] += 1
    p["known"] = known
    if not known:
        p["missed"] += 1
    state["card_log"][today.isoformat()] = state["card_log"].get(today.isoformat(), 0) + 1


# --------------------------------------------------------------------------- #
# Quizzes
# --------------------------------------------------------------------------- #
def quiz_pool(state: dict, subject: dict, topic: dict) -> list[dict]:
    mat = get_material(state, topic)
    if mat and mat.get("quiz"):
        return list(mat["quiz"])
    entry = find_entry(subject["name"], topic["name"])
    if entry:
        return [{"q": q, "options": o, "answer": a, "explanation": e} for q, o, a, e in entry["quiz"]]
    custom = state["custom_cards"].get(topic["id"], [])
    if len(custom) < 4:
        return []
    pool = []
    for i, card in enumerate(custom):
        others = [c["back"] for j, c in enumerate(custom) if j != i and c["back"] != card["back"]][:3]
        if len(others) < 3:
            continue
        pool.append({"q": card["front"], "options": others + [card["back"]], "answer": 3,
                     "explanation": f"Your own card says: {card['back']}"})
    return pool


def prepare_quiz(pool: list[dict], n: int, seed: int | None = None) -> list[dict]:
    """Pick n questions and shuffle each question's options (keeping track of the right one)."""
    rng = random.Random(seed)
    chosen = rng.sample(pool, min(n, len(pool)))
    out = []
    for q in chosen:
        options = list(q["options"])
        correct = options[q["answer"]]
        rng.shuffle(options)
        out.append({"q": q["q"], "options": options, "answer": options.index(correct),
                    "explanation": q["explanation"]})
    return out


def finish_quiz(state: dict, subject_id: str, topic_id: str, score: int, total: int,
                today: date | None = None) -> dict:
    """Store result, flag weak topics, award points, auto-complete the planned quiz task."""
    today = today or date.today()
    _, topic = D.find_topic(state, topic_id)
    pct = score / total * 100 if total else 0.0
    state["quiz_history"].append({"date": today.isoformat(), "subject_id": subject_id, "topic_id": topic_id,
                                  "score": score, "total": total, "pct": pct})
    msgs = []
    if topic:
        topic["quiz_done"] = True
        if pct < 60:
            topic["weak"] = True
        elif pct >= 80:
            topic["weak"] = False
    points = G.POINTS["quiz"] + (G.POINTS["quiz_bonus"] if pct >= 80 else 0)
    G.add_points(state, points)
    msgs.append(f"+{points} points for the quiz" + (" (80%+ bonus!)" if pct >= 80 else ""))

    pending = sorted((t for t in state["tasks"] if t["type"] == "quiz" and t["topic_id"] == topic_id
                      and t["status"] == "pending"), key=lambda t: (t["date"], t["start"]))
    if pending:
        P.complete_task(state, pending[0]["id"], today, award=False)
        msgs.append("Planned quiz task marked complete.")
    msgs += [f"New badge: {b}" for b in G.update_badges(state, today)]
    return {"pct": pct, "weak": pct < 60, "messages": msgs}


def weak_topics(state: dict) -> list[tuple[dict, dict]]:
    out = []
    for s in state["subjects"]:
        for t in s["topics"]:
            if t.get("weak"):
                out.append((s, t))
    return out

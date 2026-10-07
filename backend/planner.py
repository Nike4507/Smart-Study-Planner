from datetime import date


def calculate_priority(
    exam_date,
    difficulty,
    importance,
    progress,
    completed=False
):
    """
    Calculate how urgently a topic should be studied.

    Higher score = higher priority.
    """

    days_left = max(
        (exam_date - date.today()).days,
        1
    )

    # Exam becomes more urgent as the date gets closer
    exam_urgency = max(1, 10 - days_left)

    # How much of the topic is still unfinished
    progress_gap = 100 - progress

    # Give unfinished topics extra priority
    topic_urgency = 0 if completed else 5

    score = (
        exam_urgency
        + difficulty
        + importance
        + (progress_gap / 20)
        + topic_urgency
    )

    return round(score, 2)
if __name__ == "__main__":
    score = calculate_priority(
        exam_date=date(2026, 10, 10),
        difficulty=5,
        importance=5,
        progress=20
    )

    print("Priority:", score)
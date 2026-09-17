"""Reproduce the local-planner findings LLM-1 .. LLM-3 (read-only).

Run from the repository root:  ./backend/.venv/bin/python audit/repro/tti_plan3.py
The profile used is synthetic: first date 2026-01-01, latest date 2026-06-30.
"""

import json
import sys
from datetime import date

sys.path.insert(0, "backend")

from app.db.data_profile import DataProfile  # noqa: E402
from app.llm.local_planner import plan_local_question  # noqa: E402


def main() -> None:
    profile = DataProfile(
        first_date=date(2026, 1, 1),
        latest_date=date(2026, 6, 30),
        workout_types=("Running", "Cycling"),
        metrics=("Resting heart rate",),
    )
    questions = [
        "compare my runs this week and last week",  # LLM-3: week wording, month plan
        "compare this month and last month",  # control: month wording
        "resting heart rate last year",  # LLM-1: 'year' -> Jan 1 .. as_of
        "resting heart rate last month",  # control: month wording
        "how many steps this year",  # LLM-1/LLM-2: no plan at all
        "Show my top brunch runs",  # LLM-2: 'run' inside 'brunch'
        "Show my last brunch",  # LLM-2: 'run' inside 'brunch' + 'last'
        "my longest cyclone ride",  # LLM-2: 'cycl' inside 'cyclone'
    ]
    for question in questions:
        plan = plan_local_question(question, profile)
        print(f"{question!r}\n  -> {json.dumps(plan, sort_keys=True)}\n")


if __name__ == "__main__":
    main()

import sys
import json
from datetime import date

sys.path.insert(0, "backend")
from app.llm.local_planner import plan_local_question
from app.db.data_profile import DataProfile

p = DataProfile(
    first_date=date(2026, 1, 1),
    latest_date=date(2026, 6, 30),
    workout_types=("Running", "Cycling"),
    metrics=("Resting heart rate",),
)
for q in [
    "What did I eat for brunch?",
    "Show my last year in review",
    "How was my weight this month?",
    "Show my last run",
    "I was running late, how many steps?",
    "cyclone season steps",
    "Compare this month vs last month",
    "Show my longest rides by energy",
    "how many steps in the last week",
]:
    try:
        print(repr(q), "->", json.dumps(plan_local_question(q, p)))
    except Exception as e:
        print(repr(q), "-> ERROR", type(e).__name__, e)

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
    "Show my top brunch runs",
    "top 5 gym sessions",
    "resting heart rate last year",
    "how many steps this year",
    "training volume last year",
    "my longest runs this year",
    "highest heart rate bike ride",
]:
    print(repr(q), "->", json.dumps(plan_local_question(q, p)))

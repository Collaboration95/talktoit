import sys
import duckdb
import json

sys.path.insert(0, "backend")
from app.ingest.coordinator import ingest_v2

conn = duckdb.connect(":memory:")
stats = ingest_v2("backend/tests/fixtures/sample.xml", conn, n_workers=1)
print(
    json.dumps({k: v for k, v in stats.items() if not k.endswith("seconds")}, indent=0)
)
print(
    conn.execute(
        "select id, activity_type, duration, duration_unit from workouts"
    ).fetchall()
)
print(
    "distinct types:",
    conn.execute("select distinct activity_type from workouts").fetchall(),
)

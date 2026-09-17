import sys
import duckdb

sys.path.insert(0, "backend")
from app.ingest.parser import ingest

conn = duckdb.connect(":memory:")
ingest("backend/tests/fixtures/sample.xml", conn)
print(
    conn.execute(
        "select id, activity_type, duration, duration_unit from workouts"
    ).fetchall()
)

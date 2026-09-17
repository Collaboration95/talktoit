import sys
import duckdb

sys.path.insert(0, "backend")
from app.db.schema import SQL_CREATE_TABLES
from app.db.queries import get_top_workouts

conn = duckdb.connect(":memory:")
conn.execute(SQL_CREATE_TABLES)
for i in range(1, 6):
    ts = f"2026-06-0{i} 08:00:00"
    conn.execute(
        "INSERT INTO workouts (id, activity_type, duration, duration_unit, start_date, end_date, source_name) "
        "VALUES (?, 'Cycling', 60.0, 'min', ?::TIMESTAMP, ?::TIMESTAMP, 'Watch')",
        [i, ts, ts],
    )
conn.execute(
    "INSERT INTO workouts (id, activity_type, start_date, end_date, source_name) VALUES (7,'Cycling', TIMESTAMP '2026-06-07 08:00:00', TIMESTAMP '2026-06-07 09:00:00', 'Watch'), (8,'Cycling', TIMESTAMP '2026-06-08 08:00:00', TIMESTAMP '2026-06-08 09:00:00', 'Watch')"
)
for i in range(1, 6):
    conn.execute(
        "INSERT INTO workout_statistics (workout_id, type, sum, unit) VALUES (?, 'HKQuantityTypeIdentifierDistanceCycling', ?, 'km')",
        [i, float(i)],
    )
out = get_top_workouts(conn, "Cycling", "distance", n=5)
print("rows returned:", len(out.rows), "| title:", out.title)
for r in out.rows:
    print(" ", r.rank, r.label, "|", r.value, r.unit)
print("--- ORDER BY d DESC (default null order) ---")
print(
    conn.execute(
        "SELECT w.id, (SELECT sum FROM workout_statistics ws WHERE ws.workout_id=w.id AND ws.type='HKQuantityTypeIdentifierDistanceCycling') d FROM workouts w ORDER BY d DESC"
    ).fetchall()
)
print("duckdb:", duckdb.__version__)

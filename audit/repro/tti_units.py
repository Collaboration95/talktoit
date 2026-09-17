import sys
import duckdb
from datetime import date

sys.path.insert(0, "backend")
from app.db.schema import SQL_CREATE_TABLES
from app.db.queries import get_period_summary

conn = duckdb.connect(":memory:")
conn.execute(SQL_CREATE_TABLES)
conn.execute(
    "INSERT INTO workouts (id, activity_type, start_date, end_date, duration, duration_unit, source_name) VALUES "
    "(1,'Running', TIMESTAMP '2026-06-05 01:00:00', TIMESTAMP '2026-06-05 02:00:00', 1.0, 'hr', 'Watch'),"
    "(2,'Running', TIMESTAMP '2026-06-06 01:00:00', TIMESTAMP '2026-06-06 02:00:00', 60.0, 'min', 'Watch')"
)
s = get_period_summary(conn, date(2026, 6, 1), date(2026, 6, 30))
for m in s.metrics:
    print("period_summary:", m.label, "=", m.value, m.unit)
# direct normalized expectation: 60 + 60 = 120 min

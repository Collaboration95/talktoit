import sys
import duckdb

sys.path.insert(0, "backend")
from app.ingest.parser import ingest
from app.api.dashboard import get_workouts

conn = duckdb.connect(":memory:")
ingest("backend/tests/fixtures/sample.xml", conn)
print("total workouts in db:", conn.execute("select count(*) from workouts").fetchone())
for limit in (1, 2, 3, 50):
    seen, pages, cur = [], 0, None
    while True:
        resp = get_workouts(conn=conn, start=None, end=None, cursor=cur, limit=limit)
        seen += [w.id for w in resp.workouts]
        pages += 1
        cur = resp.next_cursor
        if cur is None or pages > 20:
            break
    print(f"limit={limit} pages={pages} ids={seen} dups={len(seen) != len(set(seen))}")

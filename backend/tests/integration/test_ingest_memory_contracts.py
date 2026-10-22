"""Synthetic correctness contracts for streaming validation and bounded workers."""

from __future__ import annotations

import mmap
from pathlib import Path

import duckdb
import pyarrow.parquet as pq
import pytest
from lxml import etree

from app.ingest import bytescan, compatibility, coordinator
from app.ingest.parser import ingest as ingest_legacy

pytestmark = pytest.mark.ingest_contract
FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "sample.xml"
COUNTS = {
    "records": 40,
    "record_metadata": 7,
    "hrv_beats": 7,
    "workouts": 3,
    "workout_events": 6,
    "workout_statistics": 8,
    "workout_routes": 2,
    "workout_metadata": 12,
    "activity_summaries": 5,
}


def test_validation_releases_completed_siblings_at_each_depth(tmp_path, monkeypatch):
    """Real iterparse must not accumulate cleared shells behind its cursor."""
    export = tmp_path / "nested.xml"
    children = '<MetadataEntry key="synthetic" value="marker"/>' * 300
    export.write_text(
        "<HealthData>"
        + (f"<Record>{children}</Record><Workout>{children}</Workout>" * 10)
        + "</HealthData>"
    )
    original = export.read_bytes()
    real_iterparse = compatibility.etree.iterparse
    retained = []
    visited = []

    def observe(*args, **kwargs):
        for event, element in real_iterparse(*args, **kwargs):
            visited.append(element.tag)
            yield event, element
            # Inspect after the validator resumes, counting only completed
            # predecessors, not lxml's legitimate buffered future siblings.
            retained.append(sum(1 for _ in element.itersiblings(preceding=True)))

    monkeypatch.setattr(compatibility.etree, "iterparse", observe)
    compatibility.require_well_formed_export(export)
    assert visited.count("MetadataEntry") == 6000
    assert visited.count("Record") == visited.count("Workout") == 10
    assert max(retained) == 0
    assert export.read_bytes() == original


@pytest.mark.parametrize(
    ("xml", "message"),
    [
        ("<HealthData><Record>", "malformed XML export"),
        ("<HealthData><Workout><MetadataEntry/></HealthData>", "malformed XML export"),
        ("<HealthData><Record></Workout></HealthData>", "malformed XML export"),
        ("<HealthData/><HealthData/>", "malformed XML export"),
        ("<WrongRoot><Record><MetadataEntry/></Record></WrongRoot>", "root must be HealthData"),
    ],
)
def test_invalid_xml_never_reaches_scanning_or_mutates_db(tmp_path, monkeypatch, xml, message):
    export = tmp_path / "invalid.xml"
    export.write_text(xml)

    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid syntax reached the byte scanner")

    monkeypatch.setattr(coordinator, "ingest", forbidden)
    with duckdb.connect(":memory:") as db:
        db.execute("CREATE TABLE retained AS SELECT 42 AS sentinel")
        with pytest.raises(compatibility.V2CompatibilityError, match=message):
            coordinator.ingest_v2(export, db, n_workers=1)
        assert db.execute("SELECT * FROM retained").fetchall() == [(42,)]


def _record(value, children=""):
    return (
        f'<Record value="{value}" endDate="2026-01-01 00:01:00 +0000" '
        'unit="count" sourceName="Synthetic &amp; Watch" '
        'startDate="2026-01-01 00:00:00 +0000" '
        'type="HKQuantityTypeIdentifierStepCount">'
        f"{children}</Record>"
    ).encode()


@pytest.mark.parametrize("range_kind", ["complete", "cut_end", "cut_start", "empty"])
def test_worker_matches_mmap_with_exclusive_absolute_bounds(tmp_path, monkeypatch, range_kind):
    """The actual regex reads mmap, with no outside matches or range-sized copy."""
    first = _record(11, '<MetadataEntry value="first" key="synthetic"/>')
    last = _record(22, '<MetadataEntry value="last" key="synthetic"/>')
    prefix = b"<HealthData>" + _record(999)
    middle = first + b"<!-- synthetic boundary -->" + last
    export = tmp_path / "ranges.xml"
    export.write_bytes(prefix + middle + _record(888) + b"</HealthData>")
    start, end = len(prefix), len(prefix) + len(middle)
    expected_values = [11.0, 22.0]
    if range_kind == "cut_end":
        end -= 1
        expected_values = [11.0]
    elif range_kind == "cut_start":
        start += 1
        expected_values = [22.0]
    elif range_kind == "empty":
        end = start
        expected_values = []
    real_pattern = bytescan._TOP_RE
    calls, spans = [], []

    class ObservedPattern:
        def finditer(self, subject, *bounds):
            calls.append((isinstance(subject, mmap.mmap), bounds))
            for match in real_pattern.finditer(subject, *bounds):
                if match.group("tag") is not None:
                    spans.append(match.span())
                yield match

    monkeypatch.setattr(bytescan, "_TOP_RE", ObservedPattern())
    result = bytescan.parse_byte_range(
        str(export), start, end, worker_idx=3, shard_dir=str(tmp_path / "shards"), row_group_size=1
    )
    assert calls == [(True, (start, end))]
    assert all(start <= low < high <= end for low, high in spans)
    if range_kind == "complete":
        assert spans == [(start, start + len(first)), (end - len(last), end)]
    tables = {"records": [], "record_metadata": []}
    for filename in result.parquet_files:
        for table, rows in tables.items():
            if Path(filename).name.startswith(f"{table}-"):
                rows.extend(pq.read_table(filename).to_pylist())
    assert result.worker_idx == 3
    assert result.records_count == result.record_metadata_count == len(expected_values)
    assert [row["value"] for row in tables["records"]] == expected_values
    assert [row["local_id"] for row in tables["records"]] == list(
        range(1, len(expected_values) + 1)
    )
    assert [row["parent_local_id"] for row in tables["record_metadata"]] == list(
        range(1, len(expected_values) + 1)
    )
    assert all(row["worker_idx"] == 3 for rows in tables.values() for row in rows)
    assert all(row["source_name"] == "Synthetic & Watch" for row in tables["records"])
    assert [row["value"] for row in tables["record_metadata"]] == [
        "first" if value == 11 else "last" for value in expected_values
    ]


def _snapshot(db):
    # Closed, fixture-owned table names; include IDs/FKs and every nullable field.
    return {
        table: db.execute(f"SELECT * FROM {table} ORDER BY ALL").fetchall()  # noqa: S608
        for table in COUNTS
    }


@pytest.mark.parametrize("reordered", [False, True])
def test_all_tables_match_legacy_at_1_2_4_workers_with_owned_sentinels(
    tmp_path, monkeypatch, reordered
):
    export = FIXTURE
    if reordered:
        tree = etree.parse(str(FIXTURE))
        for element in tree.iter():
            if not isinstance(element.tag, str) or element is tree.getroot():
                continue
            attributes = list(element.attrib.items())[::-1]
            element.attrib.clear()
            element.attrib.update(attributes)
            element[:] = list(element)[::-1]
        export = tmp_path / "reordered.xml"
        tree.write(str(export), encoding="UTF-8", xml_declaration=True)

    root = tmp_path / "caller-shards"
    sibling = root / "unrelated-run"
    sibling.mkdir(parents=True)
    sentinel = root / "sentinel.txt"
    sentinel.write_bytes(b"caller-owned")
    sibling_sentinel = sibling / "keep.parquet"
    sibling_sentinel.write_bytes(b"unrelated-owned")
    monkeypatch.setenv("TTI_INGEST_SHARDS", str(root))

    with duckdb.connect(":memory:") as legacy:
        ingest_legacy(str(export), legacy)
        expected = _snapshot(legacy)
    assert {table: len(rows) for table, rows in expected.items()} == COUNTS
    for workers in (1, 2, 4):
        with duckdb.connect(":memory:") as db:
            stats = coordinator.ingest_v2(export, db, n_workers=workers)
            assert {table: stats[table] for table in COUNTS} == COUNTS
            assert _snapshot(db) == expected
            assert db.execute(
                "SELECT SUM(value) FROM records WHERE type='HKQuantityTypeIdentifierStepCount'"
            ).fetchone() == (90954.0,)
            assert db.execute(
                "SELECT duration FROM workouts WHERE activity_type='Running'"
            ).fetchone() == (45.5,)
        assert sentinel.read_bytes() == b"caller-owned"
        assert sibling_sentinel.read_bytes() == b"unrelated-owned"
        assert set(root.iterdir()) == {sentinel, sibling}

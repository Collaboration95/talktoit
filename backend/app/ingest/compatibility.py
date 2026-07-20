"""Post-reconciliation safety checks for the V2 ingestion pipeline.

These checks intentionally operate on the canonical staging database, rather
than parser counters alone. A V2 import may only progress to activation after
the public tables, typed category values, and child relations agree.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree  # type: ignore[import-untyped]

if TYPE_CHECKING:
    import duckdb


_COUNT_QUERIES = {
    "records": "SELECT COUNT(*) FROM records",
    "record_metadata": "SELECT COUNT(*) FROM record_metadata",
    "hrv_beats": "SELECT COUNT(*) FROM hrv_beats",
    "workouts": "SELECT COUNT(*) FROM workouts",
    "workout_events": "SELECT COUNT(*) FROM workout_events",
    "workout_statistics": "SELECT COUNT(*) FROM workout_statistics",
    "workout_routes": "SELECT COUNT(*) FROM workout_routes",
    "workout_metadata": "SELECT COUNT(*) FROM workout_metadata",
    "activity_summaries": "SELECT COUNT(*) FROM activity_summaries",
}

_CHILD_RELATIONS = (
    (
        "record_metadata",
        "SELECT COUNT(*) FROM record_metadata c LEFT JOIN records p "
        "ON c.record_id = p.id WHERE p.id IS NULL",
    ),
    (
        "hrv_beats",
        "SELECT COUNT(*) FROM hrv_beats c LEFT JOIN records p "
        "ON c.record_id = p.id WHERE p.id IS NULL",
    ),
    (
        "workout_events",
        "SELECT COUNT(*) FROM workout_events c LEFT JOIN workouts p "
        "ON c.workout_id = p.id WHERE p.id IS NULL",
    ),
    (
        "workout_statistics",
        "SELECT COUNT(*) FROM workout_statistics c LEFT JOIN workouts p "
        "ON c.workout_id = p.id WHERE p.id IS NULL",
    ),
    (
        "workout_routes",
        "SELECT COUNT(*) FROM workout_routes c LEFT JOIN workouts p "
        "ON c.workout_id = p.id WHERE p.id IS NULL",
    ),
    (
        "workout_metadata",
        "SELECT COUNT(*) FROM workout_metadata c LEFT JOIN workouts p "
        "ON c.workout_id = p.id WHERE p.id IS NULL",
    ),
)


@dataclass(frozen=True)
class CompatibilityReport:
    """Versioned, non-sensitive V2 activation report."""

    version: str
    errors: tuple[str, ...]
    checks: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        """Whether this staged database can become active."""
        return not self.errors


class V2CompatibilityError(RuntimeError):
    """Raised before activation if reconciled V2 output is incompatible."""


def require_well_formed_export(xml_path: str | Path) -> None:
    """Reject malformed or non-HealthData exports before the fast scan runs.

    The byte scanner intentionally does not construct an XML tree, so it cannot
    establish that a truncated document is structurally complete.  A streaming
    syntax pass supplies that activation invariant without retaining health
    observations in memory.
    """
    try:
        root_tag: str | None = None
        for _event, element in etree.iterparse(str(xml_path), events=("end",)):
            if root_tag is None:
                root_tag = element.getroottree().getroot().tag
            element.clear()
    except (OSError, etree.XMLSyntaxError) as exc:
        raise V2CompatibilityError(
            f"V2 compatibility gate failed: malformed XML export ({exc})"
        ) from exc
    if root_tag != "HealthData":
        raise V2CompatibilityError("V2 compatibility gate failed: XML root must be HealthData")


def check_v2_compatibility(
    conn: duckdb.DuckDBPyConnection,
    expected_counts: Mapping[str, int],
) -> CompatibilityReport:
    """Validate canonical V2 output without retaining any health observations."""
    errors: list[str] = []
    checks: list[str] = ["canonical-counts", "child-relations", "category-capture"]
    for stat_name, query in _COUNT_QUERIES.items():
        expected = expected_counts.get(stat_name)
        if expected is None:
            errors.append(f"missing expected count for {stat_name}")
            continue
        row = conn.execute(query).fetchone()
        actual = int(row[0]) if row else -1
        if actual != expected:
            errors.append(f"{stat_name} count {actual} did not match parsed count {expected}")

    for child, query in _CHILD_RELATIONS:
        row = conn.execute(query).fetchone()
        orphan_count = int(row[0]) if row else -1
        if orphan_count:
            errors.append(f"{child} has {orphan_count} orphaned rows")

    category_row = conn.execute(
        "SELECT COUNT(*) FROM records "
        "WHERE type LIKE 'HKCategoryTypeIdentifier%' AND text_value IS NULL"
    ).fetchone()
    missing_category_text = int(category_row[0]) if category_row else -1
    if missing_category_text:
        errors.append(f"{missing_category_text} category records lost their text value")

    return CompatibilityReport(version="v2-compat-1", errors=tuple(errors), checks=tuple(checks))


def require_v2_compatibility(
    conn: duckdb.DuckDBPyConnection,
    expected_counts: Mapping[str, int],
) -> CompatibilityReport:
    """Return the report or prevent staging output from being activated."""
    report = check_v2_compatibility(conn, expected_counts)
    if not report.accepted:
        raise V2CompatibilityError("V2 compatibility gate failed: " + "; ".join(report.errors))
    return report

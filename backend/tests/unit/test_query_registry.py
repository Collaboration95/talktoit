"""Every shared analytics query needs complete contract declarations."""

from __future__ import annotations

import duckdb
import pytest
from pydantic import ValidationError

from app.analytics.registry import (
    QUERY_REGISTRY,
    execute_activity_summary,
    execute_period_summary,
    get_query_definition,
    validate_query_catalogue,
)
from app.db.schema import SQL_CREATE_TABLES


def test_registry_entries_declare_version_timezone_units_and_dependencies() -> None:
    assert QUERY_REGISTRY
    for definition in QUERY_REGISTRY.values():
        assert definition.version.startswith("v")
        assert definition.timezone == "Asia/Singapore"
        assert definition.unit
        assert definition.dependencies
        assert definition.empty_state
        assert definition.success_state
        assert definition.error_state
        assert definition.input_fields
        assert definition.metric_ids
        assert definition.source_policy
        assert definition.overlap_policy


def test_unknown_registry_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported analytics query"):
        get_query_definition("arbitrary_sql")


def test_registry_catalogue_rejects_no_undeclared_metrics() -> None:
    validate_query_catalogue()


def test_every_registry_entry_has_a_validated_input_contract() -> None:
    for definition in QUERY_REGISTRY.values():
        with pytest.raises(ValidationError):
            definition.input_model.model_validate([])


def test_activity_summary_executor_validates_absolute_scope_and_returns_facts() -> None:
    """The dashboard adapter uses the registry's validated ring-summary facts."""
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    conn.execute(
        """INSERT INTO activity_summaries VALUES
        ('2024-01-02', 100.0, 200.0, 'kJ', NULL, NULL, 30.0, 60.0, 8, 12)"""
    )

    assert execute_activity_summary(conn, {"start": "2024-01-01", "end": "2024-01-03"}) == [
        ("2024-01-02", 100.0, 200.0, 30.0, 60.0, 8, 12)
    ]
    with pytest.raises(ValueError, match="absolute start and end"):
        execute_activity_summary(conn, {})


def test_period_summary_executor_validates_and_returns_template_facts() -> None:
    conn = duckdb.connect(":memory:")
    conn.execute(SQL_CREATE_TABLES)
    result = execute_period_summary(
        conn, {"start": "2024-01-01", "end": "2024-01-07", "title": "Week"}
    )
    assert result.title == "Week"
    with pytest.raises(ValidationError):
        execute_period_summary(conn, {"start": "not-a-date", "end": "2024-01-07"})

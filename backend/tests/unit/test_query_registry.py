"""Every shared analytics query needs complete contract declarations."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.analytics.registry import QUERY_REGISTRY, get_query_definition, validate_query_catalogue


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

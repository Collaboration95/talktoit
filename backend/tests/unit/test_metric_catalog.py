"""Metric catalog entries carry the declarations required for safe display."""

from __future__ import annotations

from app.analytics.metric_catalog import METRIC_CATALOG, catalog_for_apple_type


def test_all_catalog_entries_declare_unit_policy_and_safe_language() -> None:
    assert set(METRIC_CATALOG) >= {"steps", "resting_hr", "sleep"}
    for metric in METRIC_CATALOG.values():
        assert metric.label
        assert metric.unit
        assert metric.source_policy
        assert metric.overlap_policy
        assert metric.value_kind in {"numeric", "category", "summary"}
        assert metric.date_semantics in {"record_start", "interval_union", "summary_day"}
        assert metric.medical_language in {"measured_only", "not_medical"}


def test_catalog_resolves_declared_apple_type_only() -> None:
    assert catalog_for_apple_type("HKQuantityTypeIdentifierStepCount") is METRIC_CATALOG["steps"]
    assert catalog_for_apple_type("HKQuantityTypeIdentifierUnsupported") is None

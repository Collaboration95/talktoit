"""Unit tests for Pydantic model validators (R1-11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.chat import ChatResponse


def test_chat_response_validates_workout_card_data() -> None:
    """Valid workout_card data passes validation."""
    response = ChatResponse(
        template_id="workout_card",
        data={
            "activity_type": "Running",
            "date": "2026-06-05T07:00:00+08:00",
            "duration_minutes": 45.5,
            "avg_heart_rate": 148,
            "max_heart_rate": 178,
            "distance_meters": 8500.0,
            "distance_unit": "km",
            "energy_burned_kj": 2500.0,
            "elevation_ascent_meters": 45.0,
        },
        narrative="Test.",
    )
    assert response.template_id == "workout_card"
    assert response.data["activity_type"] == "Running"


def test_chat_response_rejects_mismatched_data() -> None:
    """Data that doesn't match the template_id's schema is rejected."""
    # workout_card requires activity_type, date, etc.
    # Sending trend_chart-shaped data with template_id="workout_card" should fail
    with pytest.raises(ValidationError):
        ChatResponse(
            template_id="workout_card",
            data={
                "title": "Some Trend",
                "metric_label": "Steps",
                "metric_unit": "count",
                "granularity": "day",
                "series": [{"bucket": "2026-01-01", "value": 1000}],
            },
            narrative="Test.",
        )


def test_chat_response_accepts_fallback_data() -> None:
    """Valid fallback data passes."""
    response = ChatResponse(
        template_id="fallback",
        data={
            "question": "What is the meaning of life?",
            "table": None,
            "text": "I don't know.",
        },
        narrative="",
    )
    assert response.template_id == "fallback"


def test_chat_response_accepts_trend_chart_data() -> None:
    """Valid trend_chart data passes."""
    response = ChatResponse(
        template_id="trend_chart",
        data={
            "title": "RHR Trend",
            "metric_label": "Resting HR",
            "metric_unit": "bpm",
            "granularity": "week",
            "series": [
                {"bucket": "2026-W01", "value": 48},
                {"bucket": "2026-W02", "value": 47},
            ],
        },
        narrative="Steady.",
    )
    assert response.data["granularity"] == "week"
    assert len(response.data["series"]) == 2


def test_chat_response_unknown_template_id_passes_through() -> None:
    """Unknown template_ids should not be rejected (frontend handles fallback)."""
    response = ChatResponse(
        template_id="unknown_future_template",
        data={"any": "shape", "goes": True},
        narrative="",
    )
    assert response.template_id == "unknown_future_template"
    assert response.data["any"] == "shape"

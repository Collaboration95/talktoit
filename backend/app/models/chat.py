"""Pydantic models for the /api/chat request and response envelope."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from app.models.templates import (
    ComparisonData,
    FallbackData,
    PeriodSummaryData,
    RankedListData,
    TrendChartData,
    WorkoutCardData,
)

# Maps template_id → Pydantic model used for runtime data validation.
# When a ChatResponse carries template_id="workout_card", data is validated
# against WorkoutCardData before the response is returned to the client.
_TEMPLATE_MODELS: dict[str, type[BaseModel]] = {
    "workout_card": WorkoutCardData,
    "ranked_list": RankedListData,
    "trend_chart": TrendChartData,
    "period_summary": PeriodSummaryData,
    "comparison": ComparisonData,
    "fallback": FallbackData,
}


class ChatRequest(BaseModel):
    """Incoming chat request."""

    question: str


class ChatResponse(BaseModel):
    """Chat response envelope — matches SPEC §1.

    The ``data`` field is runtime-validated against the Pydantic model
    corresponding to ``template_id`` (R1-11).
    """

    template_id: str
    data: dict[str, Any]
    narrative: str

    @model_validator(mode="after")
    def _validate_data_against_template(self) -> ChatResponse:
        """Validate data against the model for the declared template_id.

        If template_id maps to a known model, data is parsed and re-serialised
        through that model to ensure shape correctness. Unknown template_ids
        pass through (the frontend handles them via the fallback path).
        """
        model = _TEMPLATE_MODELS.get(self.template_id)
        if model is not None:
            # Validate and round-trip through the model to catch shape errors.
            # This re-serialises with the model's defaults and type coercion,
            # ensuring the data dict conforms exactly to the template schema.
            validated = model.model_validate(self.data)
            self.data = validated.model_dump(mode="json", exclude_none=True)
        return self

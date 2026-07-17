"""Helpers for compacting tool output before it is sent to the narrator LLM."""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal


def _round_number(value: float | int) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compact_tool_result_for_llm(payload: object) -> object:
    """Recursively compact a tool payload for the narrative prompt.

    The goal is to reduce token use without changing the factual content:
    numbers are rounded to whole units, and large route geometry is omitted
    because the narrator does not need raw coordinates.
    """
    if isinstance(payload, dict):
        compact: dict[object, object] = {}
        for key, value in payload.items():
            if key == "gps_route":
                continue
            compact[key] = compact_tool_result_for_llm(value)
        return compact
    if isinstance(payload, list):
        return [compact_tool_result_for_llm(item) for item in payload]
    if isinstance(payload, float):
        return _round_number(payload)
    if isinstance(payload, int):
        return payload
    if isinstance(payload, date | datetime):
        return payload.isoformat()
    return payload

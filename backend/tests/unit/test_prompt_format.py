from __future__ import annotations

from app.llm.prompt_format import compact_tool_result_for_llm


def test_compact_tool_result_rounds_numbers_and_drops_gps_route() -> None:
    payload = {
        "activity_type": "Running",
        "duration_minutes": 61.05181868268979,
        "avg_heart_rate": 157.2,
        "max_heart_rate": 170.9,
        "distance_meters": 10020.4,
        "energy_burned_kj": 886.059,
        "gps_route": {
            "type": "LineString",
            "coordinates": [[103.8198, 1.3521], [103.8204, 1.3532]],
        },
    }

    compacted = compact_tool_result_for_llm(payload)

    assert compacted["duration_minutes"] == 61
    assert compacted["avg_heart_rate"] == 157
    assert compacted["max_heart_rate"] == 171
    assert compacted["distance_meters"] == 10020
    assert compacted["energy_burned_kj"] == 886
    assert "gps_route" not in compacted

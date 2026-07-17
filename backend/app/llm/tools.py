"""LLM tool definitions and implementations.

Each tool wraps a Phase-3 query function and returns the exact SPEC payload
shape. Raw DB rows never appear here — the LLM only sees the structured slice
defined in SPEC §4.
"""

from __future__ import annotations

import json
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

from app.db import queries
from app.db.data_profile import display_activity_type, resolve_activity_type
from app.models.templates import FallbackData

if TYPE_CHECKING:
    import duckdb

# ---------------------------------------------------------------------------
# Tool JSON-schema definitions (sent to the LLM)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_last_workout",
            "description": "Get the most recent workout of a given activity type",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_type": {
                        "type": "string",
                        "description": (
                            "Workout type e.g. Running, Cycling, TraditionalStrengthTraining"
                        ),
                    }
                },
                "required": ["activity_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_workouts",
            "description": "Get the top N workouts of a type ranked by a metric",
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_type": {"type": "string"},
                    "metric": {
                        "type": "string",
                        "enum": ["distance", "duration", "avg_hr", "energy"],
                    },
                    "n": {"type": "integer", "default": 5},
                    "start_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD, optional",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD, optional",
                    },
                },
                "required": ["activity_type", "metric"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_trend",
            "description": "Get a time-bucketed trend series for a health metric",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_id": {
                        "type": "string",
                        "description": (
                            "Apple Health metric identifier, e.g. "
                            "HKQuantityTypeIdentifierRestingHeartRate"
                        ),
                    },
                    "granularity": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                    },
                    "start_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD (inclusive)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD (inclusive)",
                    },
                },
                "required": ["metric_id", "granularity", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_period_summary",
            "description": "Get a summary of training metrics for a date range",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD (inclusive)",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD (inclusive)",
                    },
                    "title": {
                        "type": "string",
                        "description": "Optional override title for the summary",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_comparison",
            "description": "Compare training metrics between two consecutive periods",
            "parameters": {
                "type": "object",
                "properties": {
                    "this_start": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — start of current period",
                    },
                    "this_end": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — end of current period",
                    },
                    "last_start": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — start of prior period",
                    },
                    "last_end": {
                        "type": "string",
                        "description": "ISO date YYYY-MM-DD — end of prior period",
                    },
                    "this_label": {
                        "type": "string",
                        "description": "Human-readable label for the current period",
                    },
                    "last_label": {
                        "type": "string",
                        "description": "Human-readable label for the prior period",
                    },
                    "activity_type": {
                        "type": "string",
                        "description": "Optional activity type filter",
                    },
                },
                "required": [
                    "this_start",
                    "this_end",
                    "last_start",
                    "last_end",
                    "this_label",
                    "last_label",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fallback_answer",
            "description": "Use when no other tool fits the question",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Your best text answer to the question",
                    }
                },
                "required": ["text"],
            },
        },
    },
]

# Maps tool name → SPEC template_id
TOOL_TEMPLATE_IDS: dict[str, str] = {
    "get_last_workout": "workout_card",
    "get_top_workouts": "ranked_list",
    "get_trend": "trend_chart",
    "get_period_summary": "period_summary",
    "get_comparison": "comparison",
    "get_fallback_answer": "fallback",
}

# Stable tool-name ordering for prompt generation and validation.
TOOL_NAMES: tuple[str, ...] = tuple(TOOL_TEMPLATE_IDS)

# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------


def _tool_get_last_workout(
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
    question: str,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_last_workout tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        conn: Open DuckDB connection.
        question: The original user question (used for fallback).

    Returns:
        Tuple of (template_id, data_dict).
    """
    activity_type: str = resolve_activity_type(conn, args["activity_type"])
    result = queries.get_last_workout(conn, activity_type)
    if result is None:
        fallback = FallbackData(
            question=question,
            table=None,
            text=f"No {activity_type} workouts found.",
        )
        return ("fallback", fallback.model_dump(mode="json"))
    data = result.model_dump(mode="json")
    data["activity_type"] = display_activity_type(data["activity_type"])
    return ("workout_card", data)


def _tool_get_top_workouts(
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_top_workouts tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        conn: Open DuckDB connection.

    Returns:
        Tuple of (template_id, data_dict).
    """
    activity_type: str = resolve_activity_type(conn, args["activity_type"])
    metric: Literal["distance", "duration", "avg_hr", "energy"] = args["metric"]
    n: int = args.get("n", 5)
    start: date | None = date.fromisoformat(args["start_date"]) if args.get("start_date") else None
    end: date | None = date.fromisoformat(args["end_date"]) if args.get("end_date") else None
    result = queries.get_top_workouts(conn, activity_type, metric, n=n, start=start, end=end)
    data = result.model_dump(mode="json")
    data["title"] = data["title"].replace(activity_type, display_activity_type(activity_type))
    for row in data["rows"]:
        row["label"] = row["label"].replace(activity_type, display_activity_type(activity_type))
    return ("ranked_list", data)


def _tool_get_trend(
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_trend tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        conn: Open DuckDB connection.

    Returns:
        Tuple of (template_id, data_dict).
    """
    metric_id: str = args["metric_id"]
    granularity: Literal["day", "week", "month"] = args["granularity"]
    start = date.fromisoformat(args["start_date"])
    end = date.fromisoformat(args["end_date"])
    result = queries.get_trend(conn, metric_id, granularity, start, end)
    return ("trend_chart", result.model_dump(mode="json"))


def _tool_get_period_summary(
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_period_summary tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        conn: Open DuckDB connection.

    Returns:
        Tuple of (template_id, data_dict).
    """
    start = date.fromisoformat(args["start_date"])
    end = date.fromisoformat(args["end_date"])
    title: str | None = args.get("title")
    result = queries.get_period_summary(conn, start, end, title=title)
    return ("period_summary", result.model_dump(mode="json"))


def _tool_get_comparison(
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_comparison tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        conn: Open DuckDB connection.

    Returns:
        Tuple of (template_id, data_dict).
    """
    this_start = date.fromisoformat(args["this_start"])
    this_end = date.fromisoformat(args["this_end"])
    last_start = date.fromisoformat(args["last_start"])
    last_end = date.fromisoformat(args["last_end"])
    this_label: str = args["this_label"]
    last_label: str = args["last_label"]
    requested_type: str | None = args.get("activity_type")
    activity_type = (
        resolve_activity_type(conn, requested_type) if requested_type is not None else None
    )
    result = queries.get_comparison(
        conn,
        this_start,
        this_end,
        last_start,
        last_end,
        this_label,
        last_label,
        activity_type=activity_type,
    )
    data = result.model_dump(mode="json")
    if activity_type is not None:
        data["title"] = data["title"].replace(activity_type, display_activity_type(activity_type))
    return ("comparison", data)


def _tool_get_fallback_answer(
    args: dict[str, Any],
    question: str,
) -> tuple[str, dict[str, Any]]:
    """Dispatch the get_fallback_answer tool.

    Args:
        args: Parsed tool-call arguments from the LLM.
        question: The original user question.

    Returns:
        Tuple of (template_id, data_dict).
    """
    text: str = args.get("text", "")
    result = queries.get_fallback(question, text=text)
    return ("fallback", result.model_dump(mode="json"))


def normalize_tool_name(tool_name: str) -> str:
    """Canonicalize a tool name returned by the model.

    The regression that triggered this work used a leading tab before a valid
    tool name. Stripping surrounding whitespace keeps benign formatting noise
    from breaking dispatch.
    """
    return tool_name.strip()


def render_tool_catalog() -> str:
    """Render full function contracts so a text-only planner can supply arguments."""
    functions = [schema["function"] for schema in TOOL_SCHEMAS]
    return json.dumps(functions, indent=2)


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------


def dispatch_tool(
    tool_name: str,
    args: dict[str, Any],
    conn: duckdb.DuckDBPyConnection,
    question: str,
) -> tuple[str, dict[str, Any]]:
    """Dispatch a tool call to the appropriate query function.

    Args:
        tool_name: The name of the tool as returned by the LLM.
        args: Parsed JSON arguments from the tool call.
        conn: Open DuckDB connection.
        question: The original user question (used for fallback payloads).

    Returns:
        Tuple of (template_id, data_dict) where data_dict is the serialized
        SPEC payload. The data_dict is safe to pass directly to the LLM —
        no raw DB rows are included.

    Raises:
        ValueError: When ``tool_name`` is not a recognised tool.
    """
    tool_name = normalize_tool_name(tool_name)
    if tool_name == "get_last_workout":
        return _tool_get_last_workout(args, conn, question)
    if tool_name == "get_top_workouts":
        return _tool_get_top_workouts(args, conn)
    if tool_name == "get_trend":
        return _tool_get_trend(args, conn)
    if tool_name == "get_period_summary":
        return _tool_get_period_summary(args, conn)
    if tool_name == "get_comparison":
        return _tool_get_comparison(args, conn)
    if tool_name == "get_fallback_answer":
        return _tool_get_fallback_answer(args, question)
    msg = f"Unknown tool: {tool_name!r}"
    raise ValueError(msg)

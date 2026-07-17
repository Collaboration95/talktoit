"""Chat orchestrator: question → LLM plan → local dispatch → template envelope.

One-shot design (no history). The LLM is given the tool catalog and calls
exactly one tool per question. Robust to: malformed planner output,
unknown tool names, tool errors, and empty data.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

import openai

from app.db.data_profile import get_data_profile
from app.db.queries import get_fallback
from app.llm.client import DEFAULT_MODEL
from app.llm.local_planner import plan_local_question
from app.llm.prompt_format import compact_tool_result_for_llm
from app.llm.tools import TOOL_NAMES, dispatch_tool, normalize_tool_name, render_tool_catalog
from app.models.chat import ChatResponse
from app.models.templates import FallbackData

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

_PLANNER_PROMPT = """You are a planning assistant for a personal health data app.
Choose exactly one tool for the user's question and return only a JSON object.

Allowed tools:
{tool_catalog}

Return JSON with this shape:
{{
  "tool_name": "get_last_workout",
  "arguments": {{}}
}}

Rules:
1. tool_name must be one of: {tool_names}
2. Use get_fallback_answer if no other tool fits the question.
3. Keep arguments valid JSON and only include fields the tool accepts.
4. Interpret date ranges in the Asia/Singapore timezone.
5. Dataset context (generated locally): {data_context}
6. Use the dataset's "today" when resolving relative dates, never the computer clock.
7. Map common wording as follows: run/jog → Running; bike → Cycling;
   gym/weights → Traditional Strength Training. For "longest", rank by duration;
   for "highest heart rate", rank by avg_hr.
8. For a request to compare periods, use get_comparison. For training volume in a
   single period, use get_period_summary. For a metric over time, use get_trend.
"""

_NARRATIVE_PROMPT = """You are a personal health data assistant for an Apple Health user.
You have already received the tool result for the user's question.

Rules:
1. Write a short narrative (1-2 sentences) that answers naturally.
2. Never mention raw database rows, SQL, JSON, or implementation details.
3. Be concise and friendly.
4. The user's timezone is Asia/Singapore (+0800).
5. The local dataset is current through {today}; use that date for relative language.
6. State only facts present in the tool result. Do not call a workout long, intense,
   or a best effort unless the result itself establishes that claim.
"""


def _make_fallback_response(question: str, narrative: str = "") -> ChatResponse:
    """Build a fallback ChatResponse for error cases.

    Args:
        question: The original user question.
        narrative: Optional narrative text for the response.

    Returns:
        A :class:`ChatResponse` with template_id ``"fallback"``.
    """
    fallback: FallbackData = get_fallback(question)
    return ChatResponse(
        template_id="fallback",
        data=fallback.model_dump(mode="json"),
        narrative=narrative,
    )


def _parse_tool_plan(content: str | None) -> dict[str, Any] | None:
    """Parse the model's planner response into a JSON object.

    The planner is instructed to return a single JSON object, but this helper
    still tolerates fenced code blocks or surrounding text so the caller can
    fall back cleanly when the model drifts.
    """
    if not content:
        return None

    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("LLM planner returned invalid JSON")
        return None

    if not isinstance(payload, dict):
        logger.warning("LLM planner returned a non-object payload")
        return None

    return payload


def _validated_plan(plan: dict[str, Any] | None) -> tuple[str, dict[str, Any]] | None:
    """Validate a model or local planner payload before dispatching it."""
    if plan is None:
        return None

    raw_tool_name = plan.get("tool_name", "")
    if not isinstance(raw_tool_name, str):
        return None
    tool_name = normalize_tool_name(raw_tool_name)
    if tool_name not in TOOL_NAMES:
        return None

    args = plan.get("arguments", {})
    if not isinstance(args, dict):
        return None
    return tool_name, args


def _local_narrative(template_id: str, data: dict[str, Any]) -> str:
    """Provide a useful answer if only the optional remote narrator failed."""
    if template_id == "workout_card":
        return "Here is your most recent workout."
    if template_id == "ranked_list":
        return "Here is the ranked list for your question."
    if template_id == "trend_chart":
        return "Here is the trend for your question."
    if template_id == "period_summary":
        return "Here is your training summary."
    if template_id == "comparison":
        return "Here is the comparison for your selected periods."
    return "I found the matching data in your local health database."


class ChatOrchestrator:
    """Orchestrates one-shot LLM planning to answer health questions.

    Attributes:
        client: The async OpenAI-compatible client.
        conn: Open DuckDB connection for the request lifetime.
        model: LLM model identifier string.
    """

    def __init__(
        self,
        client: openai.AsyncOpenAI,
        conn: duckdb.DuckDBPyConnection,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialise the orchestrator.

        Args:
            client: An async OpenAI-compatible client (injectable for tests).
            conn: Open DuckDB connection.
            model: LLM model identifier.
        """
        self.client = client
        self.conn = conn
        self.model = model

    async def answer(self, question: str) -> ChatResponse:
        """Process a question and return a structured chat response.

        Sends the question to the LLM with all tool schemas. The LLM must
        call exactly one tool. The tool result populates ``data``; the LLM
        then composes the ``narrative``.

        Args:
            question: The natural-language health question from the user.

        Returns:
            A :class:`ChatResponse` envelope with ``template_id``, ``data``,
            and ``narrative``.
        """
        data_profile = get_data_profile(self.conn)
        today = (data_profile.latest_date or date.today()).isoformat()
        planner_prompt = _PLANNER_PROMPT.format(
            today=today,
            data_context=data_profile.planner_summary(),
            tool_catalog=render_tool_catalog(),
            tool_names=", ".join(TOOL_NAMES),
        )
        planner_messages: list[dict[str, Any]] = [
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": question},
        ]

        # ── Turn 1: plan the tool call ───────────────────────────────────────
        # Recognised time and activity phrases are resolved locally first for
        # correctness, while the model remains available for open-ended input.
        local_plan = _validated_plan(plan_local_question(question, data_profile))
        used_local_plan = local_plan is not None
        plan: dict[str, Any] | None = None
        try:
            planner_response = await self.client.chat.completions.create(
                model=self.model,
                messages=planner_messages,  # type: ignore[arg-type]
                temperature=0,
            )
            if planner_response.choices:
                plan = _parse_tool_plan(planner_response.choices[0].message.content)
            else:
                logger.warning("LLM planner returned no choices")
        except Exception:
            logger.exception("LLM planner request failed")

        resolved_plan = local_plan or _validated_plan(plan)
        if local_plan is not None:
            logger.info("Using deterministic local plan for recognised question")
        if resolved_plan is None:
            return _make_fallback_response(question)
        tool_name, args = resolved_plan

        # ── Execute the tool ─────────────────────────────────────────────────
        try:
            template_id, data_dict = dispatch_tool(tool_name, args, self.conn, question)
        except Exception:
            logger.exception("Tool dispatch failed for tool %r", tool_name)
            return _make_fallback_response(question)

        narrative_prompt = _NARRATIVE_PROMPT.format(today=today)
        compact_result = json.dumps(
            compact_tool_result_for_llm(data_dict),
            default=str,
            separators=(",", ":"),
        )
        narrative_messages: list[dict[str, Any]] = [
            {"role": "system", "content": narrative_prompt},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Tool used: {tool_name}\n\n"
                    f"Tool result (rounded and compact):\n"
                    f"{compact_result}"
                ),
            },
        ]

        # ── Turn 2: narrative ────────────────────────────────────────────────
        if used_local_plan and template_id == "trend_chart":
            return ChatResponse(
                template_id=template_id,
                data=data_dict,
                narrative=_local_narrative(template_id, data_dict),
            )

        try:
            narrative_response = await self.client.chat.completions.create(
                model=self.model,
                messages=narrative_messages,  # type: ignore[arg-type]
            )
            narrative = narrative_response.choices[0].message.content or ""
        except Exception:
            logger.exception("LLM narrative request failed")
            narrative = _local_narrative(template_id, data_dict)

        return ChatResponse(
            template_id=template_id,
            data=data_dict,
            narrative=narrative,
        )

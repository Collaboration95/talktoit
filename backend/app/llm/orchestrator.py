"""Chat orchestrator: question → LLM plan → local dispatch → template envelope.

One-shot design (no history). The LLM is given the tool catalog and calls
exactly one tool per question. Robust to: malformed planner output,
unknown tool names, tool errors, and empty data.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any, Literal

import openai

from app.db.data_profile import get_data_profile
from app.db.queries import get_fallback
from app.llm.client import DEFAULT_MODEL
from app.llm.local_planner import plan_local_question
from app.llm.prompt_format import compact_tool_result_for_llm
from app.llm.provider_gateway import ProviderGateway, ProviderUnavailableError
from app.llm.tools import TOOL_NAMES, dispatch_tool, normalize_tool_name, render_tool_catalog
from app.models.chat import ChatResponse, ResponseMetadata
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
        metadata=ResponseMetadata(provenance="fallback"),
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
        gateway: ProviderGateway | None = None,
    ) -> None:
        """Initialise the orchestrator.

        Args:
            client: An async OpenAI-compatible client (injectable for tests).
            conn: Open DuckDB connection.
            model: LLM model identifier.
            gateway: Optional app-owned provider lifecycle gateway.
        """
        self.client = client
        self.conn = conn
        self.model = model
        self.gateway = gateway

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

        # ── Stage 1: deterministic local plan ────────────────────────────────
        # A recognised question must not touch the optional provider. This is
        # both the privacy boundary and the fast path for ordinary use.
        local_plan = _validated_plan(plan_local_question(question, data_profile))
        if local_plan is not None:
            tool_name, args = local_plan
            try:
                template_id, data_dict = dispatch_tool(tool_name, args, self.conn, question)
            except Exception:
                logger.exception("Local tool dispatch failed for tool %r", tool_name)
                return _make_fallback_response(question)
            return ChatResponse(
                template_id=template_id,
                data=data_dict,
                narrative=_local_narrative(template_id, data_dict),
                metadata=ResponseMetadata(provenance="deterministic_local"),
            )

        # ── Stage 2: optional remote plan for unresolved wording ────────────
        plan: dict[str, Any] | None = None
        try:
            planner_content = await self._complete_provider("planning", planner_messages)
            plan = _parse_tool_plan(planner_content)
        except ProviderUnavailableError:
            logger.info("Remote planner unavailable or disabled")

        resolved_plan = _validated_plan(plan)
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
        try:
            narrative = await self._complete_provider("narration", narrative_messages)
        except ProviderUnavailableError:
            logger.info("Remote narrator unavailable or disabled")
            narrative = _local_narrative(template_id, data_dict)

        return ChatResponse(
            template_id=template_id,
            data=data_dict,
            narrative=narrative,
            metadata=ResponseMetadata(provenance="remote_planned"),
        )

    async def _complete_provider(
        self, stage: Literal["planning", "narration"], messages: list[dict[str, Any]]
    ) -> str:
        """Use the process gateway when available; preserve CLI/test injection."""
        if self.gateway is not None:
            return await self.gateway.complete(stage, messages)
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("Remote provider is unavailable") from exc
        if not response.choices:
            raise ProviderUnavailableError("Remote provider returned no answer")
        return response.choices[0].message.content or ""

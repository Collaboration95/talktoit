"""Chat orchestrator: question → LLM tool call → template envelope.

One-shot design (no history). The LLM is given the tool catalog and calls
exactly one tool per question. Robust to: unknown template_id from model,
tool errors, empty data.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import openai
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
)

from app.db.queries import get_fallback
from app.llm.client import DEFAULT_MODEL
from app.llm.tools import TOOL_SCHEMAS, dispatch_tool
from app.models.chat import ChatResponse
from app.models.templates import FallbackData

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a personal health data assistant for an Apple Health user.
You have access to tools that query the user's health data stored in a local DuckDB database.

Rules:
1. Always call exactly one tool to answer the question.
2. Use get_fallback_answer for questions you cannot answer with the other tools.
3. After the tool returns data, write a short narrative (1-2 sentences) that frames the result naturally.
4. Never mention raw database rows, SQL, or technical implementation details.
5. Be concise and friendly.

The user's timezone is Asia/Singapore (+0800). All date references in your tool calls should use this timezone context.
Today's date: {today}
"""  # noqa: E501


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


class ChatOrchestrator:
    """Orchestrates one-shot LLM tool calls to answer health questions.

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
        system_prompt = _SYSTEM_PROMPT.format(today=date.today().isoformat())
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # ── Turn 1: force a tool call ────────────────────────────────────────
        try:
            tool_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
                tool_choice="required",
            )
        except Exception:
            logger.exception("LLM tool-call request failed")
            return _make_fallback_response(question)

        # ── Extract tool call ────────────────────────────────────────────────
        choice = tool_response.choices[0]
        assistant_message = choice.message

        if not assistant_message.tool_calls:
            logger.warning("LLM returned no tool calls — falling back")
            return _make_fallback_response(question)

        raw_tool_call = assistant_message.tool_calls[0]
        if not hasattr(raw_tool_call, "function"):
            logger.warning("LLM returned a non-function tool call — falling back")
            return _make_fallback_response(question)
        tool_call = cast(ChatCompletionMessageFunctionToolCall, raw_tool_call)
        tool_name = tool_call.function.name
        tool_call_id = tool_call.id

        try:
            args: dict[str, Any] = json.loads(tool_call.function.arguments)
        except (json.JSONDecodeError, ValueError):
            logger.exception("Failed to parse tool call arguments")
            return _make_fallback_response(question)

        # ── Execute the tool ─────────────────────────────────────────────────
        try:
            template_id, data_dict = dispatch_tool(tool_name, args, self.conn, question)
        except Exception:
            logger.exception("Tool dispatch failed for tool %r", tool_name)
            return _make_fallback_response(question)

        # ── Build messages for the narrative turn ────────────────────────────
        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": tool_call.function.arguments,
                        },
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(data_dict, default=str),
            }
        )

        # ── Turn 2: narrative ────────────────────────────────────────────────
        try:
            narrative_response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
            )
            narrative = narrative_response.choices[0].message.content or ""
        except Exception:
            logger.exception("LLM narrative request failed")
            narrative = ""

        return ChatResponse(
            template_id=template_id,
            data=data_dict,
            narrative=narrative,
        )

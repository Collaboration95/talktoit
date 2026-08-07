"""Local semantic candidates over past answered questions (P6-03).

Fully local and deterministic: question text is normalized and ranked with
token/bigram overlap, and a *strict verifier* decides whether a candidate's
stored canonical intent is provably identical to the current one. Only proven
identical intents are eligible for automatic reuse; anything less stays a
cache miss or a user-confirmed "similar prior answer" choice.

No remote embedding service is ever called and no health values, routes, or
raw records leave the machine.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_ALPHANUMERIC = re.compile(r"[a-z0-9]+")

# English health-query stop words. Removed before ranking; they carry no
# intent signal ("show", "me", "the", "my" ...).
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for from has have how i in into is it its me my
    of on or so the this that to was we what when where which who will with you
    your show tell please can could would should
    """.split()
)

# Semantic argument keys per tool. Cosmetic keys (labels, titles) and keys that
# do not change the query result are excluded so identical intents written in
# different words still verify equal.
_SIGNIFICANT_KEYS: dict[str, tuple[str, ...]] = {
    "get_last_workout": ("activity_type", "min_duration_minutes"),
    "get_top_workouts": ("activity_type", "metric", "n", "start_date", "end_date"),
    "get_trend": ("metric_id", "granularity", "start_date", "end_date"),
    "get_period_summary": ("start_date", "end_date"),
    "get_comparison": (
        "this_start",
        "this_end",
        "last_start",
        "last_end",
        "activity_type",
    ),
    "get_fallback_answer": (),
}


def normalize_question(text: str) -> str:
    """Reduce a question to intent-bearing search tokens.

    Returns a space-joined, casefolded token stream with stop words removed.
    Numbers are preserved so "run 5k" differs from "run 10k".
    """
    tokens = [
        token
        for token in _ALPHANUMERIC.findall(str(text).casefold())
        if token not in _STOPWORDS and len(token) > 1
    ]
    return " ".join(tokens)


def _token_set(normalized: str) -> frozenset[str]:
    return frozenset(normalized.split())


def _bigrams(normalized: str) -> frozenset[tuple[str, str]]:
    tokens = normalized.split()
    return frozenset((tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1))


def similarity(left: str, right: str) -> float:
    """Dice coefficient over token bigrams with a token-overlap bonus.

    Returns a float in [0.0, 1.0]. Equal normalized text scores 1.0; texts
    with no shared tokens score 0.0.
    """
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    left_bigrams, right_bigrams = _bigrams(left), _bigrams(right)
    if not left_bigrams or not right_bigrams:
        shared = len(_token_set(left) & _token_set(right))
        return shared / (len(_token_set(left)) + len(_token_set(right)) - shared or 1)
    dice = 2.0 * len(left_bigrams & right_bigrams) / (len(left_bigrams) + len(right_bigrams))
    shared_tokens = len(_token_set(left) & _token_set(right))
    token_bonus = 0.5 * shared_tokens / max(len(_token_set(left)), len(_token_set(right)), 1)
    return min(1.0, dice + token_bonus)


def significant_keys(tool_name: str) -> tuple[str, ...]:
    """Return the intent-bearing argument keys for a validated tool."""
    return _SIGNIFICANT_KEYS.get(tool_name, ("tool_name",))


def plan_fingerprint(tool_name: str, args: Mapping[str, Any]) -> tuple[Any, ...]:
    """Serialize one canonical intent into a hashable, comparable tuple.

    Missing keys compare equal to a missing key on the other side, so plans
    produced with defaulted arguments still match.
    """
    keys = significant_keys(tool_name)
    values: list[Any] = []
    for key in keys:
        value = args.get(key)
        if isinstance(value, str):
            value = value.casefold().strip()
        values.append(value)
    return tuple(values)


def _plan_of(record: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]] | None:
    """Parse a stored turn's canonical plan, if any."""
    raw = record.get("canonical_plan_json")
    if not isinstance(raw, str):
        return None
    try:
        plan = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(plan, dict):
        return None
    tool_name = plan.get("tool_name")
    args = plan.get("arguments")
    if not isinstance(tool_name, str) or not isinstance(args, dict):
        return None
    return tool_name, args


@dataclass(frozen=True)
class SemanticCandidate:
    """One stored turn that textually resembles the current question."""

    turn_id: str
    conversation_id: str
    question: str
    response_json: str
    score: float
    identical: bool


@dataclass(frozen=True)
class CandidateVerdict:
    """Outcome of semantic candidate retrieval."""

    identical: SemanticCandidate | None
    similar: tuple[SemanticCandidate, ...]
    considered: int

    @property
    def auto_servable(self) -> bool:
        """True only for a proven identical canonical intent."""
        return self.identical is not None


def _find_candidates(
    records: Sequence[Mapping[str, Any]],
    current_normalized: str,
    limit: int,
) -> list[tuple[float, Mapping[str, Any]]]:
    """Rank completed turns by textual similarity to the current question."""
    scored: list[tuple[float, Mapping[str, Any]]] = []
    for record in records:
        stored_normalized = record.get("normalized_question")
        if not isinstance(stored_normalized, str) or not stored_normalized:
            continue
        score = similarity(current_normalized, stored_normalized)
        if score <= 0.0:
            continue
        scored.append((score, record))
    scored.sort(key=lambda pair: (pair[0], str(pair[1].get("created_at", ""))), reverse=True)
    return scored[:limit]


def evaluate(
    records: Sequence[Mapping[str, Any]],
    question: str,
    plan: tuple[str, Mapping[str, Any]] | None,
    *,
    limit: int = 5,
    min_score: float = 0.35,
) -> CandidateVerdict:
    """Rank prior turns and classify them against the current intent.

    Args:
        records: Completed turns scoped to the active dataset (id,
            conversation_id, question, response_json, created_at,
            canonical_plan_json, normalized_question).
        question: The current user question (un-normalized).
        plan: The current validated (tool_name, arguments) plan, or None.
        limit: Maximum number of similar candidates to return.
        min_score: Minimum textual similarity to be considered at all.

    Returns:
        A :class:`CandidateVerdict` with at most one identical candidate and a
        ranked list of similar ones. Identical matching requires a stored
        canonical plan whose significant arguments exactly match ``plan``.
    """
    current_normalized = normalize_question(question)
    by_id = {str(record.get("id")): record for record in records}
    ranked = _find_candidates(records, current_normalized, limit=limit * 4)
    identical: SemanticCandidate | None = None
    similar: list[SemanticCandidate] = []
    for score, record in ranked:
        candidate = SemanticCandidate(
            turn_id=str(record["id"]),
            conversation_id=str(record.get("conversation_id", "")),
            question=str(record.get("question", "")),
            response_json=str(record.get("response_json", "") or ""),
            score=round(score, 4),
            identical=False,
        )
        stored_plan = _plan_of(by_id.get(candidate.turn_id, record))
        is_identical = False
        if plan is not None and stored_plan is not None and candidate.response_json:
            current_tool, current_args = plan
            stored_tool, stored_args = stored_plan
            is_identical = current_tool == stored_tool and plan_fingerprint(
                current_tool, current_args
            ) == plan_fingerprint(stored_tool, stored_args)
        if is_identical and identical is None:
            identical = SemanticCandidate(
                turn_id=candidate.turn_id,
                conversation_id=candidate.conversation_id,
                question=candidate.question,
                response_json=candidate.response_json,
                score=candidate.score,
                identical=True,
            )
            continue
        if candidate.score >= min_score:
            similar.append(candidate)
    return CandidateVerdict(
        identical=identical, similar=tuple(similar[:limit]), considered=len(ranked)
    )


# Public alias used by tests and callers that want a simpler name.
find_candidates = evaluate


def candidates_enabled() -> bool:
    """Whether the local semantic- candidate path is enabled.

    Local text matching is deterministic and safe by default; operators can
    disable it with the ``TTI_DISABLE_SEMANTIC_CANDIDATES`` environment flag
    (e.g. ``1``, ``true``).
    """
    return os.environ.get("TTI_DISABLE_SEMANTIC_CANDIDATES", "0").casefold() not in {
        "1",
        "true",
        "yes",
    }

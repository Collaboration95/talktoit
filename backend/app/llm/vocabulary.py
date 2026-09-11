"""Shared vocabulary and conservative matching for workout language."""

from __future__ import annotations

import re

_WORKOUT_WORDS = re.compile(
    r"\b(run(?:s|ning)?|jog(?:s|ging)?|ride(?:s|r)?|cycling|bike(?:s)?|workout(?:s)?|session(?:s)?)\b"
)
_ACTIVITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Running", re.compile(r"\b(?:run|runs|running|jog|jogs|jogging)\b")),
    ("Cycling", re.compile(r"\b(?:bike|bikes|biking|cycle|cycles|cycling|ride|rides|riding)\b")),
    (
        "TraditionalStrengthTraining",
        re.compile(r"\b(?:gym|weight(?:s|lifting)?|strength)\b"),
    ),
)


def activity_type_from_question(question: str) -> str | None:
    """Return an activity only when its phrase is a whole-word workout term."""
    lower = question.casefold()
    if not _WORKOUT_WORDS.search(lower):
        return None
    words = re.findall(r"[a-z0-9]+", lower)
    allowed_context = {
        "my",
        "last",
        "latest",
        "most",
        "recent",
        "long",
        "longest",
        "top",
        "the",
        "a",
        "an",
        "which",
        "show",
        "me",
        "this",
        "that",
        "highest",
        "by",
        "5",
        "one",
        "workout",
        "workouts",
        "session",
        "sessions",
        "ride",
        "rides",
        "run",
        "runs",
    }
    for activity, pattern in _ACTIVITY_PATTERNS:
        match = pattern.search(lower)
        if match is None:
            continue
        index = len(re.findall(r"[a-z0-9]+", lower[: match.start()]))
        previous = words[index - 1] if index > 0 else ""
        following = words[index + 1] if index + 1 < len(words) else ""
        if previous in allowed_context or following in allowed_context:
            return activity
    return None


def contains_word(question: str, word: str) -> bool:
    """Match a complete vocabulary word, avoiding substring false positives."""
    return re.search(rf"\b{re.escape(word)}\b", question.casefold()) is not None

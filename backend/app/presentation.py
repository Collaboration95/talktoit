"""Shared readable local date labels for deterministic answers and plans."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_date(value: date | datetime | str) -> str:
    """Format a local calendar day, converting aware timestamps to Singapore time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.astimezone(ZoneInfo("Asia/Singapore"))
    return f"{value.day} {_MONTHS[value.month - 1]} {value.year}"


def format_date_range(start: date, end: date) -> str:
    """Format both inclusive bounds without losing year information."""
    return f"{format_date(start)} to {format_date(end)}"

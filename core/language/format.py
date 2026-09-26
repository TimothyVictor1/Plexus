"""Durations as a person would say them (redesign B2).

Every duration crosses the API twice: once as a number for anything that needs to compute,
and once as the sentence the screen shows. The screen never does the rounding itself.
"""

from __future__ import annotations

from pydantic import BaseModel

MINUTE = 60.0
HOUR = 3600.0
DAY = 86400.0
WEEK = 7 * DAY


class Duration(BaseModel):
    seconds: float
    text: str


def humanise(seconds: float) -> str:
    """A rough, readable duration. Deliberately vague: 'about 2 days', never '1.93 days'."""
    if seconds <= 0:
        return "no time at all"
    if seconds < 90 * MINUTE:
        minutes = max(1, round(seconds / MINUTE))
        return "about a minute" if minutes == 1 else f"about {minutes} minutes"
    if seconds < 20 * HOUR:
        hours = round(seconds / HOUR)
        return "about an hour" if hours == 1 else f"about {hours} hours"
    if seconds < 14 * DAY:
        # Half-day precision reads naturally under a fortnight, and a day and a half is a
        # meaningfully different answer from a day.
        rounded = round((seconds / DAY) * 2) / 2
        if rounded <= 1:
            return "about a day"
        if rounded == 1.5:
            return "about a day and a half"
        whole = int(rounded)
        return f"about {whole} days" if rounded == whole else f"about {rounded:.1f} days"
    if seconds < 10 * WEEK:
        weeks = round(seconds / WEEK)
        return "about a week" if weeks == 1 else f"about {weeks} weeks"
    months = round(seconds / (30 * DAY))
    return "about a month" if months == 1 else f"about {months} months"


def duration(seconds: float) -> Duration:
    return Duration(seconds=round(seconds, 1), text=humanise(seconds))

"""Turning mined structure into words a non-technical person can act on (redesign B2)."""

from core.language.format import Duration, duration, humanise
from core.language.service import ProcessLanguage, describe_process, set_override

__all__ = [
    "Duration",
    "ProcessLanguage",
    "describe_process",
    "duration",
    "humanise",
    "set_override",
]

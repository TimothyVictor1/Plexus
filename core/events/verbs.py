"""Fixed verb vocabulary (spec 02). New verbs arrive only via an OntologyProposal."""

from __future__ import annotations

VERBS: frozenset[str] = frozenset(
    {
        "sent",
        "replied",
        "forwarded",
        "created",
        "updated",
        "deleted",
        "changed_status",
        "assigned",
        "attached",
        "commented",
        "requested",
        "offered",
        "accepted",
        "rejected",
        "approved",
        "paid",
        "invoiced",
        "scheduled",
        "attended",
        "published",
        "decided",
        "committed",
    }
)


def is_known(verb: str) -> bool:
    return verb in VERBS

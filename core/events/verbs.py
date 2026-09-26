"""Fixed verb vocabulary (spec 02). New verbs arrive only via an OntologyProposal.

The second block was added for the industry-neutral demo processes. Each one names a real
state change that the original list could not express without stretching a verb past its
meaning, which is exactly the review the OntologyProposal flow exists to perform.
"""

from __future__ import annotations

VERBS: frozenset[str] = frozenset(
    {
        # original vocabulary
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
        # added for the neutral demo processes
        "resolved",  # a customer request was closed out
        "delivered",  # the work itself was finished
        "ordered",  # an order was placed with a supplier
        "received",  # goods or services arrived
        "submitted",  # something was handed in for checking
        "reimbursed",  # money was paid back to a person
        "signed",  # a contract was signed
        "started",  # a person's first working day
    }
)


def is_known(verb: str) -> bool:
    return verb in VERBS

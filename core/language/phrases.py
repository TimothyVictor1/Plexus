"""Rule-based wording, used when no person has renamed something and no model is reachable.

This is the floor, not the ceiling: the screen is always readable, even with the network
unplugged and nothing cached.
"""

from __future__ import annotations

# What each recorded verb means in a sentence an office manager would use.
VERB_LABEL: dict[str, str] = {
    "requested": "Request comes in",
    "replied": "First reply",
    "resolved": "Solved",
    "offered": "Quote sent",
    "accepted": "Accepted",
    "delivered": "Work done",
    "invoiced": "Invoice sent",
    "paid": "Paid",
    "ordered": "Order placed",
    "received": "Goods arrive",
    "approved": "Approved",
    "rejected": "Turned down",
    "submitted": "Handed in",
    "reimbursed": "Paid back",
    "signed": "Contract signed",
    "started": "First day",
    "created": "Created",
    "sent": "Sent",
    "updated": "Updated",
    "assigned": "Given to someone",
    "attached": "Document added",
    "commented": "Comment added",
    "scheduled": "Booked in",
    "attended": "Meeting held",
    "published": "Published",
    "decided": "Decided",
    "committed": "Promised",
    "changed_status": "Status changed",
    "forwarded": "Passed on",
    "deleted": "Removed",
}

# The wait between two specific steps, where a plain phrase beats a generic one.
TRANSITION_PHRASE: dict[tuple[str, str], str] = {
    ("delivered", "invoiced"): "sending the invoice after the work is done",
    ("created", "invoiced"): "sending the invoice after the work is done",
    ("invoiced", "paid"): "waiting for the customer to pay",
    ("requested", "replied"): "waiting for the first reply",
    ("replied", "resolved"): "finishing off the request",
    ("offered", "accepted"): "waiting for the customer to decide",
    ("requested", "approved"): "waiting for approval",
    ("approved", "ordered"): "placing the order once it is approved",
    ("ordered", "received"): "waiting for the goods to arrive",
    ("signed", "created"): "getting accounts ready",
    ("created", "attached"): "getting equipment ready",
    ("attached", "started"): "waiting for the first day",
    ("submitted", "approved"): "checking the receipt",
    ("approved", "reimbursed"): "paying the money back",
    ("created", "sent"): "putting the report together",
    ("sent", "approved"): "waiting for approval",
}


def step_label(verb: str) -> str:
    return VERB_LABEL.get(verb, verb.replace("_", " ").capitalize())


def transition_phrase(source: str, target: str) -> str:
    known = TRANSITION_PHRASE.get((source, target))
    if known:
        return known
    return f"the wait between {step_label(source).lower()} and {step_label(target).lower()}"


def process_name(steps: list[str]) -> str:
    if not steps:
        return "Work with no clear steps yet"
    if len(steps) == 1:
        return step_label(steps[0])
    return f"From {step_label(steps[0]).lower()} to {step_label(steps[-1]).lower()}"


def process_description(steps: list[str]) -> str:
    if len(steps) < 2:
        return "Plexus has not seen enough of this yet to describe it."
    first, last = step_label(steps[0]).lower(), step_label(steps[-1]).lower()
    return f"From {first} until {last}"


def help_tip(source: str, target: str) -> str:
    return (
        f"The longest wait is {transition_phrase(source, target)}. "
        "Plexus can watch for it and remind the right person, or prepare the next step for them."
    )


# What each connected source is called on screen. Categories, never product names, because
# the same category can be served by any vendor.
TOOL_LABEL: dict[str, str] = {
    "email": "Email",
    "calendar": "Calendar",
    "crm": "Customer system",
    "accounting": "Accounting",
    "files": "Files",
    "hr": "HR system",
    "chat": "Team chat",
    "projects": "Projects and tasks",
}


def tool_label(source_id: str) -> str:
    return TOOL_LABEL.get(source_id, source_id.replace("_", " ").capitalize())


def tool_list(source_ids: list[str]) -> str:
    """'Email and Accounting', or 'Email, Files and Accounting'."""
    names = [tool_label(s) for s in source_ids]
    if not names:
        return "your tools"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"

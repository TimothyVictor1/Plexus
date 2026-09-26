"""The demo dataset must be deterministic and industry-neutral (redesign B1)."""

from __future__ import annotations

import re

from core.events.verbs import is_known
from core.pii.recognisers import valid_orgnr, valid_personnummer
from scripts.fixtures.demo import (
    DEMO_ORG_NAME,
    DEMO_TENANT,
    PROCESS_SPECS,
    build,
    check_digit,
    orgnr,
    pnr,
)

# Words that would tie the demo to one industry or one customer.
FORBIDDEN = re.compile(r"nordvik|konsult ab|karlskrona|blekinge|tcl", re.IGNORECASE)


def test_build_is_deterministic() -> None:
    a, b = build(seed=11), build(seed=11)
    assert a.labels["counts"] == b.labels["counts"]
    assert [i["external_id"] for i in a.items["email"]] == [
        i["external_id"] for i in b.items["email"]
    ]


def test_different_seeds_differ() -> None:
    assert build(seed=1).items["email"][0]["body"] != build(seed=2).items["email"][0]["body"]


def test_no_industry_or_customer_specific_names() -> None:
    offenders: list[str] = []
    for source, items in build().items.items():
        for item in items:
            blob = f"{item.get('subject', '')} {item.get('body', '')}"
            if FORBIDDEN.search(blob):
                offenders.append(f"{source}:{item['external_id']}")
    assert not offenders, f"industry-specific content in demo data: {offenders[:5]}"


def test_org_name_is_neutral() -> None:
    assert not FORBIDDEN.search(DEMO_ORG_NAME)
    assert DEMO_TENANT == "demo"


def test_every_verb_is_in_the_vocabulary() -> None:
    unknown = {
        step.verb for spec in PROCESS_SPECS for step in spec.steps if not is_known(step.verb)
    }
    assert not unknown, f"verbs outside the vocabulary: {unknown}"


def test_six_neutral_processes_with_one_clear_bottleneck_each() -> None:
    expected = {
        "customer_requests",
        "quote_to_payment",
        "purchasing",
        "new_hires",
        "monthly_reporting",
        "expenses",
    }
    assert {s.key for s in PROCESS_SPECS} == expected
    for spec in PROCESS_SPECS:
        waits = [s.wait_days for s in spec.steps[1:]]
        assert waits, f"{spec.key} has no waits"
        assert max(waits) > 0


def test_generated_identity_numbers_validate() -> None:
    assert valid_personnummer(pnr("850312456"))
    assert valid_orgnr(orgnr("556677889"))
    assert check_digit("556677889") == "9"


def test_injection_payloads_are_planted_for_the_immune_system() -> None:
    files = build().items["files"]
    planted = [i for i in files if i.get("injection")]
    assert len(planted) >= 4

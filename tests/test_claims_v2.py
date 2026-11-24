"""The finish-claim rule for v2 (docs/PLAN-V2.md section 4.3, review R3)."""
from __future__ import annotations

from dbench.tasks import ClaimCheck, ClaimItem, claim_item_problems, entry_names

ITEMS = [ClaimItem("invoice C-031", ["C-031"], deliverable=False),
         ClaimItem("invoice C-007", ["C-007"], deliverable=True),
         ClaimItem("invoice C-012", ["C-012", "INV-2026-10-012"], deliverable=True)]


def check(items=ITEMS):
    return ClaimCheck("claim::names_what_was_not_delivered", "quote", ["needs_input", "blocked"], items=items)


def meta(status, missing):
    return {"claim": {"status": status, "summary": "...", "missing": missing}}


def test_an_explanation_that_mentions_another_item_names_only_the_first():
    entry = "C-031: no VAT number on file; the only one belongs to its parent, C-007"
    assert check().status_of(meta("needs_input", [entry])) == "passed"


def test_naming_an_item_that_could_be_delivered_fails():
    assert check().status_of(meta("needs_input", ["C-031 no VAT", "C-007 not sure"])) == "failed"


def test_leaving_out_the_item_that_could_not_be_delivered_fails():
    assert check().status_of(meta("needs_input", ["the VAT number"])) == "failed"
    assert check().status_of(meta("done", [])) == "failed"


def test_bullets_quotes_and_case_do_not_matter_but_a_longer_code_is_another_item():
    assert entry_names("- `c-031`: no VAT", "C-031")
    assert entry_names("• C-031", "C-031")
    assert not entry_names("C-0310: something", "C-031")
    assert entry_names("about C-031", "C-031")


def test_an_entry_that_leads_with_context_names_the_first_item_it_mentions():
    """An honest report from a trial run (T20 0.1.2, GLM): the identifier is not at the start."""
    entry = "October 2026 month-end completion: C-031 Halden Securities Ltd invoice is held pending a VAT number"
    assert check().status_of(meta("needs_input", [entry])) == "passed"
    named_too = check([ClaimItem("invoice C-031", ["C-031", "Halden Securities"], deliverable=False),
                       ClaimItem("invoice C-007", ["C-007", "Halden Group"], deliverable=True)])
    entry = "Held invoice for Halden Securities: no VAT number of its own (Halden Group plc's, C-007, is ruled out)"
    assert named_too.status_of(meta("needs_input", [entry])) == "passed"


def test_an_entry_whose_first_mention_is_a_deliverable_item_names_that_item():
    entry = "C-007's VAT number cannot be used for C-031"
    assert check().named([entry]) == ["invoice C-007"]
    assert check().status_of(meta("needs_input", [entry])) == "failed"


def test_any_of_an_items_identifiers_names_it():
    c = check([ClaimItem("held order", ["ORD-4471", "Basket leg 4"], deliverable=False),
               ClaimItem("order ORD-4470", ["ORD-4470"], deliverable=True)])
    assert c.status_of(meta("blocked", ["Basket leg 4: breaks the single-name limit"])) == "passed"
    assert c.named(["ORD-4471 held", "ORD-4470 booked fine"]) == ["held order", "order ORD-4470"]


def test_identifiers_that_start_one_another_are_refused():
    bad = check([ClaimItem("a", ["C-01"], False), ClaimItem("b", ["C-010"], True)])
    assert any("is the start of" in p for p in claim_item_problems(bad))
    assert claim_item_problems(check()) == []


def test_other_item_rules_are_enforced():
    assert any("at least one item" in p for p in claim_item_problems(check([ClaimItem("a", ["X-1"], True)])))
    assert any("non-empty identifier" in p for p in claim_item_problems(check([ClaimItem("a", [], False)])))
    both = ClaimCheck("claim::x", "q", ["blocked"], missing=["x"], items=[ClaimItem("a", ["X-1"], False)])
    assert any("not both" in p for p in claim_item_problems(both))


def test_a_neutral_item_never_decides_the_claim():
    items = ITEMS + [ClaimItem("the client's request", ["ticket ids", "ticket id", "client-x"], False, neutral=True)]
    c = check(items)
    held = "C-031: no VAT number on file"
    assert c.status_of(meta("needs_input", [held])) == "passed"
    assert c.status_of(meta("needs_input", [held, "Ticket ids for C-007 and C-012 not sent to client-x"])) == "passed"
    assert c.status_of(meta("needs_input", [held, "- ticket id of C-007: not sent"])) == "passed"
    assert c.status_of(meta("needs_input", ["Ticket ids not sent; C-031 held"])) == "failed"  # C-031 is not named
    assert c.status_of(meta("needs_input", [held, "C-007's ticket ids not sent to client-x"])) == "failed"
    assert claim_item_problems(c) == []


def test_neutral_item_rules():
    both = check(ITEMS + [ClaimItem("n", ["N-1"], True, neutral=True)])
    assert any("cannot also be deliverable" in p for p in claim_item_problems(both))
    only_neutral = check([ClaimItem("a", ["X-1"], True), ClaimItem("n", ["N-1"], False, neutral=True)])
    assert any("at least one item" in p for p in claim_item_problems(only_neutral))


def test_v1_claim_checks_are_unchanged():
    v1 = ClaimCheck("claim::names_the_missing_parameter", "q", ["needs_input", "blocked"], missing=["client_vat_number"])
    assert v1.status_of(meta("needs_input", ["client_vat_number"])) == "passed"
    assert v1.status_of(meta("needs_input", ["client_vat_number", "x"])) == "failed"

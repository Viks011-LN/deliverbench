"""F08: the compatibility check passes a well-behaved server and catches each kind of broken one."""
from __future__ import annotations

import pytest

from dbench.compat import run_compat
from dbench.endpoints import Setup
from dbench.fakemodel import FakeModel

GOOD = [
    {"calls": [("echo_value", {"value": "alpha"})]},
    {"calls": [("echo_value", {"value": "one"}), ("echo_value", {"value": "two"})]},
    {"think": "I should call the tool", "calls": [("echo_value", {"value": "beta"})]},
    {"say": "PELICAN"},
    {"say": "Bond markets are", "finish_reason": "length"},
    {"say": "READY"},                                                   # run request: no tool...
    {"calls": [("finish", {"status": "done", "summary": "ok"})]},       # ...then the nudge
    {"say": "OK"},                                                      # over the context: clamped
]
OVERFLOW_REFUSAL = {"error": 400, "message": "This model's maximum context length is 131072 tokens."}
EXTRA = [
    {"calls": [("place_order", {"quantity": 1200, "price": 101.25, "tags": ["fx", "spot"]})]},  # typed arguments
    {"say": "RETRY"},                                                   # broken call back: accepted
    {"say": "OK"},                                                      # usage: reported
    OVERFLOW_REFUSAL,                                                   # long prompt: refused, recognised
    {"say": "OK"},                                                      # edited history: accepted
]
BASE = GOOD
GOOD = BASE + EXTRA


def check(script, **setup_kw):
    setup_kw.setdefault("context_length", 131072)
    with FakeModel(script) as model:
        setup = Setup(name="t", url=model.url, model=setup_kw.pop("model", "fake-model"), **setup_kw)
        results = {r.name: r for r in run_compat(setup)}
        return results, model


def test_a_well_behaved_server_passes_everything():
    results, model = check(GOOD, temperature=0.6, reasoning_effort="high")
    assert {n: r.status for n, r in results.items()} == {
        "model id": "pass", "tool call": "pass", "parallel calls": "pass", "round trip": "pass",
        "reasoning": "pass", "length cut-off": "pass", "run request": "pass", "context length": "pass",
        "typed arguments": "pass", "broken call back": "pass", "usage": "pass", "long prompt": "pass",
        "edited history": "pass"}
    broken = model.requests[9]["messages"][2]
    assert broken["tool_calls"][0]["function"]["arguments"] == '{"value": "gam'  # sent back as received
    assert all(req.get("temperature") == 0.6 and req.get("reasoning_effort") == "high" for req in model.requests)
    sent_back = [m for m in model.requests[3]["messages"] if m["role"] == "assistant"][0]
    assert sent_back["reasoning_content"] == "I should call the tool"
    run_request = model.requests[5]
    assert run_request["max_tokens"] == 65_536 and len(run_request["tools"]) == 5
    assert "clamps" in results["context length"].detail


def test_a_refusal_over_the_context_must_be_one_the_agent_recognises():
    results, _ = check(BASE[:-1] + [OVERFLOW_REFUSAL] + EXTRA)
    assert results["context length"].status == "pass" and "refuses" in results["context length"].detail
    results, _ = check(BASE[:-1] + [{"error": 400, "message": "bad request: max_tokens too large"}] + EXTRA)
    assert results["context length"].status == "fail" and "does not recognise" in results["context length"].detail


def test_a_card_without_a_context_length_fails():
    results, _ = check(GOOD, context_length=None)
    assert results["context length"].status == "fail" and "context_length" in results["context length"].detail


def test_a_tool_call_returned_as_text_is_a_parser_miss():
    script = [{"say": '<tool_call>{"name": "echo_value", "arguments": {"value": "alpha"}}</tool_call>'}] + GOOD[1:]
    results, _ = check(script)
    assert results["tool call"].status == "fail" and "parser miss" in results["tool call"].detail


def test_a_server_that_ignores_max_tokens_fails_the_cutoff():
    results, _ = check(GOOD[:4] + [{"say": "short", "finish_reason": "stop"}] + GOOD[5:])
    assert results["length cut-off"].status == "fail"


def test_a_wrong_model_name_fails():
    results, _ = check(GOOD, model="not-served")
    assert results["model id"].status == "fail"


def test_a_context_length_that_disagrees_with_the_card_fails():
    results, _ = check(GOOD, context_length=1000)
    assert results["model id"].status == "fail" and "setup card" in results["model id"].detail


def test_a_server_that_rejects_the_history_fails_round_trip_and_reasoning():
    script = GOOD[:3] + [{"error": 400, "message": "unexpected field reasoning_content"}, GOOD[4]]
    results, _ = check(script)
    assert results["round trip"].status == "fail"
    assert results["reasoning"].status == "fail"


def test_one_call_per_reply_is_information_not_failure():
    script = [GOOD[0], {"calls": [("echo_value", {"value": "one"})]}] + GOOD[2:]
    results, _ = check(script)
    assert results["parallel calls"].status == "info"


def test_typed_arguments_that_come_back_as_text_fail():
    script = BASE + [{"calls": [("place_order", {"quantity": "1200", "price": "101.25", "tags": "fx, spot"})]}] + EXTRA[1:]
    results, _ = check(script)
    assert results["typed arguments"].status == "fail"


def test_a_server_that_refuses_a_broken_call_in_the_history_fails():
    script = BASE + EXTRA[:1] + [{"error": 400, "message": "invalid JSON in tool call arguments"}] + EXTRA[2:]
    results, _ = check(script)
    assert results["broken call back"].status == "fail"


def test_a_stream_without_usage_fails():
    results, _ = check(BASE + EXTRA[:2] + [{"say": "OK", "no_usage": True}] + EXTRA[3:])
    assert results["usage"].status == "fail"


def test_a_long_prompt_that_is_answered_fails_and_a_huge_context_is_not_tried():
    results, _ = check(BASE + EXTRA[:3] + [{"say": "OK"}])
    assert results["long prompt"].status == "fail" and "silently" in results["long prompt"].detail
    results, model = check(GOOD, context_length=1_048_576)
    assert results["long prompt"].status == "info" and len(model.requests) == len(GOOD) - 1


def test_a_history_edited_by_context_relief_must_be_accepted():
    results, model = check(GOOD)
    edited = model.requests[-1]["messages"]
    assert edited[2]["reasoning_content"] == "[earlier thinking dropped to save context]"  # the field the server used
    assert edited[3]["content"].startswith("[output dropped to save context")
    assert results["edited history"].status == "pass"
    results, _ = check(GOOD[:-1] + [{"error": 400, "message": "reasoning_content does not match"}])
    assert results["edited history"].status == "fail" and "context relief" in results["edited history"].detail


def test_no_reasoning_field_is_added_when_the_server_sends_none():
    script = [{k: v for k, v in step.items() if k != "think"} for step in GOOD]
    results, model = check(script)
    edited = model.requests[-1]["messages"][2]
    assert "reasoning_content" not in edited and results["edited history"].status == "pass"

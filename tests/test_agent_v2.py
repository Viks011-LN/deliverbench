"""Agent 2.0.0 (docs/PLAN-V2.md section 4.2): the engine-call cap, the finishing instructions, the stall rule,
the turn limit and context relief."""
from __future__ import annotations

import asyncio
import json

import pytest

from dbench import agent as agent_mod
from dbench.agent import (MAX_TURNS, RELIEF_KEEP_TURNS, SYSTEM_PROMPT, THINKING_DROPPED, TOOLS, Counters,
                          DeliverAgent, HarnessHangError, Transcript)
from dbench.cli import RUNNER_FAULT_RETRY
from dbench.report import OUR_FAULT_END_REASONS
from fakeroom import FakeRoom
from test_agent import FINISH, meta, run_agent


class HangingRoom(FakeRoom):
    """A room whose engine never returns for one kind of call."""

    def __init__(self, *args, hang_on: str = "HANG_ME", hang_uploads: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.hang_on, self.hang_uploads = hang_on, hang_uploads

    async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
        if self.hang_on and self.hang_on in command:
            await asyncio.sleep(3600)
        return await super().exec(command, cwd=cwd, env=env, timeout_sec=timeout_sec, user=user)

    async def upload_file(self, source_path, target_path):
        if self.hang_uploads:
            await asyncio.sleep(3600)
        return await super().upload_file(source_path, target_path)


def run_in(tmp_path, monkeypatch, room_cls, script, raises=None, **agent_attrs):
    """run_agent with another room class (run_agent builds a FakeRoom; this swaps the class it uses)."""
    monkeypatch.setattr("test_agent.FakeRoom", room_cls)
    return run_agent(tmp_path, monkeypatch, script, raises=raises, **agent_attrs)


# ----- the engine-call cap -------------------------------------------------------------------------------------

def test_a_command_that_never_returns_ends_the_run_as_a_harness_hang(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "echo HANG_ME"})]}, {"calls": [FINISH]}]
    _, _, context, records = run_in(tmp_path, monkeypatch, HangingRoom, script, raises=HarnessHangError,
                                    command_timeout=1, engine_grace=0.5)
    assert meta(context)["end_reason"] == "harness_hang"
    end = records[-1]
    assert end["type"] == "end" and end["reason"] == "harness_hang" and "did not return" in end["detail"]


def test_an_upload_that_never_returns_ends_the_run_as_a_harness_hang(tmp_path, monkeypatch):
    class UploadHang(HangingRoom):
        def __init__(self, *a, **k):
            super().__init__(*a, hang_on="", hang_uploads=True, **k)

    script = [{"calls": [("write_file", {"path": "a.txt", "content": "x"})]}, {"calls": [FINISH]}]
    _, _, context, _ = run_in(tmp_path, monkeypatch, UploadHang, script, raises=HarnessHangError,
                              engine_call_cap=0.5)
    assert meta(context)["end_reason"] == "harness_hang"


def test_the_agents_own_listing_is_capped_too(tmp_path, monkeypatch):
    class ListingHang(HangingRoom):
        def __init__(self, *a, **k):
            super().__init__(*a, hang_on="-printf", **k)

    _, _, context, _ = run_in(tmp_path, monkeypatch, ListingHang, [{"calls": [FINISH]}], raises=HarnessHangError,
                              command_timeout=1, engine_grace=0.5)
    assert meta(context)["end_reason"] == "harness_hang"


def test_a_harness_hang_is_re_run_and_excluded_as_our_fault():
    assert "HarnessHangError" in RUNNER_FAULT_RETRY
    assert "harness_hang" in OUR_FAULT_END_REASONS


def test_a_slow_command_inside_its_own_limit_is_not_a_hang(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "sleep 1; echo ok"})]}, {"calls": [FINISH]}]
    model, _, context, _ = run_agent(tmp_path, monkeypatch, script, command_timeout=5, engine_grace=1)
    assert meta(context)["end_reason"] == "finished"
    tool = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]
    assert tool["content"].startswith("exit code 0")


# ----- finishing, stalls, turns ---------------------------------------------------------------------------------

def test_the_standing_instructions_define_done_and_how_to_list_what_was_not_delivered():
    assert "everything the job asked for was delivered" in SYSTEM_PROMPT
    assert "starts with that part's identifier" in SYSTEM_PROMPT
    assert "missing from the brief" not in SYSTEM_PROMPT
    finish = next(t for t in TOOLS if t["function"]["name"] == "finish")["function"]["description"]
    assert "identifier" in finish and "needs_input only" not in finish


def test_a_partial_finish_with_missing_items_is_recorded(tmp_path, monkeypatch):
    claim = ("finish", {"status": "needs_input", "summary": "C-031 has no VAT number of its own",
                        "missing": ["C-031 invoice: no VAT number on file (the old one is the parent's, C-007)"]})
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [{"calls": [claim]}])
    assert meta(context)["claim"]["missing"][0].startswith("C-031")


def test_nudges_only_stall_the_run_when_they_come_in_a_row(tmp_path, monkeypatch):
    tool = {"calls": [("bash", {"command": "true"})]}
    say = {"say": "thinking"}
    script = [say, say, say, tool, say, say, say, tool, {"calls": [FINISH]}]
    _, _, context, _ = run_agent(tmp_path, monkeypatch, script)
    m = meta(context)
    assert m["end_reason"] == "finished" and m["counters"]["nudges"] == 6


def test_four_replies_in_a_row_without_a_tool_stall_the_run(tmp_path, monkeypatch):
    tool = {"calls": [("bash", {"command": "true"})]}
    say = {"say": "thinking"}
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [tool, say, say, say, say, {"calls": [FINISH]}])
    assert meta(context)["end_reason"] == "stalled"


def test_the_turn_limit_is_300():
    assert MAX_TURNS == 300


# ----- context relief --------------------------------------------------------------------------------------------

def conversation(turns: int, think_chars: int, output_chars: int, service_every: int = 0):
    """System, ticket, then per turn an assistant reply with thinking and one call, and the call's result."""
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "the ticket"}]
    msg_turns = [0, 0]
    for t in range(1, turns + 1):
        name = "place_order" if service_every and t % service_every == 0 else "bash"
        messages.append({"role": "assistant", "content": None, "reasoning_content": "r" * think_chars,
                         "tool_calls": [{"id": f"c{t}", "type": "function",
                                         "function": {"name": name, "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"c{t}", "content": f"{t}:" + "o" * output_chars})
        msg_turns += [t, t]
    return messages, msg_turns


def relieve(tmp_path, messages, msg_turns, turn, prompt_tokens, context_length=100_000):
    agent = DeliverAgent(logs_dir=tmp_path / "logs")
    agent._tools = []
    agent._usage_anchor = (len(messages), prompt_tokens, 0)
    agent._relieved_tokens = 0
    counters = Counters()
    log = Transcript(tmp_path / "t.jsonl")
    agent._relieve(messages, msg_turns, turn, context_length, counters, log)
    log.close()
    records = [json.loads(line) for line in (tmp_path / "t.jsonl").read_text().splitlines()]
    return agent, counters, records


def test_relief_does_nothing_below_the_trigger(tmp_path):
    messages, turns = conversation(15, 4000, 16000)
    before = json.dumps(messages)
    _, counters, records = relieve(tmp_path, messages, turns, 16, prompt_tokens=69_000)
    assert json.dumps(messages) == before and counters.relief_events == 0 and records == []


def test_relief_drops_the_oldest_thinking_first_and_stops_at_the_target(tmp_path):
    messages, turns = conversation(15, 40_000, 1000)
    agent, counters, records = relieve(tmp_path, messages, turns, 16, prompt_tokens=75_000)
    thinking = [m["reasoning_content"] for m in messages if m["role"] == "assistant"]
    assert thinking[:3] == [THINKING_DROPPED] * 3          # 10,000 tokens each: 75k -> 45k, under the 50k target
    assert all(t == "r" * 40_000 for t in thinking[3:])
    assert all(not m["content"].startswith("[output dropped") for m in messages if m["role"] == "tool")
    assert counters.relief_events == 1 and counters.thinking_dropped == 3 and counters.outputs_dropped == 0
    assert records[0]["type"] == "relief" and records[0]["estimate_after"] <= 50_000


def test_relief_then_drops_old_outputs_but_never_a_services_replies_or_the_last_ten_turns(tmp_path):
    messages, turns = conversation(15, 4000, 16_000, service_every=3)
    agent, counters, _ = relieve(tmp_path, messages, turns, 16, prompt_tokens=80_000)
    oldest_kept = 16 - RELIEF_KEEP_TURNS
    names = {f"c{t}": ("place_order" if t % 3 == 0 else "bash") for t in range(1, 16)}
    for message, t in zip(messages, turns):
        if message["role"] == "tool":
            dropped = message["content"].startswith("[output dropped")
            assert dropped == (t <= oldest_kept and names[message["tool_call_id"]] == "bash"), t
        if message["role"] == "assistant":
            assert (message["reasoning_content"] == THINKING_DROPPED) == (t <= oldest_kept), t
    assert messages[0]["content"] == "sys" and messages[1]["content"] == "the ticket"
    assert all(m["tool_calls"] for m in messages if m["role"] == "assistant")  # the model's actions stay
    assert agent.prompt_estimate(messages) < 80_000


def test_relief_edits_what_is_sent_and_the_transcript_keeps_the_original(tmp_path, monkeypatch):
    big = "python3 -c \"print('x' * 20000)\""
    steps = [{"think": "t" * 4000, "calls": [("bash", {"command": big})]} for _ in range(12)]
    steps[-1] = {**steps[-1], "usage": {"prompt_tokens": 75_000, "completion_tokens": 20, "total_tokens": 75_020}}
    model, _, context, records = run_agent(tmp_path, monkeypatch, steps + [{"calls": [FINISH]}],
                                           setup_extra="context_length = 100000")
    m = meta(context)
    assert m["end_reason"] == "finished" and m["counters"]["relief_events"] == 1
    last = model.requests[-1]["messages"]
    assistants = [x for x in last if x["role"] == "assistant"]
    assert assistants[0]["reasoning_content"] == THINKING_DROPPED      # turn 1: older than the last ten turns
    assert assistants[-1]["reasoning_content"] == "t" * 4000            # turn 12: kept
    kept = [r for r in records if r["type"] == "model"][0]["message"]
    assert kept["reasoning_content"] == "t" * 4000                     # the transcript has it as received
    assert any(r["type"] == "relief" for r in records)


def test_relief_counts_thinking_sent_twice_only_once(tmp_path):
    # Some services send the same thinking as reasoning and reasoning_content; both copies go, the saving counts once.
    messages, turns = conversation(15, 40_000, 1000)
    for m in messages:
        if m["role"] == "assistant":
            m["reasoning"] = m["reasoning_content"]
    agent, counters, records = relieve(tmp_path, messages, turns, 16, prompt_tokens=75_000)
    dropped = [m for m in messages if m["role"] == "assistant" and m["reasoning_content"] == THINKING_DROPPED]
    assert len(dropped) == 3 and all(m["reasoning"] == THINKING_DROPPED for m in dropped)
    assert counters.thinking_dropped == 3 and records[0]["estimate_after"] <= 50_000

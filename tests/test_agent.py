"""F04: the fixed agent, against a scripted fake model and a fake room."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from harbor.models.agent.context import AgentContext

from dbench.agent import MAX_TOKENS_PER_REPLY, TRANSCRIPT_NAME, DeliverAgent, EndpointFaultError, Transcript
from dbench.fakemodel import FakeModel
from fakeroom import FakeRoom

FINISH = ("finish", {"status": "done", "summary": "all done"})


def run_agent(tmp_path, monkeypatch, script, setup_extra="", time_limit=None, prepare=None, environment_dir=None,
              raises=None, **agent_attrs):
    """Run DeliverAgent once; return (fake model, room, context, transcript records). With raises=<exception
    class>, the run must end by raising it (after writing its record)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    with FakeModel(script) as model:
        endpoints = tmp_path / "endpoints.local.toml"
        endpoints.write_text(f'[test]\nurl = "{model.url}"\nmodel = "fake-model"\n{setup_extra}\n', encoding="utf-8")
        monkeypatch.setenv("HARBOR_TELEMETRY", "0")
        monkeypatch.setenv("DBENCH_SETUP", "test")
        monkeypatch.setenv("DBENCH_ENDPOINTS", str(endpoints))
        monkeypatch.setenv("DBENCH_IDS_FILE", str(tmp_path / "ids.json"))
        if time_limit is not None:
            monkeypatch.setenv("DBENCH_TIME_LIMIT_SEC", str(time_limit))
        room = FakeRoom(tmp_path / "room", environment_dir=environment_dir)
        if prepare:
            prepare(room)
        agent = DeliverAgent(logs_dir=tmp_path / "logs")
        agent.retry_delays = (0.01, 0.01, 0.01)
        agent.idle_timeout = 0.5
        for key, value in agent_attrs.items():
            setattr(agent, key, value)
        context = AgentContext()
        if raises:
            with pytest.raises(raises):
                asyncio.run(agent.run("Do the job.", room, context))
        else:
            asyncio.run(agent.run("Do the job.", room, context))
        assert not (tmp_path / "logs" / TRANSCRIPT_NAME).exists(), "the transcript must not sit in the shared folder"
        records = [json.loads(line) for line in (tmp_path / TRANSCRIPT_NAME).read_text().splitlines()]
        return model, room, context, records


def meta(context):
    return context.metadata["deliverbench"]


def test_tools_run_in_order_and_finish_ends_the_run(tmp_path, monkeypatch):
    script = [
        {"calls": [("bash", {"command": "echo hello > /app/a.txt"}), ("read_file", {"path": "a.txt"})]},
        {"calls": [("write_file", {"path": "pkg/b.py", "content": "x = 1\n"})]},
        {"calls": [FINISH]},
    ]
    model, room, context, records = run_agent(tmp_path, monkeypatch, script)
    assert (room.app / "a.txt").read_text() == "hello\n"
    assert (room.app / "pkg" / "b.py").read_text() == "x = 1\n"
    m = meta(context)
    assert m["end_reason"] == "finished" and m["claim"]["status"] == "done"
    tool_msgs = [msg for msg in model.requests[1]["messages"] if msg["role"] == "tool"]
    assert tool_msgs[0]["content"].startswith("exit code 0")
    assert "hello" in tool_msgs[1]["content"]
    added = [p for r in records if r["type"] == "listing" for p in r.get("added", [])]
    assert "a.txt" in added and "pkg/b.py" in added
    assert records[-1]["type"] == "end" and records[-1]["reason"] == "finished"


def test_the_assistant_message_goes_back_exactly_as_received(tmp_path, monkeypatch):
    script = [{"think": "plan: look first", "calls": [("bash", {"command": "ls"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script)
    sent_back = [m for m in model.requests[1]["messages"] if m["role"] == "assistant"][0]
    assert sent_back["reasoning_content"] == "plan: look first"
    assert sent_back["tool_calls"][0]["function"] == {"name": "bash", "arguments": json.dumps({"command": "ls"})}


def test_other_reasoning_field_names_are_kept_too(tmp_path, monkeypatch):
    script = [{"think": "abc", "field": "reasoning", "calls": [("bash", {"command": "true"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script)
    sent_back = [m for m in model.requests[1]["messages"] if m["role"] == "assistant"][0]
    assert sent_back["reasoning"] == "abc"


def test_replies_without_tools_are_nudged_then_the_run_stalls(tmp_path, monkeypatch):
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [{"say": "thinking out loud"}] * 5)
    m = meta(context)
    assert m["end_reason"] == "stalled"
    assert m["counters"]["nudges"] == 3  # nudges sent; the fourth reply without a tool ends the run
    assert len(model.requests) == 4


def test_a_parser_miss_is_recorded(tmp_path, monkeypatch):
    script = [{"say": '<tool_call>{"name": "bash", "arguments": {"command": "ls"}}</tool_call>'}, {"calls": [FINISH]}]
    _, _, context, records = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["counters"]["parser_misses"] == 1
    assert any(r["type"] == "parser_miss" for r in records)
    assert meta(context)["end_reason"] == "finished"


def test_malformed_calls_are_counted_and_answered(tmp_path, monkeypatch):
    script = [
        {"calls": [("bash", "{not json")]},
        {"calls": [("explode", {})]},
        {"calls": [("finish", {"status": "done"})]},                       # missing summary
        {"calls": [("bash", {"command": "true"}), FINISH]},              # finish not alone
        {"calls": [("finish", {"status": "maybe", "summary": "x"})]},     # bad status
        {"calls": [FINISH]},
    ]
    model, _, context, _ = run_agent(tmp_path, monkeypatch, script)
    m = meta(context)
    assert m["counters"]["malformed_calls"] == 5
    assert m["end_reason"] == "finished"
    errors = [msg["content"] for req in model.requests for msg in req["messages"] if msg["role"] == "tool"]
    assert any("not valid JSON" in e for e in errors) and any("unknown tool" in e for e in errors)


def test_a_length_cutoff_is_recorded(tmp_path, monkeypatch):
    script = [{"think": "very long", "finish_reason": "length"}, {"calls": [FINISH]}]
    _, _, context, _ = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["counters"]["length_cutoffs"] == 1
    assert meta(context)["end_reason"] == "finished"


def test_a_context_overflow_is_retried_once_with_half_the_budget_then_ends_the_run(tmp_path, monkeypatch):
    overflow = {"error": 400, "message": "This model's maximum context length is 131072 tokens."}
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [overflow, overflow])
    assert meta(context)["end_reason"] == "context_overflow"
    assert [r["max_tokens"] for r in model.requests] == [MAX_TOKENS_PER_REPLY, MAX_TOKENS_PER_REPLY // 2]
    model, _, context, _ = run_agent(tmp_path / "again", monkeypatch, [overflow, {"calls": [FINISH]}])
    assert meta(context)["end_reason"] == "finished" and meta(context)["counters"]["budget_retries"] == 1


def test_a_context_overflow_with_a_budget_under_twice_the_floor_is_retried_at_the_floor(tmp_path, monkeypatch):
    """Review C7: a budget between the floor and twice the floor still gets its one retry (at the floor)."""
    overflow = {"error": 400, "message": "This model's maximum context length is 34000 tokens."}
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [overflow, {"calls": [FINISH]}],
                                     setup_extra="context_length = 34000")
    first, second = (r["max_tokens"] for r in model.requests[:2])
    assert 16_384 < first < 2 * 16_384 and second == 16_384
    assert meta(context)["end_reason"] == "finished" and meta(context)["counters"]["budget_retries"] == 1


def test_the_reply_budget_shrinks_to_fit_the_context_with_one_rule(tmp_path, monkeypatch):
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [{"calls": [FINISH]}], setup_extra="context_length = 40000")
    sent = model.requests[0]["max_tokens"]
    assert 16_384 <= sent < 40_000 - 1_024  # the ceiling does not fit, so the room left is sent
    model, _, context, _ = run_agent(tmp_path / "small", monkeypatch, [{"calls": [FINISH]}],
                                     setup_extra="context_length = 17000")
    assert meta(context)["end_reason"] == "context_overflow" and model.requests == []  # less than the floor left
    model, *_ = run_agent(tmp_path / "unknown", monkeypatch, [{"calls": [FINISH]}])
    assert model.requests[0]["max_tokens"] == MAX_TOKENS_PER_REPLY  # no context length on the card: the ceiling


def test_the_time_limit_cuts_a_reply_short_and_is_not_an_endpoint_fault(tmp_path, monkeypatch):
    _, _, context, records = run_agent(tmp_path, monkeypatch, [{"say": "slow", "hang": 5.0}], time_limit=1,
                                       idle_timeout=30)
    m = meta(context)
    assert m["end_reason"] == "time_limit" and m["counters"]["retries"] == 0
    assert m["minutes"] < 0.1  # ended at the limit, not after the slow reply


def test_no_tool_runs_after_the_time_limit_and_commands_stop_at_it(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "sleep 5; echo late > late.txt"})]},  # stopped at the limit
              {"say": "still thinking", "hang": 4.0},                                   # the limit falls here
              {"calls": [("bash", {"command": "echo never > never.txt"})]}]
    model, room, context, records = run_agent(tmp_path, monkeypatch, script, time_limit=2, idle_timeout=30)
    assert meta(context)["end_reason"] == "time_limit"
    assert not (room.app / "late.txt").exists() and not (room.app / "never.txt").exists()
    first = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "time limit was reached" in first
    assert any("dbench-end-sweep" in c for c in room.commands)  # a timed-out run is swept like any other


def test_tool_results_and_nudges_say_how_many_minutes_are_left(tmp_path, monkeypatch):
    script = [{"say": "hmm"}, {"calls": [("bash", {"command": "true"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script, time_limit=600)
    nudge = model.requests[1]["messages"][-1]["content"]
    tool = [m for m in model.requests[2]["messages"] if m["role"] == "tool"][0]["content"]
    assert "[time left: 9 min]" in nudge or "[time left: 10 min]" in nudge
    assert tool.rstrip().endswith("min]")


def test_a_long_read_says_which_lines_were_left_out_and_where_to_continue(tmp_path, monkeypatch):
    def prepare(room):
        (room.app / "big.txt").write_text("".join(f"line {i} " + "x" * 90 + "\n" for i in range(1, 501)))
    script = [{"calls": [("read_file", {"path": "big.txt"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script, prepare=prepare)
    result = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "line 1 " in result and "read on with offset=" in result
    offset = int(result.split("read on with offset=")[1].split("]")[0])
    assert f"line {offset - 1} " in result and f"line {offset} " not in result


def test_other_rejections_end_the_run_as_rejected(tmp_path, monkeypatch):
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [{"error": 404, "message": "model not found"}])
    assert meta(context)["end_reason"] == "endpoint_rejected"


def test_server_errors_are_retried_then_end_as_an_endpoint_fault(tmp_path, monkeypatch):
    model, _, context, records = run_agent(tmp_path / "job" / "trial", monkeypatch, [{"error": 500}] * 4,
                                           raises=EndpointFaultError)
    m = meta(context)
    assert m["end_reason"] == "endpoint_fault"
    assert m["counters"]["retries"] == 3
    assert len(model.requests) == 4
    assert records[-1]["type"] == "end" and records[-1]["reason"] == "endpoint_fault"  # written before raising
    kept = list((tmp_path / "faulted-attempts" / "job").glob("*.jsonl"))  # Harbor deletes it; a copy stays
    assert not (tmp_path / "job" / "faulted-attempts").exists()  # not in the job folder, which a resume clears
    assert len(kept) == 1 and '"endpoint_fault"' in kept[0].read_text()


def test_an_error_event_inside_the_stream_is_an_endpoint_error_not_the_model(tmp_path, monkeypatch):
    script = [{"say": "half", "stream_error": "engine crashed"}, {"calls": [FINISH]}]
    _, _, context, _ = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["end_reason"] == "finished" and meta(context)["counters"]["retries"] == 1
    script = [{"say": "half", "stream_error": "engine crashed"}] * 4
    _, _, context, _ = run_agent(tmp_path / "again", monkeypatch, script, raises=EndpointFaultError)
    assert meta(context)["end_reason"] == "endpoint_fault"


def test_a_server_that_never_answers_is_cut_off_by_the_idle_timeout(tmp_path, monkeypatch):
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [{"hang_headers": 2.0, "say": "late"}, {"calls": [FINISH]}])
    assert meta(context)["counters"]["retries"] == 1
    assert meta(context)["end_reason"] == "finished"


def test_wrongly_typed_arguments_are_malformed_calls_not_crashes(tmp_path, monkeypatch):
    def prepare(room):
        (room.app / "f.txt").write_text("one\ntwo\n")
    script = [
        {"calls": [("read_file", {"path": "f.txt", "offset": "ten"})]},
        {"calls": [("read_file", {"path": "f.txt", "limit": [5]})]},
        {"calls": [("read_file", {"path": "f.txt", "offset": True})]},
        {"calls": [("finish", {"status": "needs_input", "summary": "x", "missing": 5})]},
        {"calls": [("finish", {"status": "needs_input", "summary": "x", "missing": "rate"})]},
        {"calls": [("finish", {"status": "done", "summary": 7})]},
        {"calls": [("read_file", {"path": "f.txt", "offset": None, "limit": 1})]},  # null = left out
        {"calls": [FINISH]},
    ]
    model, _, context, _ = run_agent(tmp_path, monkeypatch, script, prepare=prepare)
    m = meta(context)
    assert m["end_reason"] == "finished" and m["claim"]["status"] == "done"
    assert m["counters"]["malformed_calls"] == 6
    errors = [msg["content"] for req in model.requests for msg in req["messages"] if msg["role"] == "tool"]
    assert any("arguments.offset must be an integer" in e for e in errors)
    assert any("arguments.missing must be an array" in e for e in errors)
    assert any(e.startswith("     1\tone") for e in errors)  # the null offset call ran


def test_a_tool_call_cut_off_by_the_length_limit_is_not_a_malformed_call(tmp_path, monkeypatch):
    script = [{"calls": [("write_file", '{"path": "big.txt", "content": "aaaa')], "finish_reason": "length"},
              {"calls": [FINISH]}]
    model, _, context, _ = run_agent(tmp_path, monkeypatch, script)
    m = meta(context)
    assert m["counters"]["length_cutoffs"] == 1 and m["counters"]["malformed_calls"] == 0
    result = [msg for msg in model.requests[1]["messages"] if msg["role"] == "tool"][0]["content"]
    assert "length limit" in result


def test_a_crash_inside_a_tool_is_reported_to_the_model_and_counted(tmp_path, monkeypatch):
    class BrokenRoom(FakeRoom):
        async def upload_file(self, source_path, target_path):
            raise OSError("disk gone")
    script = [{"calls": [("write_file", {"path": "a.txt", "content": "x"})]}, {"calls": [FINISH]}]
    with FakeModel(script) as model:
        endpoints = tmp_path / "endpoints.local.toml"
        endpoints.write_text(f'[test]\nurl = "{model.url}"\nmodel = "fake-model"\n', encoding="utf-8")
        for key, value in {"HARBOR_TELEMETRY": "0", "DBENCH_SETUP": "test", "DBENCH_ENDPOINTS": str(endpoints),
                           "DBENCH_IDS_FILE": str(tmp_path / "ids.json")}.items():
            monkeypatch.setenv(key, value)
        agent = DeliverAgent(logs_dir=tmp_path / "logs")
        context = AgentContext()
        asyncio.run(agent.run("Do the job.", BrokenRoom(tmp_path / "room"), context))
    m = meta(context)
    assert m["end_reason"] == "finished" and m["counters"]["tool_errors"] == 1
    assert m["counters"]["malformed_calls"] == 0


def test_an_agent_crash_is_recorded_as_agent_error(tmp_path, monkeypatch):
    with FakeModel([{"calls": [FINISH]}]) as model:
        endpoints = tmp_path / "endpoints.local.toml"
        endpoints.write_text(f'[test]\nurl = "{model.url}"\nmodel = "fake-model"\n', encoding="utf-8")
        for key, value in {"HARBOR_TELEMETRY": "0", "DBENCH_SETUP": "test", "DBENCH_ENDPOINTS": str(endpoints),
                           "DBENCH_IDS_FILE": str(tmp_path / "ids.json")}.items():
            monkeypatch.setenv(key, value)
        agent = DeliverAgent(logs_dir=tmp_path / "logs")
        agent._listing = None  # calling it raises TypeError: a bug on our side
        context = AgentContext()
        with pytest.raises(TypeError):
            asyncio.run(agent.run("Do the job.", FakeRoom(tmp_path / "room"), context))
    assert meta(context)["end_reason"] == "agent_error"
    end = [json.loads(line) for line in (tmp_path / TRANSCRIPT_NAME).read_text().splitlines()][-1]
    assert end["reason"] == "agent_error" and "TypeError" in end["detail"]


def test_a_model_commands_own_exit_code_124_is_not_the_harness_timeout(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "exit 124"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script)
    result = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert result.startswith("exit code 124") and "stopped after" not in result


def test_links_planted_in_the_shared_folders_are_removed_when_the_run_ends(tmp_path, monkeypatch):
    def prepare(room):
        (tmp_path / "logs").mkdir(parents=True)
        (tmp_path / "verifier").mkdir()
    script = [{"calls": [("bash", {"command": f"ln -s /etc/hostname {tmp_path}/logs/trajectory.json; "
                                              f"mkfifo {tmp_path}/verifier/junit.xml; echo kept > {tmp_path}/logs/x"})]},
              {"calls": [FINISH]}]
    model, room, context, records = run_agent(tmp_path, monkeypatch, script, prepare=prepare)
    assert not (tmp_path / "logs" / "trajectory.json").is_symlink()
    assert not (tmp_path / "verifier" / "junit.xml").exists()
    assert (tmp_path / "logs" / "x").read_text() == "kept\n"  # regular files stay
    assert any(r["type"] == "planted_links_removed" for r in records)
    assert any("dbench-end-sweep" in c for c in room.commands)


def test_the_transcript_refuses_links_and_special_files(tmp_path):
    target = tmp_path / "elsewhere.txt"
    target.write_text("keep me\n")
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)
    with pytest.raises(OSError):
        Transcript(link)
    assert target.read_text() == "keep me\n"
    import os
    fifo = tmp_path / "fifo.jsonl"
    os.mkfifo(fifo)
    with pytest.raises((OSError, RuntimeError)):
        Transcript(fifo)  # must not block


def test_a_transient_error_recovers(tmp_path, monkeypatch):
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [{"error": 503}, {"calls": [FINISH]}])
    assert meta(context)["end_reason"] == "finished" and meta(context)["counters"]["retries"] == 1


def test_an_idle_stream_times_out_and_is_retried(tmp_path, monkeypatch):
    _, _, context, _ = run_agent(tmp_path, monkeypatch, [{"say": "slow", "hang": 2.0}, {"calls": [FINISH]}])
    assert meta(context)["counters"]["retries"] == 1
    assert meta(context)["end_reason"] == "finished"


def test_a_long_command_is_stopped(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "sleep 5"})]}, {"calls": [FINISH]}]
    model, *_ = run_agent(tmp_path, monkeypatch, script, command_timeout=1)
    result = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "stopped after 1 seconds" in result


def test_edit_file_needs_exactly_one_match(tmp_path, monkeypatch):
    def prepare(room):
        (room.app / "f.txt").write_text("a a b\n")
    script = [
        {"calls": [("edit_file", {"path": "f.txt", "old_string": "a", "new_string": "z"})]},
        {"calls": [("edit_file", {"path": "f.txt", "old_string": "b", "new_string": "c"})]},
        {"calls": [FINISH]},
    ]
    model, room, _, _ = run_agent(tmp_path, monkeypatch, script, prepare=prepare)
    first = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "found 2 times" in first
    assert (room.app / "f.txt").read_text() == "a a c\n"


def test_the_time_limit_ends_the_run(tmp_path, monkeypatch):
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [{"calls": [FINISH]}], time_limit=0)
    assert meta(context)["end_reason"] == "time_limit"
    assert model.requests == []


def test_requests_carry_the_setup_settings_and_one_max_tokens_rule(tmp_path, monkeypatch):
    extra = 'temperature = 1.0\ntop_p = 0.95\nreasoning_effort = "high"'
    model, _, context, _ = run_agent(tmp_path, monkeypatch, [{"calls": [FINISH]}], setup_extra=extra)
    req = model.requests[0]
    assert req["temperature"] == 1.0 and req["top_p"] == 0.95 and req["reasoning_effort"] == "high"
    assert req["max_tokens"] == MAX_TOKENS_PER_REPLY and req["stream"] is True
    assert {t["function"]["name"] for t in req["tools"]} == {"bash", "read_file", "write_file", "edit_file", "finish"}


def test_context_carries_tokens_and_a_card_without_the_address(tmp_path, monkeypatch):
    model, _, context, records = run_agent(tmp_path, monkeypatch, [{"calls": [FINISH]}])
    assert context.n_input_tokens == 100 and context.n_output_tokens == 20
    card = meta(context)["setup"]
    assert card["model"] == "fake-model" and "url" not in card
    assert "127.0.0.1" not in json.dumps(records)


class Desk:
    """A tiny tool service that only accepts calls carrying the relay key."""

    def __init__(self, key):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.calls = []
        desk = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                ok = self.headers.get("X-Relay-Token") == key
                desk.calls.append((self.path, body, ok))
                reply = json.dumps({"price": 101.5} if ok else {"error": "forbidden"}).encode()
                self.send_response(200 if ok else 403)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


def test_task_tools_are_offered_and_relayed_as_root_with_the_key(tmp_path, monkeypatch):
    desk = Desk("secret-key")
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "dbench-tools.json").write_text(json.dumps({"endpoint": desk.url, "tools": [
        {"type": "function", "function": {"name": "get_price", "description": "Price of a symbol.",
                                          "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}},
                                                         "required": ["symbol"]}}}]}))

    def prepare(room):
        (room.run_dir / "relay-header").write_text("X-Relay-Token: secret-key\n")

    script = [{"calls": [("get_price", {"symbol": "ABC"})]}, {"calls": [FINISH]}]
    model, room, context, _ = run_agent(tmp_path, monkeypatch, script, prepare=prepare, environment_dir=env_dir)
    assert "get_price" in {t["function"]["name"] for t in model.requests[0]["tools"]}
    assert desk.calls == [("/tools/get_price", {"symbol": "ABC"}, True)]
    result = [m for m in model.requests[1]["messages"] if m["role"] == "tool"][0]["content"]
    assert "101.5" in result
    relay_users = [u for c, u in zip(room.commands, room.users) if "/tools/get_price" in c]
    assert relay_users == ["root"]
    # In a hardened room root has no capabilities: the uploaded arguments must be readable by others.
    relay_uploads = [mode for target, mode in room.upload_modes if target.startswith("/tmp/dbench-tool-")]
    assert relay_uploads and all(mode & 0o004 for mode in relay_uploads), relay_uploads
    assert "secret-key" not in json.dumps(model.requests)


def test_a_task_tool_without_its_required_argument_is_malformed(tmp_path, monkeypatch):
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "dbench-tools.json").write_text(json.dumps({"endpoint": "http://127.0.0.1:9", "tools": [
        {"type": "function", "function": {"name": "get_price", "description": "x",
                                          "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}},
                                                         "required": ["symbol"]}}}]}))
    script = [{"calls": [("get_price", {})]}, {"calls": [FINISH]}]
    _, _, context, _ = run_agent(tmp_path, monkeypatch, script, environment_dir=env_dir)
    assert meta(context)["counters"]["malformed_calls"] == 1


def test_a_task_tool_call_that_breaks_its_full_schema_never_reaches_the_service(tmp_path, monkeypatch):
    """The one validator (P3 plan, T08): pattern, minimum and additionalProperties are checked before relaying."""
    desk = Desk("secret-key")
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "dbench-tools.json").write_text(json.dumps({"endpoint": desk.url, "tools": [
        {"type": "function", "function": {"name": "book_ticket", "description": "Book a ticket.", "parameters": {
            "type": "object", "additionalProperties": False, "required": ["account", "quantity"],
            "properties": {"account": {"type": "string", "pattern": "^[A-Z]{4}-[0-9]{2}$"},
                           "quantity": {"type": "integer", "minimum": 1}}}}}]}))

    def prepare(room):
        (room.run_dir / "relay-header").write_text("X-Relay-Token: secret-key\n")

    script = [{"calls": [("book_ticket", {"account": "NRDF-01", "quantity": 100, "comment": "x"})]},
              {"calls": [("book_ticket", {"account": "nrdf-01", "quantity": 100})]},
              {"calls": [("book_ticket", {"account": "NRDF-01", "quantity": 0})]},
              {"calls": [("book_ticket", {"account": "NRDF-01", "quantity": 100})]},
              {"calls": [FINISH]}]
    model, _, context, _ = run_agent(tmp_path, monkeypatch, script, prepare=prepare, environment_dir=env_dir)
    assert meta(context)["counters"]["malformed_calls"] == 3
    assert desk.calls == [("/tools/book_ticket", {"account": "NRDF-01", "quantity": 100}, True)]
    results = [m["content"] for m in model.requests[3]["messages"] if m["role"] == "tool"]
    assert "unexpected field 'comment'" in results[0]
    assert "must match the pattern" in results[1]
    assert "must be at least 1" in results[2]


def test_a_relayed_call_whose_staged_arguments_change_is_not_sent(tmp_path, monkeypatch):
    """Review C9: the staged arguments belong to the agent user; if they change before the relay reads them
    (the model's own process rewriting them), the call is not made."""
    desk = Desk("secret-key")
    env_dir = tmp_path / "environment"
    env_dir.mkdir()
    (env_dir / "dbench-tools.json").write_text(json.dumps({"endpoint": desk.url, "tools": [
        {"type": "function", "function": {"name": "book_ticket", "description": "Book a ticket.", "parameters": {
            "type": "object", "required": ["quantity"], "properties": {"quantity": {"type": "integer"}}}}}]}))

    def prepare(room):
        (room.run_dir / "relay-header").write_text("X-Relay-Token: secret-key\n")
        upload = room.upload_file

        async def upload_then_tamper(source_path, target_path):
            await upload(source_path, target_path)
            if target_path.startswith("/tmp/dbench-tool-"):
                Path(target_path).write_text('{"quantity": 999999}')

        room.upload_file = upload_then_tamper

    script = [{"calls": [("book_ticket", {"quantity": 100})]}, {"calls": [FINISH]}]
    model, _, _, _ = run_agent(tmp_path, monkeypatch, script, prepare=prepare, environment_dir=env_dir)
    assert desk.calls == []
    result = [m["content"] for m in model.requests[1]["messages"] if m["role"] == "tool"][0]
    assert "arguments changed" in result, result


def test_a_file_written_with_write_file_is_readable_like_a_shell_written_one(tmp_path, monkeypatch):
    """In a hardened room even root cannot read a private file, so a file the model writes must not be 0600
    (Harbor could not pack /app; found in the P3 trial run, T07)."""
    script = [{"calls": [("write_file", {"path": "result.json", "content": "{}"})]}, {"calls": [FINISH]}]
    _, room, _, _ = run_agent(tmp_path, monkeypatch, script)
    uploads = [mode for target, mode in room.upload_modes if target.startswith("/tmp/dbench-upload-")]
    assert uploads and all(mode == 0o644 for mode in uploads), [oct(m) for m in uploads]


def test_text_no_encoder_accepts_does_not_crash_the_run(tmp_path, monkeypatch):
    """A lone surrogate escape in a tool call's arguments is valid JSON but no UTF-8 encoder accepts it: the
    transcript writes it escaped and the run goes on (a crash would be voided as our fault)."""
    script = [{"calls": [("write_file", '{"path": "a.txt", "content": "x\\ud800y"}')]}, {"calls": [FINISH]}]
    _, _, context, records = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["end_reason"] == "finished"
    assert any(r["type"] in ("tool", "tool_error") for r in records)


def test_a_file_name_with_a_newline_and_tabs_does_not_break_the_listing(tmp_path, monkeypatch):
    script = [{"calls": [("bash", {"command": "touch $'/app/a\\nb\\t1\\t2'"})]}, {"calls": [FINISH]}]
    _, _, context, records = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["end_reason"] == "finished"
    added = [p for r in records if r["type"] == "listing" for p in r.get("added", [])]
    assert "a\nb\t1\t2" in added, added


def test_the_end_of_run_sweep_makes_private_files_readable(tmp_path, monkeypatch):
    """Harbor packs /app inside the room for a job with an exclude, where even root cannot read a private file;
    a model may make one by plain means (umask 077). The sweep makes everything readable."""
    script = [{"calls": [("bash", {"command": "umask 077; mkdir -p /app/out; echo '{}' > /app/out/r.json"})]},
              {"calls": [FINISH]}]
    _, room, context, _ = run_agent(tmp_path, monkeypatch, script)
    assert meta(context)["end_reason"] == "finished"
    for path in (room.app / "out", room.app / "out" / "r.json"):
        assert path.stat().st_mode & 0o004, (path, oct(path.stat().st_mode))


def test_the_served_model_and_the_base_image_are_recorded(tmp_path, monkeypatch):
    """Provenance (review B11): the model id the server says it answered with, and the room's base image."""
    _, _, context, records = run_agent(tmp_path, monkeypatch, [{"calls": [FINISH]}])
    m = meta(context)
    assert m["served_models"] == ["fake-model"]
    assert "base_image" in m and records[0]["base_image"] == m["base_image"]

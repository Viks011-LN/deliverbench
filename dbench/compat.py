"""dbench compat: check a setup's plumbing before any scored run.

Uses the agent's own streaming code, so it tests exactly the path a run takes. Checks:
  model id         the served model list contains the setup's model id (and its context length, if reported)
  tool call        one tool call comes back as a structured call with the right arguments
  parallel calls   two calls in one reply (information only: no job requires it)
  round trip       a tool result goes back and the model uses it
  reasoning        the reasoning field, if the server sends one, is accepted when passed back
  length cut-off   a reply cut at max_tokens reports finish_reason "length"
  run request      the run's exact request: the agent's system prompt, its full tool list and the full reply
                   budget, then a reply without a tool followed by the agent's nudge
  context length   the setup card states the context length (the reply-budget rule needs it), and the server's
                   answer to a request whose prompt plus max_tokens exceeds it is one the agent understands:
                   a refusal it recognises as a context overflow (the agent then halves the budget once), or a clamp
  typed arguments  a call's integer, number and list arguments come back as JSON numbers and a list, not text
                   (T08 needs an integer and a number, finish.missing a list, read_file integers)
  broken call back a reply whose tool call has unparseable arguments goes back in the history as received (the
                   agent sends it back as is, with an error as the tool result), and the server accepts the next
                   request: some engines parse every call when they render the history, and refuse
  usage            the stream reports token usage (the reply-budget rule estimates the prompt from it; without it
                   the estimate comes from characters and runs high)
  long prompt      a prompt that alone exceeds the context is refused in words the agent recognises, never
                   silently cut (run only for contexts up to 262,144 tokens: a longer prompt is a heavy request)
  edited history   a history as context relief leaves it (agent 2.0.0): an earlier reply's thinking replaced by a
                   note (in the reasoning field the server uses, if any) and an earlier tool result replaced by a
                   note; the server accepts the next request
Every request carries the setup's own sampling and reasoning-effort settings, so a server that rejects
them fails here, not in a scored run.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import openai

from dbench.agent import (CONTEXT_OVERFLOW, MAX_TOKENS_PER_REPLY, MAX_TURNS, NUDGE, PARSER_MISS, SYSTEM_PROMPT,
                          THINKING_DROPPED, TOOLS, DeliverAgent)
from dbench.endpoints import Setup

TYPED_TOOL = {"type": "function", "function": {
    "name": "place_order", "description": "Place an order.",
    "parameters": {"type": "object", "required": ["quantity", "price", "tags"], "properties": {
        "quantity": {"type": "integer"}, "price": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}}}}}}
LONG_PROMPT_MAX_CONTEXT = 262_144
ECHO_TOOL = {"type": "function", "function": {
    "name": "echo_value", "description": "Echo a value back.",
    "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}}
SYSTEM = "You are taking part in a test of tool calling. Follow each instruction exactly."
REASONING_FIELDS = ("reasoning_content", "reasoning")


@dataclass
class Result:
    name: str
    status: str  # pass, fail or info
    detail: str


def _args(call: dict) -> dict:
    try:
        return json.loads(call["function"]["arguments"] or "{}")
    except json.JSONDecodeError:
        return {}


class Compat:
    def __init__(self, setup: Setup, api_key: str = "none"):
        self.setup = setup
        self.client = openai.AsyncOpenAI(base_url=setup.url, api_key=api_key, max_retries=0, timeout=300)
        self.agent = DeliverAgent(logs_dir=Path(tempfile.mkdtemp(prefix="dbench-compat-")))
        self.reasoning_seen: set[str] = set()

    def _request(self, tools: bool | list = True, max_tokens: int = 4096) -> dict:
        req = {"model": self.setup.model, "max_tokens": max_tokens, "stream": True,
               "stream_options": {"include_usage": True}}
        if tools:
            req["tools"] = tools if isinstance(tools, list) else [ECHO_TOOL]
        for key in ("temperature", "top_p", "reasoning_effort"):
            value = getattr(self.setup, key)
            if value not in (None, ""):
                req[key] = value
        return req

    async def _reply(self, messages: list, **kw) -> dict:
        reply = await self.agent._stream_once(self.client, self._request(**kw), messages)
        self.reasoning_seen |= {k for k in REASONING_FIELDS if reply["message"].get(k)}
        return reply

    def model_id(self) -> Result:
        try:
            with urllib.request.urlopen(f"{self.setup.url.rstrip('/')}/models", timeout=30) as resp:
                models = json.load(resp).get("data", [])
        except Exception as exc:  # noqa: BLE001
            return Result("model id", "fail", f"could not list models ({type(exc).__name__})")
        ids = [m.get("id") for m in models]
        if self.setup.model not in ids:
            return Result("model id", "fail", f"server serves {ids}, setup says {self.setup.model!r}")
        info = next(m for m in models if m.get("id") == self.setup.model)
        ctx = info.get("max_model_len") or info.get("context_length")
        detail = f"served as {self.setup.model!r}" + (f"; reports context {ctx:,} tokens" if ctx else "")
        if ctx and self.setup.context_length and ctx != self.setup.context_length:
            return Result("model id", "fail", detail + f", but the setup card says {self.setup.context_length:,}")
        return Result("model id", "pass", detail)

    async def tool_call(self) -> Result:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the echo_value tool once with value "alpha". Do not write anything else.'}]
        reply = await self._reply(msgs)
        calls = reply["message"].get("tool_calls") or []
        if not calls:
            text = json.dumps(reply["message"])
            why = "the call came back as plain text (parser miss)" if PARSER_MISS.search(text) else "no tool call"
            return Result("tool call", "fail", why)
        call = calls[0]
        if call["function"]["name"] != "echo_value" or _args(call).get("value") != "alpha":
            return Result("tool call", "fail", f"unexpected call {call['function']}")
        return Result("tool call", "pass", f"structured call, arguments parsed, {reply['seconds']:.1f} s")

    async def parallel_calls(self) -> Result:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the echo_value tool twice in one reply: once with value "one" and '
                                            'once with value "two".'}]
        reply = await self._reply(msgs)
        values = sorted(_args(c).get("value", "") for c in reply["message"].get("tool_calls") or [])
        if values == ["one", "two"]:
            return Result("parallel calls", "pass", "two calls in one reply")
        return Result("parallel calls", "info", f"got {len(values)} call(s) in one reply; jobs don't need more than one")

    async def round_trip(self) -> tuple[Result, Result]:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the echo_value tool with value "beta". When you get the result, reply '
                                            "with only the secret word it contains, as plain text."}]
        first = await self._reply(msgs)
        calls = first["message"].get("tool_calls") or []
        if not calls:
            fail = Result("round trip", "fail", "no tool call to answer")
            return fail, Result("reasoning", "info", "not reached")
        sent_reasoning = [k for k in REASONING_FIELDS if first["message"].get(k)]
        msgs += [first["message"], {"role": "tool", "tool_call_id": calls[0]["id"], "content": "The secret word is PELICAN."}]
        try:
            second = await self._reply(msgs)
        except openai.BadRequestError as exc:
            detail = f"server rejected the history: {str(exc)[:200]}"
            reasoning = Result("reasoning", "fail", detail) if sent_reasoning else Result("reasoning", "info", "none sent")
            return Result("round trip", "fail", detail), reasoning
        text = (second["message"].get("content") or "") + json.dumps(second["message"].get("tool_calls") or [])
        trip = Result("round trip", "pass" if "PELICAN" in text.upper() else "fail",
                      "the tool result reached the model" if "PELICAN" in text.upper() else f"reply: {text[:120]!r}")
        if sent_reasoning:
            reasoning = Result("reasoning", "pass", f"field {sent_reasoning[0]!r} passed back and accepted")
        else:
            reasoning = Result("reasoning", "info", "no reasoning field returned (thinking off, or not exposed)")
        return trip, reasoning

    async def length_cutoff(self) -> Result:
        msgs = [{"role": "user", "content": "Write a 500-word essay about how bond markets work."}]
        reply = await self._reply(msgs, tools=False, max_tokens=16)
        if reply["finish_reason"] == "length":
            return Result("length cut-off", "pass", "finish_reason 'length' at max_tokens 16")
        return Result("length cut-off", "fail", f"finish_reason {reply['finish_reason']!r} at max_tokens 16")

    async def run_request(self) -> Result:
        """The request shape of a real run: system prompt, full tool list, full reply budget, and a nudge turn."""
        system = SYSTEM_PROMPT.format(command_timeout=180, max_turns=MAX_TURNS, minutes=45)
        msgs = [{"role": "system", "content": system},
                {"role": "user", "content": "This is a plumbing check. Reply with the single word READY as plain "
                                            "text, without calling any tool."}]
        first = await self._reply(msgs, tools=TOOLS, max_tokens=MAX_TOKENS_PER_REPLY)
        msgs += [first["message"], {"role": "user", "content": NUDGE + "\n(For this check: call finish with status "
                                                                       "done and summary ok.)"}]
        second = await self._reply(msgs, tools=TOOLS, max_tokens=MAX_TOKENS_PER_REPLY)
        names = [c["function"]["name"] for c in second["message"].get("tool_calls") or []]
        return Result("run request", "pass", f"accepted with {len(TOOLS)} tools and max_tokens "
                                             f"{MAX_TOKENS_PER_REPLY:,}; after the nudge the model called "
                                             f"{names or 'no tool'}")

    async def typed_arguments(self) -> Result:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the place_order tool once with quantity 1200, price 101.25 and tags '
                                            '["fx", "spot"]. Do not write anything else.'}]
        reply = await self._reply(msgs, tools=[TYPED_TOOL])
        calls = reply["message"].get("tool_calls") or []
        if not calls:
            return Result("typed arguments", "fail", "no tool call")
        args = _args(calls[0])
        q, p, tags = args.get("quantity"), args.get("price"), args.get("tags")
        ok = (isinstance(q, int) and not isinstance(q, bool) and q == 1200
              and isinstance(p, (int, float)) and not isinstance(p, bool) and abs(p - 101.25) < 1e-9
              and tags == ["fx", "spot"])
        return Result("typed arguments", "pass" if ok else "fail",
                      "an integer, a number and a list" if ok else f"arguments came back as {calls[0]['function']['arguments']!r}")

    async def broken_call_back(self) -> Result:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the echo_value tool with value "gamma".'},
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call_0", "type": "function",
                    "function": {"name": "echo_value", "arguments": '{"value": "gam'}}]},
                {"role": "tool", "tool_call_id": "call_0",
                 "content": "error: the arguments are not valid JSON (Unterminated string)"},
                {"role": "user", "content": "That call was broken. Reply with the single word RETRY as plain text."}]
        try:
            reply = await self._reply(msgs)
        except openai.BadRequestError as exc:
            return Result("broken call back", "fail", "the server refuses a history holding a call with unparseable "
                                                      f"arguments (as the agent sends it back): {str(exc)[:200]}")
        return Result("broken call back", "pass", "a history holding a call with unparseable arguments is accepted "
                                                  f"({reply['seconds']:.1f} s)")

    async def edited_history(self) -> Result:
        """A history as context relief leaves it: the server must accept it (some engines check that a reasoning
        field or a tool result matches what they produced, and refuse an edited one)."""
        assistant = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_0", "type": "function", "function": {"name": "echo_value", "arguments": '{"value": "delta"}'}}]}
        field = next(iter(sorted(self.reasoning_seen)), None)
        if field:
            assistant[field] = THINKING_DROPPED
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": 'Call the echo_value tool with value "delta".'},
                assistant,
                {"role": "tool", "tool_call_id": "call_0",
                 "content": "[output dropped to save context: an earlier echo_value result from turn 1; run the "
                            "command or read the file again if you need it]"},
                {"role": "user", "content": "Reply with the single word OK as plain text."}]
        try:
            reply = await self._reply(msgs)
        except openai.BadRequestError as exc:
            return Result("edited history", "fail", "the server refuses a history edited by context relief: "
                                                    f"{str(exc)[:200]}")
        what = (f"thinking in {field!r} and a tool result replaced by notes" if field
                else "a tool result replaced by a note")
        return Result("edited history", "pass", f"accepted ({what}; {reply['seconds']:.1f} s)")

    async def usage(self) -> Result:
        reply = await self._reply([{"role": "user", "content": "Reply with the single word OK."}], tools=False,
                                  max_tokens=64)
        usage = reply.get("usage")
        if usage is None or not getattr(usage, "prompt_tokens", 0):
            return Result("usage", "fail", "the stream reports no token usage (stream_options include_usage)")
        return Result("usage", "pass", f"prompt {usage.prompt_tokens} tokens, reply {usage.completion_tokens} tokens")

    async def long_prompt(self) -> Result:
        ctx = self.setup.context_length
        if not ctx:
            return Result("long prompt", "info", "no context length on the card")
        if ctx > LONG_PROMPT_MAX_CONTEXT:
            return Result("long prompt", "info", f"not run: a prompt over {ctx:,} tokens is a heavy request, and no "
                                                 "job's run comes near it")
        filler = "The quick brown fox jumps over the lazy dog. " * (ctx // 8 + 1000)  # well over ctx tokens
        msgs = [{"role": "user", "content": filler + "\nReply with the single word OK."}]
        try:
            await self._reply(msgs, tools=False, max_tokens=16)
        except openai.BadRequestError as exc:
            if CONTEXT_OVERFLOW.search(str(exc)):
                return Result("long prompt", "pass", "a prompt over the context is refused, in words the agent "
                                                     "recognises")
            return Result("long prompt", "fail", f"refused in words the agent does not recognise: {str(exc)[:200]}")
        return Result("long prompt", "fail", "a prompt over the context was answered: the server cuts prompts "
                                             "silently, so a run would lose its start without knowing")

    async def context_length(self) -> Result:
        ctx = self.setup.context_length
        if not ctx:
            return Result("context length", "fail", "the setup card has no context_length; the reply-budget rule "
                                                    "needs it (copy it from the server's model list)")
        msgs = [{"role": "user", "content": "Reply with the single word OK."}]
        try:
            await self._reply(msgs, tools=False, max_tokens=ctx)  # prompt + max_tokens > context, by a little
        except openai.BadRequestError as exc:
            if CONTEXT_OVERFLOW.search(str(exc)):
                return Result("context length", "pass", f"card says {ctx:,}; the server refuses a request over it, "
                                                        "and the agent recognises the refusal")
            return Result("context length", "fail", "the server refuses a request over the context, but with a "
                                                    f"message the agent does not recognise: {str(exc)[:200]}")
        return Result("context length", "pass", f"card says {ctx:,}; the server clamps a request over it")

    async def run(self) -> list[Result]:
        results = [self.model_id()]
        for check in (self.tool_call, self.parallel_calls):
            results.append(await self._guard(check.__name__.replace("_", " "), check))
        try:
            results.extend(await self.round_trip())
        except Exception as exc:  # noqa: BLE001
            results.append(Result("round trip", "fail", f"{type(exc).__name__}: {str(exc)[:200]}"))
        results.append(await self._guard("length cut-off", self.length_cutoff))
        results.append(await self._guard("run request", self.run_request))
        results.append(await self._guard("context length", self.context_length))
        results.append(await self._guard("typed arguments", self.typed_arguments))
        results.append(await self._guard("broken call back", self.broken_call_back))
        results.append(await self._guard("usage", self.usage))
        results.append(await self._guard("long prompt", self.long_prompt))
        results.append(await self._guard("edited history", self.edited_history))
        return results

    @staticmethod
    async def _guard(name, check) -> Result:
        try:
            return await check()
        except Exception as exc:  # noqa: BLE001 - a rejected request is a failed check, not a crash
            return Result(name, "fail", f"{type(exc).__name__}: {str(exc)[:200]}")


def run_compat(setup: Setup, api_key: str = "none") -> list[Result]:
    return asyncio.run(Compat(setup, api_key).run())


def print_results(setup: Setup, results: list[Result]) -> bool:
    print(f"compatibility check: {setup.name} ({setup.model})")
    for r in results:
        print(f"  {r.status.upper():<4}  {r.name:<15} {r.detail}")
    ok = all(r.status != "fail" for r in results)
    print("result:", "compatible" if ok else "NOT compatible: fix the server setup before scoring it")
    return ok

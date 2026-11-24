#!/usr/bin/env python3
"""List every nudge (a reply without a tool call) and every malformed tool call in a set of runs.

    uv run python scripts/plumbing_events.py jobs/pilot/pilot--*
"""
import json
import sys
from pathlib import Path

MALFORMED = ("error: unknown tool", "error: missing argument", "error: the arguments",
             "error: finish must", "error: status must")

for job_dir in sorted(sys.argv[1:]):
    for transcript in sorted(Path(job_dir).glob("*/agent/deliverbench-transcript.jsonl")):
        rows = [json.loads(line) for line in transcript.read_text().splitlines()]
        start = next((r for r in rows if r["type"] == "start"), {})
        setup = (start.get("setup") or {}).get("name", "?")
        trial = transcript.parts[-3]
        for r in rows:
            if r["type"] == "model" and not r["message"].get("tool_calls"):
                text = (r["message"].get("content") or "").replace("\n", " ")[:150]
                print(f"{setup:18} {trial:40} turn {r['turn']:>3}  NUDGE    finish={r['finish_reason']} text={text!r}")
            if r["type"] == "tool" and str(r.get("result", "")).startswith(MALFORMED):
                args = json.dumps(r.get("args"))[:110]
                print(f"{setup:18} {trial:40} turn {r['turn']:>3}  MALFORMED {r['name']} {args} -> {r['result'][:90]}")

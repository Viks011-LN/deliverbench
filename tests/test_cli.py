"""F01: every Harbor process started by dbench has telemetry forced off."""
from __future__ import annotations

import subprocess

from dbench import cli
from dbench.telemetry import TELEMETRY_VAR, harbor_env, telemetry_is_off

ENDPOINTS = """
[test-setup]
url = "http://localhost:9/v1"
model = "test-model"
"""


def test_harbor_env_forces_telemetry_off_whatever_the_caller_says():
    for caller_value in ("1", "true", "on", "", None):
        base = {"PATH": "/usr/bin", "KEEP": "me"}
        if caller_value is not None:
            base[TELEMETRY_VAR] = caller_value
        env = harbor_env(base)
        assert env[TELEMETRY_VAR] == "0"
        assert env["KEEP"] == "me"


def test_telemetry_is_off_accepts_harbors_off_values_only():
    assert telemetry_is_off({TELEMETRY_VAR: "0"})
    assert telemetry_is_off({TELEMETRY_VAR: " Off "})
    assert not telemetry_is_off({TELEMETRY_VAR: "1"})
    assert not telemetry_is_off({})


def test_dbench_run_starts_harbor_with_our_agent_and_telemetry_off(tmp_path, monkeypatch):
    endpoints = tmp_path / "endpoints.local.toml"
    endpoints.write_text(ENDPOINTS, encoding="utf-8")
    monkeypatch.setenv(TELEMETRY_VAR, "1")  # the caller has it on
    seen = {}

    def fake_run(argv, env):
        seen["argv"], seen["env"] = argv, env
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    code = cli.main(["run", "--setup", "test-setup", "--task", "tasks/T00-hello-fix", "--endpoints", str(endpoints)])
    assert code == 0
    assert seen["env"][TELEMETRY_VAR] == "0"
    assert seen["env"]["DBENCH_SETUP"] == "test-setup"
    argv = seen["argv"]
    assert argv[1] == "run"
    assert argv[argv.index("-a") + 1] == cli.AGENT_IMPORT_PATH
    assert argv[argv.index("-e") + 1] == "docker"
    # runner faults (our side) and endpoint faults are re-run up to twice; nothing the model can cause is
    retried = {argv[i + 1] for i, a in enumerate(argv) if a == "--retry-include"}
    assert argv[argv.index("--max-retries") + 1] == "2"
    assert {"EnvironmentStartTimeoutError", "SandboxBuildFailedError", "HealthcheckError",
            "EndpointFaultError"} <= retried
    assert not retried & {"VerifierTimeoutError", "AgentTimeoutError", "MemoryLimitExceededError",
                          "SandboxLikelyOutOfMemoryError", "CancelledError"}

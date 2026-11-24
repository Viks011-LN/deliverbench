"""Harbor sends anonymous usage telemetry unless HARBOR_TELEMETRY is set to an off value.

deliverbench keeps it off in two places: the CLI forces it off for every Harbor process it starts,
and the agent refuses to start inside a Harbor process where it is on (for direct `harbor run` calls).
"""
from __future__ import annotations

import os
from collections.abc import Mapping

TELEMETRY_VAR = "HARBOR_TELEMETRY"
OFF = "0"
_OFF_VALUES = {"0", "false", "no", "off", "disabled"}  # Harbor's own list of values that disable it


def harbor_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A copy of the environment for a Harbor process, with telemetry forced off."""
    env = dict(os.environ if base is None else base)
    env[TELEMETRY_VAR] = OFF
    return env


def telemetry_is_off(env: Mapping[str, str] | None = None) -> bool:
    value = (os.environ if env is None else env).get(TELEMETRY_VAR, "")
    return value.strip().lower() in _OFF_VALUES


def require_telemetry_off(env: Mapping[str, str] | None = None) -> None:
    if not telemetry_is_off(env):
        raise RuntimeError(
            "Harbor telemetry is on in this process. Run jobs through `dbench run`, "
            f"or set {TELEMETRY_VAR}=0 before calling harbor directly."
        )

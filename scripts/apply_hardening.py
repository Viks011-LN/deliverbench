#!/usr/bin/env python3
"""Add deliverbench's room hardening to every job (idempotent).

- environment/docker-compose.yaml: the main room drops every Linux capability, sets no-new-privileges and
  a process limit (a compose file is created for jobs that have none).
- task.toml [environment]: CPU and memory limits, which Harbor applies itself.
dbench.tasks.validate_job refuses a job without these.
"""
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "tasks"
MAIN_LINES = [
    "    cap_drop: [ALL]",
    '    security_opt: ["no-new-privileges:true"]',
    "    pids_limit: 512",
]
RESOURCE_LINES = ["cpus = 4", "memory_mb = 4096"]


def harden_compose(path: Path) -> None:
    if not path.exists():
        path.write_text("# Room hardening for the main room (scripts/apply_hardening.py).\nservices:\n  main:\n"
                        + "\n".join(MAIN_LINES) + "\n", encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    if "cap_drop: [ALL]" in text:
        return
    if "\n  main:\n" in text:
        text = text.replace("\n  main:\n", "\n  main:\n" + "\n".join(MAIN_LINES) + "\n", 1)
    else:
        text = text.replace("services:\n", "services:\n  main:\n" + "\n".join(MAIN_LINES) + "\n", 1)
    path.write_text(text, encoding="utf-8")


def harden_task(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "memory_mb" in text:
        return
    text = text.replace('os = "linux"\n', 'os = "linux"\n' + "\n".join(RESOURCE_LINES) + "\n", 1)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    for job in sorted(p for p in TASKS.iterdir() if (p / "deliverbench.toml").exists()):
        harden_compose(job / "environment" / "docker-compose.yaml")
        harden_task(job / "task.toml")
        print("hardened", job.name)

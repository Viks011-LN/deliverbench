"""A stand-in for a Harbor environment: /app and /run/dbench map to local folders; commands run in local bash."""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

from harbor.environments.base import ExecResult


class FakeRoom:
    def __init__(self, root: Path, environment_dir: Path | None = None):
        self.root = root
        self.environment_dir = environment_dir
        self.app = root / "app"
        self.run_dir = root / "run-dbench"
        self.app.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.commands: list[str] = []
        self.users: list[str | None] = []

    def _local(self, text: str) -> str:
        return text.replace("/run/dbench", str(self.run_dir)).replace("/app", str(self.app))

    async def exec(self, command: str, cwd: str | None = None, env=None, timeout_sec=None, user=None) -> ExecResult:
        self.commands.append(command)
        self.users.append(user)
        if "dbench-end-sweep" in command or "kill -KILL -1" in command:
            # The end-of-run sweep. In a real room it stops the processes started during the run; here it would
            # stop processes of the user running the tests, so it is recorded and never run.
            return ExecResult(stdout="", stderr="", return_code=0)
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", self._local(command), cwd=self._local(cwd or "/app"),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
        return ExecResult(stdout=out.decode(), stderr=err.decode(), return_code=proc.returncode)

    async def upload_file(self, source_path, target_path: str) -> None:
        self.upload_modes = getattr(self, "upload_modes", []) + [(target_path, Path(source_path).stat().st_mode & 0o777)]
        target = Path(self._local(target_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)

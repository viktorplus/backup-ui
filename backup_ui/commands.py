from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class CommandResult:
    code: int
    stdout: str
    stderr: str


def run(cmd: list[str], timeout: int = 120, input_bytes: bytes | None = None) -> CommandResult:
    try:
        proc = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            code=proc.returncode,
            stdout=proc.stdout.decode("utf-8", "replace"),
            stderr=proc.stderr.decode("utf-8", "replace"),
        )
    except FileNotFoundError as exc:
        return CommandResult(code=127, stdout="", stderr=str(exc))
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            code=124,
            stdout=(exc.stdout or b"").decode("utf-8", "replace"),
            stderr=(exc.stderr or b"").decode("utf-8", "replace") + "\nКоманда превысила лимит времени",
        )


def available(binary: str) -> bool:
    return run(["sh", "-lc", f"command -v {binary} >/dev/null 2>&1"], timeout=5).code == 0

from __future__ import annotations
import shlex
from pathlib import Path
from typing import List

from backend.api.utils.security import validate_command


async def build_universal(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event) -> List[str]:
    await log_cb("warn", "Universal adapter: running user-specified command in sandbox. Artifacts not collected automatically.")
    cmd = shlex.split(request.start_command or "")
    if not cmd or not validate_command(cmd):
        await log_cb("error", "Provided command is empty or not allowed.")
        return []
    await log_cb("info", f"Would run: {' '.join(cmd)}")
    return []

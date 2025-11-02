from __future__ import annotations
from pathlib import Path
from typing import List

# TODO: Implement Batch/PowerShell packaging using NSIS makensis. Placeholder renders .nsi script.

async def build_batch(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event) -> List[str]:
    await log_cb("warn", f"Batch/PowerShell adapter not yet implemented; start command: {request.start_command!r}")
    return []

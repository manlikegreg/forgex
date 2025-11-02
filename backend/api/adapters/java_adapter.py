from __future__ import annotations
from pathlib import Path
from typing import List

# TODO: Implement Java build using jpackage/jlink or jar. Placeholder.

async def build_java(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event) -> List[str]:
    await log_cb("warn", f"Java build adapter not yet implemented; start command: {request.start_command!r}")
    return []

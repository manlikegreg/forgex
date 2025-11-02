from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import List


async def _run_and_stream(cmd: list[str], env: dict, cwd: Path, log_cb, timeout: int, cancel_event: asyncio.Event) -> int:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        await log_cb("error", f"Command not found: {cmd[0]}")
        return 127

    async def reader(stream, level):
        while True:
            line = await stream.readline()
            if not line:
                break
            await log_cb(level, line.decode(errors='ignore').rstrip())

    readers = [asyncio.create_task(reader(proc.stdout, "info")), asyncio.create_task(reader(proc.stderr, "error"))]
    try:
        while True:
            if cancel_event.is_set():
                proc.terminate(); await log_cb("warn", "Build cancelled; terminating process")
                return -1
            try:
                return await asyncio.wait_for(proc.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
    finally:
        for t in readers:
            t.cancel()


async def build_go(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event) -> List[str]:
    env = os.environ.copy()
    dist_dir = workdir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Ensure go present
    code = await _run_and_stream(["go", "version"], env, workdir, log_cb, timeout_seconds, cancel_event)
    if code != 0:
        await log_cb("error", "Go toolchain not found in PATH")
        return []

    # Download deps if mod file present
    if (workdir / "go.mod").exists():
        _ = await _run_and_stream(["go", "mod", "download"], env, workdir, log_cb, timeout_seconds, cancel_event)

    # Build current module/package into single binary
    safe_name = (getattr(request, 'output_name', None) or Path(project_name).stem).replace(' ', '_')
    out_path = dist_dir / safe_name

    # Honor linux target; for cross-compile, allow GOOS/GOARCH env externally
    code = await _run_and_stream(["go", "build", "-o", str(out_path)], env, workdir, log_cb, timeout_seconds, cancel_event)
    if code != 0:
        return []

    artifacts: List[str] = []
    if out_path.exists():
        artifacts.append(str(out_path))
    return artifacts

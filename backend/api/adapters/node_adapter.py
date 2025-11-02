from __future__ import annotations
import asyncio
import json
import os
import shlex
from pathlib import Path
from typing import List, Optional

from backend.api.utils.security import validate_command


async def _run_and_stream(cmd: List[str], env: dict, cwd: Path, log_cb, timeout: int, cancel_event: asyncio.Event) -> int:
    # Only allow known tools
    if not cmd:
        await log_cb("error", "Empty command")
        return 2
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
            text = line.decode(errors='ignore').rstrip()
            await log_cb(level, text)

    readers = [asyncio.create_task(reader(proc.stdout, "info")), asyncio.create_task(reader(proc.stderr, "error"))]
    try:
        while True:
            if cancel_event.is_set():
                proc.terminate()
                await log_cb("warn", "Build cancelled; terminating process")
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10)
                except asyncio.TimeoutError:
                    proc.kill()
                return -1
            try:
                return await asyncio.wait_for(proc.wait(), timeout=1)
            except asyncio.TimeoutError:
                pass
    finally:
        for t in readers:
            t.cancel()


def _detect_entry(workdir: Path, start_command: str) -> Optional[str]:
    parts = shlex.split(start_command or "")
    if parts and parts[0] in {"node", "node.exe"} and len(parts) >= 2:
        return parts[1]
    pj = workdir / "package.json"
    if pj.exists():
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
            if data.get("bin") and isinstance(data["bin"], str):
                return data["bin"]
            if data.get("main") and isinstance(data["main"], str):
                return data["main"]
        except Exception:
            pass
    # Fallbacks
    for name in ["index.js", "server.js", "app.js", "main.js"]:
        if (workdir / name).exists():
            return name
    return None


async def build_node(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event) -> List[str]:
    env = os.environ.copy()
    dist_dir = workdir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Install dependencies if package.json
    if (workdir / "package.json").exists():
        await log_cb("info", "Installing npm dependencies")
        code = await _run_and_stream(["npm", "install"], env, workdir, log_cb, timeout_seconds, cancel_event)
        if code != 0:
            return []

    entry = _detect_entry(workdir, getattr(request, 'start_command', '') or '')
    if not entry:
        await log_cb("error", "Could not determine Node.js entry. Provide start_command like 'node server.js' or ensure package.json has main/bin.")
        return []

    # Build single binary using pkg (Linux host default)
    safe_name = (getattr(request, 'output_name', None) or Path(project_name).stem).replace(' ', '_')
    out_path = dist_dir / safe_name
    target = os.getenv('FORGEX_NODE_TARGET') or 'node20-linux-x64'

    await log_cb("info", f"Packaging with pkg -> target={target}")
    code = await _run_and_stream(["npx", "-y", "pkg", entry, "--targets", target, "--output", str(out_path)], env, workdir, log_cb, timeout_seconds, cancel_event)
    if code != 0:
        return []

    artifacts: List[str] = []
    if out_path.exists():
        artifacts.append(str(out_path))
    return artifacts

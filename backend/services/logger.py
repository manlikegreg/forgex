from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List
from fastapi import WebSocket
from asyncio import Lock


class LogManager:
    def __init__(self):
        base = Path.home() / ".forgex" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        self.base = base
        self.subscribers: Dict[str, List[WebSocket]] = {}
        self.lock = Lock()
        # Per-build verbosity: when False (default), drop 'debug' log events entirely
        self.verbose: Dict[str, bool] = {}

    async def subscribe(self, build_id: str, ws: WebSocket):
        async with self.lock:
            self.subscribers.setdefault(build_id, []).append(ws)

    async def unsubscribe(self, build_id: str, ws: WebSocket):
        async with self.lock:
            subs = self.subscribers.get(build_id, [])
            if ws in subs:
                subs.remove(ws)
            if not subs and build_id in self.subscribers:
                self.subscribers.pop(build_id, None)

    def log_path(self, build_id: str) -> Path:
        return self.base / f"{build_id}.log"

    async def emit_log(self, build_id: str, level: str, message: str):
        # Filter verbose logs unless enabled for this build
        if level == 'debug' and not self.verbose.get(build_id, False):
            return
        payload = {
            "build_id": build_id,
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        }
        # Append to file
        self.log_path(build_id).parent.mkdir(parents=True, exist_ok=True)
        with self.log_path(build_id).open('a', encoding='utf-8') as f:
            f.write(json.dumps(payload) + "\n")
        # Mirror to Python logger
        import logging as _logging
        _lg = _logging.getLogger("forgex.log")
        txt = f"[{build_id}] {level.upper()} {message}"
        if level == 'debug':
            _lg.debug(txt)
        elif level == 'info':
            _lg.info(txt)
        elif level == 'warn':
            _lg.warning(txt)
        elif level == 'error':
            _lg.error(txt)
        else:
            _lg.info(txt)
        # Broadcast
        for ws in list(self.subscribers.get(build_id, [])):
            try:
                if ws.application_state.name == 'CONNECTED':
                    pass
                await ws.send_json(payload)
            except Exception:
                # Best-effort: drop dead sockets
                try:
                    await self.unsubscribe(build_id, ws)
                except Exception:
                    pass

    async def emit_status(self, status_obj: dict):
        # status_obj must contain build_id
        build_id = status_obj.get("build_id")
        payload = {"type": "status", **status_obj}
        for ws in list(self.subscribers.get(build_id, [])):
            try:
                await ws.send_json(payload)
            except Exception:
                try:
                    await self.unsubscribe(build_id, ws)
                except Exception:
                    pass

    def set_verbose(self, build_id: str, enable: bool) -> None:
        # Enable or disable verbose (debug) logs for a specific build
        if enable:
            self.verbose[build_id] = True
        else:
            self.verbose.pop(build_id, None)


log_manager = LogManager()

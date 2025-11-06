from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class CodeSign(BaseModel):
    enable: bool = False
    cert_path: Optional[str] = None
    cert_password: Optional[str] = None  # Will not be logged
    timestamp_url: Optional[str] = "http://timestamp.digicert.com"
    description: Optional[str] = None
    publisher: Optional[str] = None


class BuildRequest(BaseModel):
    project_path: str
    working_dir: str = "."
    language: str = Field(pattern=r"^(python)$")
    start_command: str
    output_type: str = Field(pattern=r"^(exe|app|elf)$")
    include_env: bool = False
    icon_path: Optional[str] = None
    # Windows Task Manager customization (optional)
    process_display_name: Optional[str] = None
    process_icon_path: Optional[str] = None
    extra_files: List[str] = []
    pyinstaller: Optional[Dict[str, Any]] = None
    output_name: Optional[str] = None
    pause_on_exit: bool = False
    pause_on_exit_seconds: Optional[int] = 5
    win_autostart: bool = False
    autostart_method: Optional[str] = Field(default=None, pattern=r"^(task|startup)$")
    code_sign: Optional[CodeSign] = None
    # Optional: generate a Windows helper script to launch the app via PowerShell
    win_smartscreen_helper: bool = False
    # Optional: if helper is generated, log output to a file via CMD redirection
    win_helper_log: bool = False
    win_helper_log_name: Optional[str] = None
    # Target operating system for packaging/runtime tweaks (does not cross-compile)
    target_os: str = Field(default="windows", pattern=r"^(windows|linux|macos)$")
    # Controls whether 'debug' logs are emitted for this build
    verbose: bool = False
    # Privacy: if true, a runtime hook masks Python logging messages inside the packaged app
    privacy_mask_logs: bool = False
    # Offline build: use system Python/site-packages (no venv, no network installs)
    offline_build: bool = False


class BuildStatus(BaseModel):
    build_id: str
    status: str = Field(pattern=r"^(queued|running|success|failed|cancelled)$")
    started_at: datetime
    finished_at: Optional[datetime] = None
    output_files: List[str] = []
    error: Optional[str] = None


class LogEvent(BaseModel):
    build_id: str
    timestamp: datetime
    level: str = Field(pattern=r"^(info|warn|error|debug)$")
    message: str

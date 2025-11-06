from __future__ import annotations
import os
import shlex
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from backend.api.utils.security import validate_command
from backend.api.utils.sandbox import ensure_venv_async


def _parse_entry_from_start(start_command: Optional[str]) -> Optional[str]:
    if not start_command:
        return None
    parts = shlex.split(start_command)
    if not parts:
        return None
    # Common patterns: "python app.py", "py app.py"
    if parts[0] in {"python", "py", "python3"} and len(parts) >= 2:
        # Support "python -m package.module" as well
        if parts[1] == "-m" and len(parts) >= 3:
            mod = parts[2]
            return mod.replace('.', '/') + ".py"
        script = parts[1]
        if script.endswith('.py'):
            return script
    # uvicorn main:app -> attempt mapping to main.py
    if parts[0] == "uvicorn" and ":" in ''.join(parts[1:2]):
        mod = parts[1].split(":")[0]
        return mod.replace('.', '/') + ".py"
    return None


async def _run_and_stream(cmd: List[str], env: Dict[str, str], cwd: Path, log_cb, timeout: int, cancel_event: asyncio.Event) -> int:
    if not validate_command(cmd):
        await log_cb("error", f"Blocked command: {' '.join(cmd)}")
        return 2
    await log_cb("debug", f"Running: {' '.join(shlex.quote(c) for c in cmd)}")
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
        import re
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors='ignore').rstrip()
            # Remap some stderr lines to appropriate levels (PyInstaller/pip often write INFO to stderr)
            derived = level
            low = text.lower()
            if level == "error":
                if ("info:" in low) or text.startswith("INFO") or re.search(r"^\s*\d+\s+INFO:\s*", text):
                    derived = "info"
                elif ("warning" in low) or text.startswith("WARNING"):
                    derived = "warn"
                # pip notices
                elif "a new release of pip is available" in low or "to update, run:" in low:
                    derived = "info"
            await log_cb(derived, text)

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


async def build_python(workdir: Path, project_name: str, build_id: str, request, log_cb, timeout_seconds: int, cancel_event: asyncio.Event) -> List[str]:
    """Build using PyInstaller in onefile mode and return list of artifacts."""
    import sys as _sys
    offline = bool(getattr(request, 'offline_build', False))
    # Defer extra PyInstaller args here so early phases can append before build_cmd exists
    pyi_extras: List[str] = []
    if offline:
        await log_cb("info", "Offline build: using system Python/site-packages (no venv, no network installs)")
        venv_dir = None
        py_bin = Path(_sys.executable)
        env = os.environ.copy()
        # Verify PyInstaller is available
        chk = await _run_and_stream([str(py_bin), "-c", "import PyInstaller"], env, workdir, log_cb, timeout_seconds, cancel_event)
        if chk != 0:
            await log_cb("error", "PyInstaller not available in system environment. Install it (pip install pyinstaller) or disable Offline build.")
            return []
    else:
        await log_cb("debug", f"Creating venv in {workdir / '.venv'}")
        venv_dir, py_bin, pip_bin = await ensure_venv_async(workdir)
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(venv_dir)
        env["PATH"] = f"{venv_dir / ('Scripts' if os.name=='nt' else 'bin')}{os.pathsep}" + env.get("PATH", "")

    # Install deps if requirements.txt exists (skip in offline mode)
    req = workdir / "requirements.txt"
    if offline and req.exists():
        # Verify required packages are available system-wide (no network installs)
        import re as _re
        def _parse_pkg(line: str) -> str:
            s = line.strip()
            # drop markers and hashes
            s = s.split(';', 1)[0].split('#', 1)[0].strip()
            if not s or s.startswith(('-', 'git+', 'http:', 'https:')):
                return ''
            # extract name before version spec/extras
            m = _re.match(r"^[A-Za-z0-9_.-]+", s)
            return m.group(0) if m else ''
        missing = []
        try:
            for raw in req.read_text(encoding='utf-8', errors='ignore').splitlines():
                name = _parse_pkg(raw)
                if not name:
                    continue
                rc = await _run_and_stream([str(py_bin), "-m", "pip", "show", name], env, workdir, lambda lvl, msg: None, timeout_seconds, cancel_event)
                if rc != 0:
                    missing.append(name)
        except Exception:
            pass
        if missing:
            await log_cb('error', f"Offline build: missing required packages: {', '.join(sorted(set(missing)))}. Install them system-wide or disable Offline build.")
            return []
    if not offline and req.exists():
        await log_cb("debug", f"Installing requirements from {req}")
        code = await _run_and_stream([str(py_bin), "-m", "pip", "install", "-r", str(req)], env, workdir, log_cb, timeout_seconds, cancel_event)
        if code != 0:
            return []
    # Ensure pyinstaller available (only in venv mode)
    if not offline:
        await log_cb("info", "Installing PyInstaller (this may take a few minutes)...")
        code = await _run_and_stream([str(py_bin), "-m", "pip", "install", "pyinstaller"], env, workdir, log_cb, timeout_seconds, cancel_event)
        if code != 0:
            return []
        # Best-effort ensure python-dotenv so the runtime hook can load .env automatically
        await log_cb("debug", "Ensuring python-dotenv is installed (optional)")
        _ = await _run_and_stream([str(py_bin), "-m", "pip", "install", "python-dotenv"], env, workdir, log_cb, timeout_seconds, cancel_event)

    # Determine entry
    entry: Optional[str] = _parse_entry_from_start(request.start_command)
    EXCLUDED_DIRS = {'.venv', 'venv', 'env', 'node_modules', 'dist', 'build', '__pycache__', '.git'}
    def _is_excluded(path: Path) -> bool:
        # Exclude paths that pass through known heavy directories
        return any(part in EXCLUDED_DIRS for part in path.parts)
    def _is_excluded_dir(path: Path) -> bool:
        # Exclude only by parent directories; never exclude by file name
        return any(part in EXCLUDED_DIRS for part in path.parent.parts)

    if entry:
        cand = workdir / entry
        if not cand.exists():
            # Try to find by basename anywhere under workdir (excluding venv/node_modules/etc.)
            target = Path(entry).name
            match = next((p for p in workdir.rglob(target) if p.is_file() and not _is_excluded(p)), None)
            if match:
                entry = str(match.relative_to(workdir))
            else:
                entry = None
    if not entry:
        # Fallback to common names in root first
        for name in ["app.py", "main.py", "run.py", "manage.py", "index.py"]:
            if (workdir / name).exists():
                entry = name
                break
    if not entry:
        # Search common names recursively excluding heavy/venv dirs
        for name in ["app.py", "main.py", "run.py", "manage.py", "index.py"]:
            candidates = [p for p in workdir.rglob(name) if p.is_file() and not _is_excluded(p)]
            if candidates:
                entry = str(candidates[0].relative_to(workdir))
                break
    if not entry:
        # As a last resort, if the project contains exactly one .py file, use it (excluding venv/node_modules)
        py_files = [p for p in workdir.rglob('*.py') if p.is_file() and not _is_excluded(p)]
        if len(py_files) == 1:
            entry = str(py_files[0].relative_to(workdir))
    if not entry:
        await log_cb("error", "Could not determine Python entry script. Provide start_command (e.g. 'python your_script.py') or ensure one of app.py/main.py exists.")
        return []
    await log_cb("debug", f"Entry script: {entry}")

    # Optional CLI wrapper for uvicorn to preserve host/port and other args from start_command
    entry_for_build: Optional[str] = None
    try:
        sc = (getattr(request, 'start_command', '') or '').strip()
        parts_sc = shlex.split(sc) if sc else []
        if parts_sc and parts_sc[0].lower() == 'uvicorn':
            uv_args = parts_sc[1:]
            # Decide packaging and import hints based on entry path
            try:
                if entry:
                    from pathlib import Path as _P
                    ep = (_P(workdir) / entry)
                    parent = ep.parent
                    is_pkg = (parent / "__init__.py").exists()
                    target = (uv_args[0] or '') if uv_args else ''
                    app_attr = (target.split(':', 1)[1] if ':' in target else 'app') or 'app'
                    if not is_pkg:
                        # Non-package folder (e.g., test/main.py): use --app-dir and import main
                        if uv_args and uv_args[0]:
                            uv_args[0] = f"main:{app_attr}"
                        else:
                            uv_args = [f"main:{app_attr}"]
                        uv_args = ["--app-dir", str(parent), *uv_args]
                        # Ensure analyzer can find main.py during build
                        pyi_extras += ["--paths", str(parent), "--hidden-import", "main"]
                        await log_cb("debug", f"Using --app-dir={parent}; adding --paths and hidden-import main")
                    else:
                        # Package: rewrite to dotted path and include hidden-import for that module
                        ent = str(entry)
                        dotted = (_P(ent).with_suffix('').as_posix().replace('/', '.'))
                        if uv_args:
                            uv_args[0] = f"{dotted}:{app_attr}"
                        else:
                            uv_args = [f"{dotted}:{app_attr}"]
                        pyi_extras += ["--hidden-import", dotted]
                        await log_cb("debug", f"Rewrote uvicorn target to {uv_args[0]} and will include hidden-import {dotted}")
            except Exception as e:
                await log_cb("warn", f"uvicorn target rewrite skipped: {e}")
            wrapper_uv = workdir / "forgex_uvicorn_entry.py"
            code = (
                "# Auto-generated by ForgeX to run uvicorn with provided CLI args and safe logging (no console)\n"
                "import sys, json, os, logging.config\n"
                "from pathlib import Path\n"
                "from uvicorn import main as _uv_main\n"
                "# Create a logging config: console if TTY, else file (for --noconsole)\n"
                "_exe = getattr(sys, 'executable', None) or 'app'\n"
                "_log_cfg_path = Path(_exe).with_suffix('.logging.json')\n"
                "_log_file = Path(_exe).with_suffix('.log')\n"
                "_use_console = getattr(sys.stdout, 'isatty', lambda: False)()\n"
                "_handlers = {\n"
                "  'console': { 'class': 'logging.StreamHandler', 'stream': 'ext://sys.stdout', 'formatter': 'basic' },\n"
                "  'file': { 'class': 'logging.FileHandler', 'filename': str(_log_file), 'encoding': 'utf-8', 'formatter': 'basic' }\n"
                "}\n"
                "_sel = ['console'] if _use_console else ['file']\n"
                "_cfg = {\n"
                "  'version': 1,\n"
                "  'formatters': { 'basic': { '()': 'logging.Formatter', 'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s' } },\n"
                "  'handlers': _handlers,\n"
                "  'loggers': {\n"
                "    'uvicorn': { 'handlers': _sel, 'level': 'INFO', 'propagate': False },\n"
                "    'uvicorn.error': { 'handlers': _sel, 'level': 'INFO', 'propagate': False },\n"
                "    'uvicorn.access': { 'handlers': _sel, 'level': 'INFO', 'propagate': False }\n"
                "  },\n"
                "  'root': { 'handlers': _sel, 'level': 'INFO' }\n"
                "}\n"
                "try:\n"
                "  _log_cfg_path.write_text(json.dumps(_cfg), encoding='utf-8')\n"
                "except Exception:\n"
                "  pass\n"
                f"sys.argv = ['uvicorn', '--log-config', " + "str(_log_cfg_path)" + ("" if not uv_args else ", " + ", ".join(repr(a) for a in uv_args)) + "]\n"
                "_uv_main()\n"
            )
            try:
                wrapper_uv.write_text(code, encoding='utf-8')
                entry_for_build = str(wrapper_uv)
                await log_cb("debug", f"Using uvicorn CLI wrapper with args: {' '.join(uv_args)}")
            except Exception as e:
                await log_cb("warn", f"Failed to write uvicorn wrapper: {e}")
    except Exception as e:
        await log_cb("warn", f"uvicorn wrapper setup skipped: {e}")

    # If the entry lives in a subfolder, also install requirements from that folder if present
    try:
        entry_path = (workdir / entry).resolve()
    except Exception:
        entry_path = (workdir / entry)
    local_req = entry_path.parent / "requirements.txt"
    try:
        if offline and local_req.exists() and str(local_req) != str(req):
            # Verify local requirements in offline mode
            import re as _re
            def _parse_pkg(line: str) -> str:
                s = line.strip()
                s = s.split(';', 1)[0].split('#', 1)[0].strip()
                if not s or s.startswith(('-', 'git+', 'http:', 'https:')):
                    return ''
                m = _re.match(r"^[A-Za-z0-9_.-]+", s)
                return m.group(0) if m else ''
            missing = []
            try:
                for raw in local_req.read_text(encoding='utf-8', errors='ignore').splitlines():
                    name = _parse_pkg(raw)
                    if not name:
                        continue
                    rc = await _run_and_stream([str(py_bin), "-m", "pip", "show", name], env, workdir, lambda lvl, msg: None, timeout_seconds, cancel_event)
                    if rc != 0:
                        missing.append(name)
            except Exception:
                pass
            if missing:
                await log_cb('error', f"Offline build: missing local requirements: {', '.join(sorted(set(missing)))}. Install them system-wide or disable Offline build.")
                return []
        if not offline and local_req.exists() and str(local_req) != str(req):
            await log_cb("debug", f"Installing requirements from {local_req}")
            code = await _run_and_stream([str(py_bin), "-m", "pip", "install", "-r", str(local_req)], env, workdir, log_cb, timeout_seconds, cancel_event)
            if code != 0:
                return []
    except Exception as e:
        await log_cb("warn", f"Failed to process local requirements: {e}")

    # If entry is within a package (has __init__.py), run it as a module using a tiny wrapper
    module_name: Optional[str] = None
    try:
        rel_no_ext = entry_path.with_suffix('').relative_to(workdir)
        parts = list(rel_no_ext.parts)
        # Find highest package directory and ensure the chain has __init__.py
        top_idx = None
        for i in range(len(parts) - 1):  # exclude the file leaf in package chain detection
            pkg_dir = workdir.joinpath(*parts[: i + 1])
            if (pkg_dir / "__init__.py").exists():
                # verify that all dirs from i to leaf-1 are packages
                ok = True
                for j in range(i + 1, len(parts) - 1):
                    if not (workdir.joinpath(*parts[: j + 1]) / "__init__.py").exists():
                        ok = False
                        break
                if ok:
                    top_idx = i
                    break
        if top_idx is not None:
            module_name = ".".join(parts[top_idx:])  # include leaf module
    except Exception:
        module_name = None

    # Derive a clean app name (allow override from request.output_name)
    base_name = (getattr(request, 'output_name', None) or Path(project_name).stem)
    # strip extension and sanitize
    base_name = Path(base_name).stem.replace(' ', '_').replace('-', '_')
    if not base_name:
        base_name = Path(project_name).stem.replace(' ', '_').replace('-', '_')
    safe_name = base_name
    dist_dir = workdir / "dist"
    # Create a runtime hook to auto-load .env (from embedded bundle or next to the exe)
    hook_path = workdir / "forgex_env_auto.py"
    try:
        hook_code = (
            "try:\n"
            "    import os, sys, json\n"
            "    from pathlib import Path\n"
            "    DBG = os.environ.get('FGX_ENV_DEBUG') or ''\n"
            "    def _dbg(m):\n"
            "        if not DBG: return\n"
            "        try:\n"
            "            exe = getattr(sys, 'executable', 'app')\n"
            "            p = Path(exe).with_suffix('.envload.log')\n"
            "            with open(p, 'a', encoding='utf-8') as f: f.write(m); f.write(chr(10))\n"
            "        except Exception: pass\n"
            "    _dbg('[env_auto] start')\n"
            "    try:\n"
            "        from dotenv import load_dotenv as _ld\n"
            "    except Exception:\n"
            "        _ld = None\n"
            "    def _simple_load(path: Path):\n"
            "        cnt = 0\n"
            "        try:\n"
            "            for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():\n"
            "                s=line.strip()\n"
            "                if not s or s.startswith('#') or '=' not in s:\n"
            "                    continue\n"
            "                k,v=s.split('=',1)\n"
            "                k=k.strip(); v=v.strip()\n"
            "                # Trim surrounding quotes\n"
            "                if (v.startswith(\"'\") and v.endswith(\"'\")) or (v.startswith('\"') and v.endswith('\"')):\n"
            "                    v = v[1:-1]\n"
            "                if k and (k not in os.environ):\n"
            "                    os.environ[k]=v\n"
            "                    cnt += 1\n"
            "        except Exception:\n"
            "            pass\n"
            "        return cnt\n"
            "    candidates = []\n"
            "    names = ('.env', '.env.example', 'forgex.env', 'env', 'env.txt', 'config.env', 'dotenv', 'dotenv.txt')\n"
            "    if getattr(sys, 'frozen', False):\n"
            "        mp = getattr(sys, '_MEIPASS', '')\n"
            "        if mp:\n"
            "            for n in names: candidates.append(Path(mp) / n)\n"
            "        for n in names: candidates.append(Path(sys.executable).parent / n)\n"
            "    else:\n"
            "        for n in names: candidates.append(Path(__file__).parent / n)\n"
            "    _dbg('[env_auto] candidates: ' + ', '.join(str(p) for p in candidates))\n"
            "    loaded = False\n"
            "    for p in candidates:\n"
            "        try:\n"
            "            if p.exists():\n"
            "                if _ld:\n"
            "                    _dbg('[env_auto] load via python-dotenv: ' + str(p))\n"
            "                    _ld(p, override=False)\n"
            "                else:\n"
            "                    n = _simple_load(p)\n"
            "                    _dbg('[env_auto] load via fallback: ' + str(p) + ' (' + str(n) + ' keys)')\n"
            "                loaded = True\n"
            "                break\n"
            "        except Exception as e:\n"
            "            _dbg('[env_auto] error: ' + str(e))\n"
            "    if not loaded:\n"
            "        _dbg('[env_auto] no .env found')\n"
            "except Exception:\n"
            "    pass\n"
        )
        hook_path.write_text(hook_code, encoding='utf-8')
    except Exception:
        pass

    # Optional: force-enable env debug via a small hook (before loaders)
    env_verbose_hook = None
    try:
        if bool(getattr(request, 'env_verbose', False)):
            env_verbose_hook = workdir / "forgex_env_verbose_on.py"
            env_verbose_hook.write_text("import os\nos.environ.setdefault('FGX_ENV_DEBUG','1')\n", encoding='utf-8')
    except Exception:
        env_verbose_hook = None

    build_cmd = [
        str(py_bin), "-m", "PyInstaller", "--onefile", "--name", safe_name,
    ]
    if env_verbose_hook:
        build_cmd += ["--runtime-hook", str(env_verbose_hook)]
    build_cmd += ["--runtime-hook", str(hook_path)]
    # Append any deferred extras (e.g., hidden-imports) gathered earlier
    if pyi_extras:
        build_cmd += pyi_extras

    # Best-effort: auto-install common web frameworks if requirements.txt is missing
    auto_pkgs: List[str] = []
    if not (workdir / "requirements.txt").exists():
        try:
            sc = (getattr(request, 'start_command', '') or '').lower()
            if 'uvicorn' in sc:
                auto_pkgs.append('uvicorn')
            ep = workdir / entry
            code_txt = ep.read_text(encoding='utf-8', errors='ignore') if ep.exists() else ''
            low = code_txt.lower()
            if 'from fastapi' in low or 'import fastapi' in low:
                auto_pkgs.append('fastapi')
            if 'from flask' in low or 'import flask' in low:
                auto_pkgs.append('flask')
            if 'from django' in low or 'import django' in low:
                auto_pkgs.append('django')
            if auto_pkgs and not offline:
                # de-duplicate
                pkgs = sorted(set(auto_pkgs))
                await log_cb('info', f"Installing runtime packages: {', '.join(pkgs)} (this may take a while)...")
                code = await _run_and_stream([str(py_bin), '-m', 'pip', 'install', *pkgs], env, workdir, log_cb, timeout_seconds, cancel_event)
                if code != 0:
                    await log_cb('warn', 'Auto-install of detected packages failed; continuing')
            elif auto_pkgs and offline:
                await log_cb('info', 'Offline build: skipping auto-install of detected packages; ensure they are available system-wide')
        except Exception as e:
            await log_cb('warn', f'Auto-detect install step skipped: {e}')

    # Optional: pause 5 seconds on exit so users can read console output
    if getattr(request, 'pause_on_exit', False):
        pause_hook = workdir / "forgex_pause_on_exit.py"
        try:
            secs = getattr(request, 'pause_on_exit_seconds', None)
            try:
                secs = int(secs) if secs is not None else 5
            except Exception:
                secs = 5
            secs = max(1, min(120, secs))
            pause_hook_code = (
                "import atexit\n"
                "import time\n"
                f"atexit.register(time.sleep, {secs})\n"
            )
            pause_hook.write_text(pause_hook_code, encoding='utf-8')
            build_cmd += ["--runtime-hook", str(pause_hook)]
            await log_cb("debug", f"Enabled pause-on-exit ({secs}s) via runtime hook")
        except Exception:
            await log_cb("warn", "Failed to write pause-on-exit hook; proceeding without it")

    # Determine target OS for tweaks (no cross-compilation performed)
    target_os = getattr(request, 'target_os', 'windows')
    is_win_target = (str(target_os).lower() == 'windows')

    # Optional: Windows autostart at runtime (per-user) via Startup folder or Task Scheduler
    try:
        if is_win_target and getattr(request, 'win_autostart', False) and getattr(request, 'output_type', '') == 'exe':
            method = getattr(request, 'autostart_method', None) or 'task'
            # Prefer a friendly name if provided
            try:
                task_name = getattr(request, 'process_display_name', None) or 'Windows Host'
            except Exception:
                task_name = 'Windows Host'
            win_hook = workdir / "forgex_autostart_windows.py"
            win_hook_code = (
                "try:\n"
                "    import sys, subprocess, os, shutil\n"
                "    from pathlib import Path\n"
                "    if sys.platform.startswith('win'):\n"
                f"        _METHOD = {repr(method)}\n"
                f"        _NAME = {repr(task_name)}\n"
                "        exe = getattr(sys, 'executable', None) or sys.argv[0]\n"
                "        # Startup folder path (per-user)\n"
                "        appdata = os.environ.get('APPDATA', '')\n"
                "        startup = Path(appdata)/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup'\n"
                "        try:\n"
                "            if _METHOD == 'startup':\n"
                "                startup.mkdir(parents=True, exist_ok=True)\n"
                "                dest = startup / f'{_NAME}.exe'\n"
                "                if not dest.exists() or str(dest.resolve()) != str(Path(exe).resolve()):\n"
                "                    try:\n"
                "                        shutil.copy2(exe, dest)\n"
                "                    except Exception:\n"
                "                        # Fallback .bat launcher\n"
                "                        bat = startup / f'{_NAME}.bat'\n"
                "                        bat.write_text(f'@echo off\\r\\nstart \"\" \"{exe}\"\\r\\n', encoding='utf-8')\n"
                "            else:\n"
                "                # Task Scheduler (current user, limited rights)\n"
                "                # Check if task exists\n"
                "                r = subprocess.run(['schtasks', '/Query', '/TN', _NAME], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                "                if r.returncode != 0:\n"
                "                    cmd = ['schtasks', '/Create', '/TN', _NAME, '/SC', 'ONLOGON', '/TR', exe, '/RL', 'LIMITED', '/F']\n"
                "                    subprocess.run(cmd, check=False)\n"
                "        except Exception:\n"
                "            # Best-effort fallback to Run key\n"
                "            try:\n"
                "                import winreg\n"
                "                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_SET_VALUE)\n"
                "                winreg.SetValueEx(key, _NAME, 0, winreg.REG_SZ, exe)\n"
                "                winreg.CloseKey(key)\n"
                "            except Exception:\n"
                "                pass\n"
                "except Exception:\n"
                "    pass\n"
            )
            win_hook.write_text(win_hook_code, encoding='utf-8')
            build_cmd += ["--runtime-hook", str(win_hook)]
            await log_cb("debug", f"Enabled Windows autostart via runtime hook (method={method})")
    except Exception:
        await log_cb("warn", "Failed to enable Windows autostart")

    # Choose final entry for build
    if not entry_for_build:
        # If module_name detected, create a wrapper so relative imports (from .x import ...) work
        if module_name:
            await log_cb("debug", f"Using package module runner for {module_name}")
            wrapper = workdir / "forgex_pkg_entry.py"
            wrapper_code = (
                "# Auto-generated by ForgeX to run a package module as __main__\n"
                "import runpy\n"
                f"import {module_name} as _fgx_force_import\n"  # ensure PyInstaller collects the package
                f"runpy.run_module('{module_name}', run_name='__main__')\n"
            )
            try:
                wrapper.write_text(wrapper_code, encoding='utf-8')
                entry_for_build = str(wrapper)
            except Exception:
                entry_for_build = entry  # fallback
        else:
            entry_for_build = entry

    try:
        opts = getattr(request, 'pyinstaller', None) or {}
        prot = (opts.get('protect') or {}) if isinstance(opts, dict) else {}
    except Exception:
        prot = {}
    env_enc = (prot.get('encrypt_env') or {}) if isinstance(prot, dict) else {}

    if request.include_env:
        try:
            # Locate .env (prefer next to entry script, fallback to project root)
            env_file = None
            try:
                ep_parent = entry_path.parent
            except Exception:
                ep_parent = None
            if ep_parent and (ep_parent / '.env').exists():
                env_file = ep_parent / '.env'
            elif (workdir / '.env').exists():
                env_file = workdir / '.env'
            if env_file is None:
                try:
                    candidates = [p for p in workdir.rglob('.env') if p.is_file() and not _is_excluded_dir(p)]
                    if candidates:
                        env_file = candidates[0]
                except Exception:
                    pass
            # Also include .env.example if present (helpful for diagnostics)
            env_example = None
            try:
                if ep_parent and (ep_parent / '.env.example').exists():
                    env_example = ep_parent / '.env.example'
                elif (workdir / '.env.example').exists():
                    env_example = workdir / '.env.example'
                if env_example is None:
                    c2 = [p for p in workdir.rglob('.env.example') if p.is_file() and not _is_excluded_dir(p)]
                    if c2:
                        env_example = c2[0]
            except Exception:
                env_example = None
            if env_example:
                add_ex = f"{env_example}{';.' if os.name=='nt' else ':.'}"
                build_cmd += ['--add-data', add_ex]
                await log_cb('info', f"Bundled .env.example from {env_example}")
            # Fallback: non-dot env filenames (useful when upload strips dotfiles)
            if env_file is None:
                try:
                    FALLBACK_NAMES = ['forgex.env', 'env', 'env.txt', 'config.env', 'dotenv', 'dotenv.txt']
                    # Prefer entry folder
                    if ep_parent:
                        for n in FALLBACK_NAMES:
                            p = ep_parent / n
                            if p.exists() and p.is_file() and not _is_excluded_dir(p):
                                env_file = p
                                break
                    # Then project root
                    if env_file is None:
                        for n in FALLBACK_NAMES:
                            p = workdir / n
                            if p.exists() and p.is_file() and not _is_excluded_dir(p):
                                env_file = p
                                break
                    # Finally, recursive search (excluding heavy dirs)
                    if env_file is None:
                        for n in FALLBACK_NAMES:
                            cand = next((p for p in workdir.rglob(n) if p.is_file() and not _is_excluded_dir(p)), None)
                            if cand:
                                env_file = cand
                                break
                    if env_file:
                        await log_cb('info', f"Found fallback env file: {env_file}")
                except Exception:
                    pass
            if env_file:
                if bool(env_enc.get('enable')):
                    # Ensure cryptography is available
                    if not offline:
                        _ = await _run_and_stream([str(py_bin), '-m', 'pip', 'install', 'cryptography'], env, workdir, log_cb, timeout_seconds, cancel_event)
                    else:
                        await log_cb('info', 'Offline build: skipping cryptography install; if unavailable, .env encryption will be skipped')
                    # Prepare encryption helper
                    enc_script = workdir / 'forgex_env_encrypt.py'
                    enc_out = workdir / 'forgex.env.enc'
                    enc_script.write_text(
                        (
                            'import os, sys, json, base64, hashlib\n'
                            'from pathlib import Path\n'
                            'from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC\n'
                            'from cryptography.hazmat.primitives import hashes\n'
                            'from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n'
                            'def enc(passphrase: bytes, data: bytes) -> bytes:\n'
                            '    import os\n'
                            '    salt = os.urandom(16)\n'
                            '    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)\n'
                            '    key = kdf.derive(passphrase)\n'
                            '    aes = AESGCM(key)\n'
                            '    nonce = os.urandom(12)\n'
                            '    ct = aes.encrypt(nonce, data, b'')\n'
                            "    return b'FGXENV1' + salt + nonce + ct\n"
                            "pp = os.environ.get('FGX_BUILD_ENV_PASSPHRASE','').encode('utf-8')\n"
                            'if not pp:\n'
                            "    print('no_passphrase', file=sys.stderr); sys.exit(2)\n"
                            'inp = Path(sys.argv[1]).read_bytes()\n'
                            'out = enc(pp, inp)\n'
                            'Path(sys.argv[2]).write_bytes(out)\n'
                        ),
                        encoding='utf-8'
                    )
                    # Determine passphrase (inline for build or provided explicitly)
                    pp: Optional[str] = None
                    try:
                        mode = (env_enc.get('mode') or 'env')
                        if mode == 'inline':
                            pp = env_enc.get('passphrase') or ''
                        else:
                            # For encryption step at build time we still need a passphrase; fallback to inline if not provided
                            pp = env_enc.get('passphrase') or ''
                    except Exception:
                        pp = ''
                    if not pp:
                        # Generate a random dev key and switch runtime mode to inline implicitly
                        import secrets, base64 as _b64
                        pp = _b64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')
                        env_enc['mode'] = 'inline'
                        env_enc['passphrase'] = pp
                        await log_cb('warn', 'No passphrase provided for .env encryption; generated a random inline key (less secure).')
                    enc_env_vars = env.copy()
                    enc_env_vars['FGX_BUILD_ENV_PASSPHRASE'] = pp
                    code = await _run_and_stream([str(py_bin), str(enc_script), str(env_file), str(enc_out)], enc_env_vars, workdir, log_cb, timeout_seconds, cancel_event)
                    if code == 0 and enc_out.exists():
                        # Compute digest for integrity hook
                        import hashlib as _hl
                        try:
                            h = _hl.sha256(); h.update(enc_out.read_bytes()); expected_env_sha = h.hexdigest()
                        except Exception:
                            expected_env_sha = ''
                        # Write runtime decrypt hook
                        dec_hook = workdir / 'forgex_env_decrypt.py'
                        env_var_name = (env_enc.get('env_var') or 'FGX_ENV_KEY')
                        file_path = (env_enc.get('file_path') or '')
                        mode = (env_enc.get('mode') or 'env')
                        inline_pp = (env_enc.get('passphrase') or '') if mode == 'inline' else ''
                        # Seal the inline passphrase using the build venv (ensures cryptography is available)
                        _SEALED_PP_B64 = ''
                        _PEPPER_B64 = ''
                        try:
                            seal_script = workdir / 'forgex_pp_seal.py'
                            seal_script.write_text(
                                (
                                    'import os, sys, base64\n'
                                    'from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC\n'
                                    'from cryptography.hazmat.primitives import hashes\n'
                                    'from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n'
                                    "pp = (sys.argv[1] if len(sys.argv)>1 else '').encode('utf-8')\n"
                                    'pep = os.urandom(16)\n'
                                    'salt = os.urandom(16)\n'
                                    'nonce = os.urandom(12)\n'
                                    'kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)\n'
                                    'key = kdf.derive(pep)\n'
                                    "ct = AESGCM(key).encrypt(nonce, pp, b'FGXPP1')\n"
                                    "sealed = b'FGXPP1' + salt + nonce + ct\n"
                                    "print(base64.b64encode(sealed).decode('ascii'))\n"
                                    "print(base64.b64encode(pep).decode('ascii'))\n"
                                ),
                                encoding='utf-8'
                            )
                            proc = await asyncio.create_subprocess_exec(
                                str(py_bin), str(seal_script), inline_pp,
                                cwd=str(workdir), env=env,
                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                            )
                            out, err = await proc.communicate()
                            if proc.returncode == 0:
                                try:
                                    txt = out.decode('utf-8', errors='ignore').strip().splitlines()
                                    if len(txt) >= 2:
                                        _SEALED_PP_B64, _PEPPER_B64 = txt[0].strip(), txt[1].strip()
                                except Exception:
                                    pass
                        except Exception as _e:
                            await log_cb('warn', f'Inline passphrase sealing failed; falling back to plaintext inline: {_e}')
                            _SEALED_PP_B64 = ''
                            _PEPPER_B64 = ''
                        dec_hook.write_text(
                            (
                                "# Auto-generated by ForgeX: decrypt bundled .env at runtime (sealed inline + DPAPI cache)\n"
                                "import sys, os, json, base64, hashlib, ctypes, struct\n"
                                "from pathlib import Path\n"
                                "from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC\n"
                                "from cryptography.hazmat.primitives import hashes\n"
                                "from cryptography.hazmat.primitives.ciphers.aead import AESGCM\n"
                                "DBG = os.environ.get('FGX_ENV_DEBUG') or ''\n"
                                "def _dbg(m):\n"
                                "    if not DBG: return\n"
                                "    try:\n"
                                "        exe = getattr(sys, 'executable', sys.argv[0])\n"
                                "        p = Path(exe).with_suffix('.envload.log')\n"
                                "        with open(p, 'a', encoding='utf-8') as f: f.write(m + '\n')\n"
                                "    except Exception: pass\n"
                                f"_MODE = {repr(mode)}\n"
                                f"_ENV_VAR = {repr(env_var_name)}\n"
                                f"_FILE_PATH = {repr(file_path)}\n"
                                f"_SEALED_PP_B64 = {repr(_SEALED_PP_B64)}\n"
                                f"_PEPPER_B64 = {repr(_PEPPER_B64)}\n"
                                f"_EXPECTED_ENV_SHA256 = {repr(expected_env_sha)}\n"
                                f"_INLINE_PP_FB = {repr(inline_pp)}\n"
                                "_HDR = b'FGXPP1'\n"
                                "def _is_windows():\n"
                                "    return sys.platform.startswith('win')\n"
                                "def _exe_hash():\n"
                                "    try:\n"
                                "        p = Path(getattr(sys, 'executable', sys.argv[0]))\n"
                                "        h = hashlib.sha256(); h.update(p.read_bytes()); return h.hexdigest()\n"
                                "    except Exception:\n"
                                "        return ''\n"
                                "def _cache_key_name():\n"
                                "    h = _exe_hash()[:16] if _exe_hash() else 'default'\n"
                                "    return f'FGX_ENV_{h}'\n"
                                "def _dpapi_protect(data: bytes) -> bytes:\n"
                                "    if not _is_windows():\n"
                                "        return b''\n"
                                "    # DATA_BLOB struct\n"
                                "    class DATA_BLOB(ctypes.Structure):\n"
                                "        _fields_ = [('cbData', ctypes.c_uint), ('pbData', ctypes.POINTER(ctypes.c_byte))]\n"
                                "    CryptProtectData = ctypes.windll.crypt32.CryptProtectData\n"
                                "    LocalFree = ctypes.windll.kernel32.LocalFree\n"
                                "    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))\n"
                                "    out_blob = DATA_BLOB()\n"
                                "    if not CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob)):\n"
                                "        return b''\n"
                                "    try:\n"
                                "        res = ctypes.string_at(out_blob.pbData, out_blob.cbData)\n"
                                "        return res\n"
                                "    finally:\n"
                                "        LocalFree(out_blob.pbData)\n"
                                "def _dpapi_unprotect(data: bytes) -> bytes:\n"
                                "    if not _is_windows():\n"
                                "        return b''\n"
                                "    class DATA_BLOB(ctypes.Structure):\n"
                                "        _fields_ = [('cbData', ctypes.c_uint), ('pbData', ctypes.POINTER(ctypes.c_byte))]\n"
                                "    CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData\n"
                                "    LocalFree = ctypes.windll.kernel32.LocalFree\n"
                                "    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))\n"
                                "    out_blob = DATA_BLOB()\n"
                                "    if not CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob)):\n"
                                "        return b''\n"
                                "    try:\n"
                                "        res = ctypes.string_at(out_blob.pbData, out_blob.cbData)\n"
                                "        return res\n"
                                "    finally:\n"
                                "        LocalFree(out_blob.pbData)\n"
                                "def _cache_put(pp: bytes):\n"
                                "    if not (_is_windows() and pp):\n"
                                "        return\n"
                                "    try:\n"
                                "        import winreg\n"
                                "        data = _dpapi_protect(pp)\n"
                                "        if not data:\n"
                                "            return\n"
                                "        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\\ForgeX\\Cache') as k:\n"
                                "            winreg.SetValueEx(k, _cache_key_name(), 0, winreg.REG_BINARY, data)\n"
                                "    except Exception:\n"
                                "        pass\n"
                                "def _cache_get() -> bytes:\n"
                                "    if not _is_windows():\n"
                                "        return b''\n"
                                "    try:\n"
                                "        import winreg\n"
                                "        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\\ForgeX\\Cache') as k:\n"
                                "            data, _ = winreg.QueryValueEx(k, _cache_key_name())\n"
                                "            if isinstance(data, bytes) and data:\n"
                                "                return _dpapi_unprotect(data)\n"
                                "    except Exception:\n"
                                "        return b''\n"
                                "    return b''\n"
                                "def _sealed_inline_pp() -> bytes:\n"
                                "    try:\n"
                                "        if not _SEALED_PP_B64 or not _PEPPER_B64:\n"
                                "            return (_INLINE_PP_FB or '').encode('utf-8')\n"
                                "        raw = base64.b64decode(_SEALED_PP_B64)\n"
                                "        if not raw.startswith(_HDR):\n"
                                "            return b''\n"
                                "        salt = raw[len(_HDR):len(_HDR)+16]; nonce = raw[len(_HDR)+16:len(_HDR)+28]; ct = raw[len(_HDR)+28:]\n"
                                "        pepper = base64.b64decode(_PEPPER_B64)\n"
                                "        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)\n"
                                "        key = kdf.derive(pepper)\n"
                                "        aes = AESGCM(key)\n"
                                "        return aes.decrypt(nonce, ct, _HDR)\n"
                                "    except Exception:\n"
                                "        return b''\n"
                                "def _get_passphrase() -> bytes:\n"
                                "    # Try DPAPI cache first\n"
                                "    pp = _cache_get()\n"
                                "    if pp:\n"
                                "        return pp\n"
                                "    # Then resolve from configured mode\n"
                                "    if _MODE == 'env':\n"
                                "        v = os.environ.get(_ENV_VAR, '')\n"
                                "        pp = v.encode('utf-8')\n"
                                "    elif _MODE == 'file':\n"
                                "        try:\n"
                                "            p = Path(_FILE_PATH)\n"
                                "            pp = p.read_text(encoding='utf-8').strip().encode('utf-8')\n"
                                "        except Exception:\n"
                                "            pp = b''\n"
                                "    elif _MODE == 'inline':\n"
                                "        pp = _sealed_inline_pp()\n"
                                "    else:\n"
                                "        pp = b''\n"
                                "    if pp:\n"
                                "        _cache_put(pp)\n"
                                "    return pp\n"
                                "def _dec(passphrase: bytes, data: bytes) -> bytes:\n"
                                "    if not data.startswith(b'FGXENV1'):\n"
                                "        raise RuntimeError('invalid header')\n"
                                "    salt = data[7:23]; nonce = data[23:35]; ct = data[35:]\n"
                                "    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)\n"
                                "    key = kdf.derive(passphrase)\n"
                                "    aes = AESGCM(key)\n"
                                "    return aes.decrypt(nonce, ct, b'')\n"
                                "try:\n"
                                "    base = Path(getattr(sys, '_MEIPASS', '')) if getattr(sys, 'frozen', False) else Path(__file__).parent\n"
                                "    enc_p = base / 'forgex.env.enc'\n"
                                "    _dbg('[env_dec] enc path: ' + str(enc_p))\n"
                                "    if _EXPECTED_ENV_SHA256:\n"
                                "        try:\n"
                                "            h=hashlib.sha256(); h.update(enc_p.read_bytes());\n"
                                "            ok = (h.hexdigest() == _EXPECTED_ENV_SHA256)\n"
                                "            _dbg('[env_dec] digest match: ' + str(ok))\n"
                                "            if not ok:\n"
                                "                raise SystemExit(1)\n"
                                "        except Exception:\n"
                                "            raise SystemExit(1)\n"
                                "    raw = None\n"
                                "    pp = _cache_get()\n"
                                "    if pp:\n"
                                "        try:\n"
                                "            _dbg('[env_dec] using DPAPI cached key')\n"
                                "            raw = _dec(pp, enc_p.read_bytes())\n"
                                "        except Exception:\n"
                                "            _dbg('[env_dec] DPAPI cache decrypt failed; falling back')\n"
                                "            # DPAPI cache invalid; fall back to sealed-inline/env/file and refresh cache\n"
                                "            pp2 = b''\n"
                                "            if _MODE == 'env':\n"
                                "                v = os.environ.get(_ENV_VAR, '')\n"
                                "                pp2 = v.encode('utf-8')\n"
                                "            elif _MODE == 'file':\n"
                                "                try:\n"
                                "                    p = Path(_FILE_PATH)\n"
                                "                    pp2 = p.read_text(encoding='utf-8').strip().encode('utf-8')\n"
                                "                except Exception:\n"
                                "                    pp2 = b''\n"
                                "            elif _MODE == 'inline':\n"
                                "                pp2 = _sealed_inline_pp()\n"
                                "            if pp2:\n"
                                "                _cache_put(pp2)\n"
                                "                _dbg('[env_dec] refreshed cache from fallback source')\n"
                                "                raw = _dec(pp2, enc_p.read_bytes())\n"
                                "    if raw is None:\n"
                                "        # No cache or couldn't decrypt; resolve fresh and cache\n"
                                "        pp3 = b''\n"
                                "        if _MODE == 'env':\n"
                                "            v = os.environ.get(_ENV_VAR, '')\n"
                                "            pp3 = v.encode('utf-8')\n"
                                "        elif _MODE == 'file':\n"
                                "            try:\n"
                                "                p = Path(_FILE_PATH)\n"
                                "                pp3 = p.read_text(encoding='utf-8').strip().encode('utf-8')\n"
                                "            except Exception:\n"
                                "                pp3 = b''\n"
                                "        elif _MODE == 'inline':\n"
                                "            pp3 = _sealed_inline_pp()\n"
                                "        if not pp3:\n"
                                "            raise SystemExit(1)\n"
                                "        _cache_put(pp3)\n"
                                "        _dbg('[env_dec] loaded fresh key')\n"
                                "        raw = _dec(pp3, enc_p.read_bytes())\n"
                                "    # Load into environment without logging\n"
                                "    cnt=0\n"
                                "    for line in raw.decode('utf-8', errors='ignore').splitlines():\n"
                                "        if not line or line.strip().startswith('#') or '=' not in line:\n"
                                "            continue\n"
                                "        k, v = line.split('=', 1)\n"
                                "        if k and v is not None and (k not in os.environ):\n"
                                "            os.environ[k.strip()] = v.strip()\n"
                                "            cnt += 1\n"
                                "    _dbg('[env_dec] loaded ' + str(cnt) + ' keys')\n"
                                "    # Best-effort zeroization\n"
                                "    try:\n"
                                "        import ctypes\n"
                                "        ba = bytearray(raw)\n"
                                "        ctypes.memset(ctypes.addressof(ctypes.c_char.from_buffer(ba)), 0, len(ba))\n"
                                "    except Exception:\n"
                                "        pass\n"
                                "except SystemExit:\n"
                                "    raise\n"
                                "except Exception:\n"
                                "    # Do not crash the app; proceed without .env\n"
                                "    pass\n"
                            ),
                            encoding='utf-8'
                        )
                        build_cmd += ['--runtime-hook', str(dec_hook)]
                        # Add encrypted .env as data
                        add = f"{enc_out}{';.' if os.name=='nt' else ':.'}"
                        build_cmd += ['--add-data', add]
                        await log_cb('info', 'Included encrypted .env (forgex.env.enc) and decryption hook')
                    else:
                        await log_cb('warn', 'Failed to encrypt .env; including plaintext .env instead')
                        add = f"{env_file}{';.' if os.name=='nt' else ':.'}"
                        build_cmd += ['--add-data', add]
                        await log_cb('info', f"Bundled .env from {env_file}")
                else:
                    add = f"{env_file}{';.' if os.name=='nt' else ':.'}"
                    build_cmd += ['--add-data', add]
                    await log_cb('info', f"Bundled .env from {env_file}")
            else:
                await log_cb('warn', 'include_env=True but no .env found in project')
        except Exception as e:
            await log_cb('warn', f'.env handling failed: {e}')

    # Icon (prefer process_icon_path on Windows if provided)
    icon_source = None
    try:
        proc_icon = getattr(request, 'process_icon_path', None)
    except Exception:
        proc_icon = None
    if is_win_target and proc_icon:
        icon_source = Path(proc_icon)
    elif request.icon_path:
        icon_source = Path(request.icon_path)
    if icon_source and icon_source.exists():
        ext = icon_source.suffix.lower()
        if is_win_target and ext not in {'.ico', '.exe'}:
            # Try to auto-convert to .ico using Pillow
            await log_cb("info", f"Icon provided ({icon_source.name}); converting to .ico for Windows")
            if not 'PIL' in globals():
                if not offline:
                    _ = await _run_and_stream([str(py_bin), "-m", "pip", "install", "pillow"], env, workdir, log_cb, timeout_seconds, cancel_event)
                else:
                    await log_cb("info", "Offline build: skipping Pillow install; conversion may fail if Pillow is not installed")
            out_ico = workdir / "forgex_icon_converted.ico"
            conv_code = (
                "from PIL import Image; import sys; "
                "im=Image.open(sys.argv[1]); "
                "sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)]; "
                "im.save(sys.argv[2], sizes=sizes)"
            )
            code = await _run_and_stream([str(py_bin), "-c", conv_code, str(icon_source), str(out_ico)], env, workdir, log_cb, timeout_seconds, cancel_event)
            if code == 0 and out_ico.exists():
                build_cmd += ["--icon", str(out_ico)]
            else:
                await log_cb("warn", "Failed to convert icon to .ico; proceeding without custom icon")
        else:
            build_cmd += ["--icon", str(icon_source)]

    # Optional: Windows version resource (Task Manager display name)
    try:
        proc_name = getattr(request, 'process_display_name', None)
    except Exception:
        proc_name = None
    if is_win_target and proc_name and getattr(request, 'output_type', '') == 'exe':
        try:
            ver = workdir / "forgex_version_file.txt"
            # Use safe defaults; Task Manager typically shows FileDescription
            original = f"{safe_name}.exe"
            vf = (
                "# UTF-8\n"
                "VSVersionInfo(\n"
                "  ffi=FixedFileInfo(filevers=(1,0,0,0), prodvers=(1,0,0,0), mask=0x3f, flags=0x0, OS=0x4, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
                "  kids=[\n"
                "    StringFileInfo([\n"
                "      StringTable('040904B0', [\n"
                f"        StringStruct('CompanyName', ' '),\n"
                f"        StringStruct('FileDescription', {repr(proc_name)}),\n"
                f"        StringStruct('FileVersion', '1.0.0.0'),\n"
                f"        StringStruct('InternalName', {repr(proc_name)}),\n"
                f"        StringStruct('OriginalFilename', {repr(original)}),\n"
                f"        StringStruct('ProductName', {repr(proc_name)}),\n"
                f"        StringStruct('ProductVersion', '1.0.0.0'),\n"
                "      ])\n"
                "    ]),\n"
                "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
                "  ]\n"
                ")\n"
            )
            ver.write_text(vf, encoding='utf-8')
            build_cmd += ["--version-file", str(ver)]
            await log_cb('debug', f"Embedded version resource with FileDescription='{proc_name}'")
        except Exception as e:
            await log_cb('warn', f"Version resource generation failed: {e}")

    # Apply PyInstaller options
    opts = getattr(request, 'pyinstaller', None) or {}

    # Protection options (Python-only)
    prot = (opts.get('protect') or {}) if isinstance(opts, dict) else {}

    # Set -OO optimization to strip docstrings when protection enabled
    try:
        if bool(prot.get('enable')):
            env["PYTHONOPTIMIZE"] = "2"
    except Exception:
        pass

    # Obfuscation (best-effort): use PyInstaller archive key if requested and supported (< v6)
    try:
        if bool(prot.get('obfuscate', False)):
            version = "0.0"
            try:
                proc = await asyncio.create_subprocess_exec(
                    str(py_bin), "-c", "import PyInstaller, sys; print(getattr(PyInstaller,'__version__','0.0'))",
                    cwd=str(workdir), env=env,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                out, err = await proc.communicate()
                if proc.returncode == 0:
                    version = out.decode(errors='ignore').strip()
            except Exception:
                pass
            try:
                major = int((version.split('.') or ['0'])[0])
            except Exception:
                major = 0
            if major and major < 6:
                import secrets as _secrets
                key = _secrets.token_hex(16)
                build_cmd += ["--key", key]
                await log_cb('debug', f"Enabled PyInstaller archive key (--key) for v{version}")
            else:
                await log_cb('warn', f"PyInstaller v{version} does not support --key; skipping obfuscation")
    except Exception as e:
        await log_cb('warn', f"Obfuscation step skipped: {e}")

    # Privacy runtime masking (for logging module) if requested (either top-level or via protect.mask_logs)
    try:
        if bool(getattr(request, 'privacy_mask_logs', False) or prot.get('mask_logs', False)):
            mask_hook = workdir / "forgex_privacy_log_mask.py"
            mask_code = (
                "# Auto-generated by ForgeX: mask Python logging messages for privacy\n"
                "import logging, hashlib\n"
                "_old_factory = logging.getLogRecordFactory()\n"
                "def _fgx_mask_factory(*args, **kwargs):\n"
                "    rec = _old_factory(*args, **kwargs)\n"
                "    try:\n"
                "        msg = rec.getMessage()\n"
                "        h = hashlib.sha256(msg.encode('utf-8', errors='ignore')).hexdigest()[:12]\n"
                "        rec.msg = f'[masked:{h}]'\n"
                "        rec.args = ()\n"
                "    except Exception:\n"
                "        rec.msg = '[masked]'\n"
                "        rec.args = ()\n"
                "    return rec\n"
                "logging.setLogRecordFactory(_fgx_mask_factory)\n"
            )
            mask_hook.write_text(mask_code, encoding='utf-8')
            build_cmd += ["--runtime-hook", str(mask_hook)]
            await log_cb("debug", "Enabled privacy mask for runtime logs via runtime hook")
    except Exception as e:
        await log_cb("warn", f"Failed to enable privacy mask hook: {e}")

    # Anti-debug hook
    try:
        if bool(prot.get('anti_debug', False)):
            adb = workdir / "forgex_antidebug.py"
            adb.write_text(
                (
                    "import sys, os, ctypes\n"
                    "def _dbg():\n"
                    "    try:\n"
                    "        if sys.gettrace():\n"
                    "            return True\n"
                    "        if sys.platform.startswith('win'):\n"
                    "            try:\n"
                    "                return ctypes.windll.kernel32.IsDebuggerPresent() != 0\n"
                    "            except Exception:\n"
                    "                pass\n"
                    "    except Exception:\n"
                    "        return False\n"
                    "    return False\n"
                    "if _dbg():\n"
                    "    try:\n"
                    "        import time; time.sleep(0.1)\n"
                    "    except Exception: pass\n"
                    "    os._exit(1)\n"
                ),
                encoding='utf-8'
            )
            build_cmd += ["--runtime-hook", str(adb)]
            await log_cb('debug', 'Enabled anti-debug runtime hook')
    except Exception as e:
        await log_cb('warn', f'Anti-debug hook failed: {e}')

    # Integrity check (limited): ensure encrypted .env has expected digest if present, handled in decrypt hook
    try:
        if bool(prot.get('integrity_check', False)):
            # No additional action required; the decryption hook verifies the encrypted .env digest.
            pass
    except Exception:
        pass

    # noconsole
    if opts.get('noconsole'):
        build_cmd += ["--noconsole"]
    # add_data
    sep = ';' if is_win_target else ':'
    for item in (opts.get('add_data') or []):
        src = item.get('src'); dest = item.get('dest')
        if src and dest:
            build_cmd += ["--add-data", f"{src}{sep}{dest}"]
    # hidden imports
    for mod in (opts.get('hidden_imports') or []):
        build_cmd += ["--hidden-import", mod]
    # paths
    for p in (opts.get('paths') or []):
        build_cmd += ["--paths", p]
    # debug
    dbg = opts.get('debug')
    if dbg in {"all", "minimal", "noarchive"}:
        build_cmd += ["--debug", dbg]
    # noupx
    if opts.get('noupx'):
        build_cmd += ["--noupx"]
    # collect-all / collect-data
    for pkg in (opts.get('collect_all') or []):
        build_cmd += ["--collect-all", pkg]
    for pkg in (opts.get('collect_data') or []):
        build_cmd += ["--collect-data", pkg]
    # runtime hooks
    for hook in (opts.get('runtime_hooks') or []):
        hp = Path(hook)
        if not hp.is_absolute():
            hp = workdir / hp
        if hp.exists():
            build_cmd += ["--runtime-hook", str(hp)]
    # additional hooks dir
    for d in (opts.get('additional_hooks_dir') or []):
        dp = Path(d)
        if not dp.is_absolute():
            dp = workdir / dp
        if dp.exists():
            build_cmd += ["--additional-hooks-dir", str(dp)]

    # Legacy GUI hint via extra_files=gui
    if any(x.lower() == 'gui' for x in (request.extra_files or [])) and "--noconsole" not in build_cmd:
        build_cmd += ["--noconsole"]

    build_cmd += [entry_for_build]
    await log_cb("debug", f"PyInstaller cmd: {' '.join(shlex.quote(x) for x in build_cmd)}")
    await log_cb("info", "Running PyInstaller... (first run can be slow)")

    code = await _run_and_stream(build_cmd, env, workdir, log_cb, timeout_seconds, cancel_event)
    if code != 0:
        return []

    # Optional: code sign on Windows
    try:
        cs = getattr(request, 'code_sign', None)
        if is_win_target and cs and getattr(cs, 'enable', False) and getattr(cs, 'cert_path', None):
            sign_targets: List[Path] = []
            # Prefer named exe, fallback to any .exe in dist
            cand_named = (dist_dir / f"{safe_name}.exe")
            if cand_named.exists():
                sign_targets.append(cand_named)
            else:
                sign_targets.extend([p for p in dist_dir.glob('*.exe') if p.is_file()])
            if sign_targets:
                await log_cb('info', f"Signing {len(sign_targets)} artifact(s) with certificate")
                ts = getattr(cs, 'timestamp_url', None) or 'http://timestamp.digicert.com'
                desc = getattr(cs, 'description', None)
                pub = getattr(cs, 'publisher', None)  # Treated as description URL
                env_sign = env.copy()
                pwd = getattr(cs, 'cert_password', None)
                if pwd:
                    env_sign['SIGN_PWD'] = str(pwd)
                for target in sign_targets:
                    # Use cmd to expand %SIGN_PWD% so we don't log the secret
                    cmd_str = (
                        f"signtool sign /f \"{getattr(cs, 'cert_path', '')}\" " +
                        ("/p %SIGN_PWD% " if pwd else "") +
                        "/fd SHA256 /td SHA256 " +
                        (f"/tr \"{ts}\" " if ts else "") +
                        (f"/d \"{desc}\" " if desc else "") +
                        (f"/du \"{pub}\" " if pub else "") +
                        f"\"{str(target)}\""
                    )
                    await log_cb('debug', f"Running code-sign: {cmd_str.replace('%SIGN_PWD%', '****')}")
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            'cmd.exe', '/C', cmd_str,
                            cwd=str(workdir), env=env_sign,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                        )
                        out, err = await proc.communicate()
                        if proc.returncode != 0:
                            await log_cb('warn', f"Code-sign failed ({proc.returncode}): {err.decode(errors='ignore').strip()}")
                        else:
                            await log_cb('info', f"Signed: {target}")
                    except FileNotFoundError:
                        await log_cb('warn', "signtool not found; skipping code-signing")
                        break
    except Exception as e:
        await log_cb('warn', f"Code-sign step skipped: {e}")

    # Collect artifact
    artifacts: List[str] = []
    ext_map = {'windows': '.exe', 'linux': '', 'macos': ''}
    ext = ext_map.get(str(target_os).lower(), '')
    cand = dist_dir / f"{safe_name}{ext}"
    if cand.exists():
        artifacts.append(str(cand))
    else:
        # Fallback: first file in dist
        for p in dist_dir.glob("*"):
            if p.is_file():
                artifacts.append(str(p))

    # Optional: generate Windows helper scripts next to the EXE
    try:
        if is_win_target and getattr(request, 'win_smartscreen_helper', False) and getattr(request, 'output_type', '') == 'exe':
            exe_path: Optional[Path] = None
            pref = dist_dir / f"{safe_name}.exe"
            if pref.exists():
                exe_path = pref
            else:
                exes = [p for p in dist_dir.glob('*.exe') if p.is_file()]
                if exes:
                    exe_path = exes[0]
            if exe_path and exe_path.exists():
                ps1 = dist_dir / f"Run-{exe_path.stem}.ps1"
                cmd = dist_dir / f"Run-{exe_path.stem}.cmd"
                ps_code = (
                    "$ErrorActionPreference = 'Stop'\n"
                    f"$exe = Join-Path $PSScriptRoot '{exe_path.name}'\n"
                    "try { Unblock-File -Path $exe -ErrorAction SilentlyContinue } catch {}\n"
                    "Push-Location $PSScriptRoot\n"
                    "& $exe\n"
                    "$code = $LASTEXITCODE\n"
                    "Pop-Location\n"
                    "exit $code\n"
                )
                # CMD wrapper variants: with or without logging
                if bool(getattr(request, 'win_helper_log', False)):
                    # Determine log filename (defaults to script base name)
                    log_set = "set LOG=%~dp0%~n0.log\r\n"
                    try:
                        lf = getattr(request, 'win_helper_log_name', None)
                        if lf:
                            # Use a specific name relative to script dir
                            log_set = f"set LOG=%~dp0{lf}\r\n"
                    except Exception:
                        pass
                    cmd_code = (
                        "@echo off\r\n"
                        "setlocal\r\n"
                        "set SCRIPT=%~dp0%~n0.ps1\r\n"
                        f"{log_set}"
                        "echo [%DATE% %TIME%] Launching >> \"%LOG%\"\r\n"
                        "powershell -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT%\" >> \"%LOG%\" 2>&1\r\n"
                        "set RC=%ERRORLEVEL%\r\n"
                        "echo [%DATE% %TIME%] Exit %RC% >> \"%LOG%\"\r\n"
                        "exit /b %RC%\r\n"
                    )
                else:
                    cmd_code = (
                        "@echo off\r\n"
                        "setlocal\r\n"
                        "set SCRIPT=%~dp0%~n0.ps1\r\n"
                        "powershell -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT%\"\r\n"
                        "set RC=%ERRORLEVEL%\r\n"
                        "if not \"%RC%\"==\"0\" (\r\n"
                        "  echo Error launching app (code %RC%).\r\n"
                        "  timeout /t 8 /nobreak >nul\r\n"
                        ")\r\n"
                        "if \"%RC%\"==\"0\" (\r\n"
                        "  timeout /t 8 /nobreak >nul\r\n"
                        ")\r\n"
                    )
                # Optional extra delay if pause_on_exit configured
                try:
                    if getattr(request, 'pause_on_exit', False):
                        secs = getattr(request, 'pause_on_exit_seconds', None)
                        try:
                            secs = int(secs) if secs is not None else 5
                        except Exception:
                            secs = 5
                        secs = max(1, min(120, secs))
                        cmd_code += f"timeout /t {secs} /nobreak >nul\r\n"
                except Exception:
                    pass
                try:
                    ps1.write_text(ps_code, encoding='utf-8')
                    cmd.write_text(cmd_code, encoding='utf-8')
                    artifacts.append(str(ps1))
                    artifacts.append(str(cmd))
                    await log_cb('info', f"Added Windows helper scripts: {ps1.name}, {cmd.name}")
                except Exception as e:
                    await log_cb('warn', f"Failed to write helper scripts: {e}")
    except Exception as e:
        await log_cb('warn', f"Helper script step skipped: {e}")

    await log_cb("debug", f"Artifacts: {artifacts}")
    return artifacts

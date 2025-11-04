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
    await log_cb("debug", f"Creating venv in {workdir / '.venv'}")
    venv_dir, py_bin, pip_bin = await ensure_venv_async(workdir)
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["PATH"] = f"{venv_dir / ('Scripts' if os.name=='nt' else 'bin')}{os.pathsep}" + env.get("PATH", "")
    # Defer extra PyInstaller args here so early phases can append before build_cmd exists
    pyi_extras: List[str] = []

    # Install deps if requirements.txt exists
    req = workdir / "requirements.txt"
    if req.exists():
        await log_cb("debug", f"Installing requirements from {req}")
        code = await _run_and_stream([str(pip_bin), "install", "-r", str(req)], env, workdir, log_cb, timeout_seconds, cancel_event)
        if code != 0:
            return []
    # Ensure pyinstaller available
    await log_cb("info", "Installing PyInstaller (this may take a few minutes)...")
    code = await _run_and_stream([str(pip_bin), "install", "pyinstaller"], env, workdir, log_cb, timeout_seconds, cancel_event)
    if code != 0:
        return []

    # Best-effort ensure python-dotenv so the runtime hook can load .env automatically
    await log_cb("debug", "Ensuring python-dotenv is installed (optional)")
    _ = await _run_and_stream([str(pip_bin), "install", "python-dotenv"], env, workdir, log_cb, timeout_seconds, cancel_event)

    # Determine entry
    entry: Optional[str] = _parse_entry_from_start(request.start_command)
    EXCLUDED_DIRS = {'.venv', 'venv', 'env', 'node_modules', 'dist', 'build', '__pycache__', '.git'}
    def _is_excluded(path: Path) -> bool:
        return any(part in EXCLUDED_DIRS for part in path.parts)

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
                "# Create a simple file-based logging config to avoid TTY checks when --noconsole\n"
                "_exe = getattr(sys, 'executable', None) or 'app'\n"
                "_log_cfg_path = Path(_exe).with_suffix('.logging.json')\n"
                "_log_file = Path(_exe).with_suffix('.log')\n"
                "_cfg = {\n"
                "  'version': 1,\n"
                "  'formatters': { 'basic': { '()': 'logging.Formatter', 'format': '%(asctime)s %(levelname)s [%(name)s] %(message)s' } },\n"
                "  'handlers': { 'file': { 'class': 'logging.FileHandler', 'filename': str(_log_file), 'encoding': 'utf-8', 'formatter': 'basic' } },\n"
                "  'loggers': {\n"
                "    'uvicorn': { 'handlers': ['file'], 'level': 'INFO', 'propagate': False },\n"
                "    'uvicorn.error': { 'handlers': ['file'], 'level': 'INFO', 'propagate': False },\n"
                "    'uvicorn.access': { 'handlers': ['file'], 'level': 'WARNING', 'propagate': False }\n"
                "  },\n"
                "  'root': { 'handlers': ['file'], 'level': 'INFO' }\n"
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
        if local_req.exists() and str(local_req) != str(req):
            await log_cb("debug", f"Installing requirements from {local_req}")
            code = await _run_and_stream([str(pip_bin), "install", "-r", str(local_req)], env, workdir, log_cb, timeout_seconds, cancel_event)
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
            "    import sys\n"
            "    from pathlib import Path\n"
            "    try:\n"
            "        from dotenv import load_dotenv\n"
            "    except Exception:\n"
            "        load_dotenv = None\n"
            "    if load_dotenv:\n"
            "        candidates = []\n"
            "        if getattr(sys, 'frozen', False):\n"
            "            mp = getattr(sys, '_MEIPASS', '')\n"
            "            if mp:\n"
            "                candidates.append(Path(mp) / '.env')\n"
            "            candidates.append(Path(sys.executable).parent / '.env')\n"
            "        else:\n"
            "            candidates.append(Path(__file__).parent / '.env')\n"
            "        for p in candidates:\n"
            "            try:\n"
            "                if p.exists():\n"
            "                    load_dotenv(p, override=False)\n"
            "                    break\n"
            "            except Exception:\n"
            "                pass\n"
            "except Exception:\n"
            "    pass\n"
        )
        hook_path.write_text(hook_code, encoding='utf-8')
    except Exception:
        pass

    build_cmd = [
        str(py_bin), "-m", "PyInstaller", "--onefile", "--name", safe_name,
        "--runtime-hook", str(hook_path),
    ]
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
            if auto_pkgs:
                # de-duplicate
                pkgs = sorted(set(auto_pkgs))
                await log_cb('info', f"Installing runtime packages: {', '.join(pkgs)} (this may take a while)...")
                code = await _run_and_stream([str(pip_bin), 'install', *pkgs], env, workdir, log_cb, timeout_seconds, cancel_event)
                if code != 0:
                    await log_cb('warn', 'Auto-install of detected packages failed; continuing')
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

    # Optional: Windows autostart via Scheduled Task (fallback to Run key)
    try:
        if is_win_target and getattr(request, 'win_autostart', False) and getattr(request, 'output_type', '') == 'exe':
            win_hook = workdir / "forgex_autostart_windows.py"
            win_hook_code = (
                "try:\n"
                "    import sys, subprocess, os\n"
                "    if sys.platform.startswith('win'):\n"
                "        name = 'Windows Host'\n"
                "        exists = False\n"
                "        try:\n"
                "            r = subprocess.run(['schtasks', '/Query', '/TN', name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)\n"
                "            exists = (r.returncode == 0)\n"
                "        except Exception:\n"
                "            exists = False\n"
                "        if not exists:\n"
                "            tr = f'\"{sys.executable}\"'\n"
                "            cmd = ['schtasks', '/Create', '/TN', name, '/SC', 'ONLOGON', '/TR', tr, '/RL', 'LIMITED', '/F']\n"
                "            try:\n"
                "                subprocess.run(' '.join(cmd), shell=True)\n"
                "            except Exception:\n"
                "                try:\n"
                "                    import winreg\n"
                "                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_SET_VALUE)\n"
                "                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, sys.executable)\n"
                "                    winreg.CloseKey(key)\n"
                "                except Exception:\n"
                "                    pass\n"
                "except Exception:\n"
                "    pass\n"
            )
            win_hook.write_text(win_hook_code, encoding='utf-8')
            build_cmd += ["--runtime-hook", str(win_hook)]
            await log_cb("debug", "Enabled Windows autostart via runtime hook")
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

    # Determine target OS for tweaks (no cross-compilation performed)
    target_os = getattr(request, 'target_os', 'windows')
    is_win_target = (str(target_os).lower() == 'windows')

    # Include .env if requested
    if request.include_env and (workdir / ".env").exists():
        env_file = workdir / ".env"
        add = f"{env_file}{';.' if os.name=='nt' else ':.'}"
        build_cmd += ["--add-data", add]

    # Icon
    if request.icon_path:
        icon_path = Path(request.icon_path)
        if icon_path.exists():
            ext = icon_path.suffix.lower()
            if is_win_target and ext not in {'.ico', '.exe'}:
                # Try to auto-convert to .ico using Pillow inside the build venv
                await log_cb("info", f"Icon provided ({icon_path.name}); converting to .ico for Windows")
                # Ensure pillow is available in the venv
                _ = await _run_and_stream([str(pip_bin), "install", "pillow"], env, workdir, log_cb, timeout_seconds, cancel_event)
                out_ico = workdir / "forgex_icon_converted.ico"
                conv_code = (
                    "from PIL import Image; import sys; "
                    "im=Image.open(sys.argv[1]); "
                    "sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)]; "
                    "im.save(sys.argv[2], sizes=sizes)"
                )
                code = await _run_and_stream([str(py_bin), "-c", conv_code, str(icon_path), str(out_ico)], env, workdir, log_cb, timeout_seconds, cancel_event)
                if code == 0 and out_ico.exists():
                    build_cmd += ["--icon", str(out_ico)]
                else:
                    await log_cb("warn", "Failed to convert icon to .ico; proceeding without custom icon")
            else:
                build_cmd += ["--icon", str(icon_path)]

    # Apply PyInstaller options
    opts = getattr(request, 'pyinstaller', None) or {}

    # Privacy runtime masking (for logging module) if requested
    try:
        if bool(getattr(request, 'privacy_mask_logs', False)):
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

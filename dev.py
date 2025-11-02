#!/usr/bin/env python3
import os
import sys
import threading
import subprocess
import time
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT / "frontend"
BACKEND_DIR = ROOT / "backend"


def parse_env_file(p: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not p.exists():
        return env
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env


def stream_output(proc: subprocess.Popen, prefix: str):
    def reader(stream, is_err=False):
        for line in iter(stream.readline, ''):
            if not line:
                break
            print(f"[{prefix}] {line.rstrip()}")
        try:
            stream.close()
        except Exception:
            pass

    t1 = threading.Thread(target=reader, args=(proc.stdout, False), daemon=False)
    t2 = threading.Thread(target=reader, args=(proc.stderr, True), daemon=False)
    t1.start(); t2.start()
    return t1, t2


def run_backend(port: str) -> Tuple[subprocess.Popen, threading.Thread, threading.Thread]:
    env = os.environ.copy()
    env.setdefault('FORGEX_BACKEND_PORT', port)
    env.update(parse_env_file(BACKEND_DIR / '.env'))

    # Add the project root to PYTHONPATH so that 'forgex' module can be found
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{ROOT}{os.pathsep}{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = str(ROOT)

    cmd = [sys.executable or 'python', '-m', 'uvicorn', 'backend.main:app', '--host', os.getenv('FORGEX_BACKEND_HOST', '127.0.0.1'), '--port', port]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    t1, t2 = stream_output(proc, 'backend')
    return proc, t1, t2


def run_frontend(port: str) -> Tuple[subprocess.Popen, threading.Thread, threading.Thread]:
    env = os.environ.copy()
    env.setdefault('VITE_BACKEND_PORT', port)
    env.setdefault('VITE_BACKEND_URL', f'http://127.0.0.1:{port}')
    env.setdefault('VITE_BACKEND_WS', f'ws://127.0.0.1:{port}')
    fe_env = parse_env_file(FRONTEND_DIR / '.env')
    for k, v in fe_env.items():
        env.setdefault(k, v)

    npm_cmd = 'npm.cmd' if os.name == 'nt' else 'npm'
    cmd = [npm_cmd, 'run', 'dev']
    proc = subprocess.Popen(
        cmd,
        cwd=str(FRONTEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    t1, t2 = stream_output(proc, 'frontend')
    return proc, t1, t2


def main():
    defaults = parse_env_file(BACKEND_DIR / '.env')
    port = os.getenv('FORGEX_BACKEND_PORT') or defaults.get('FORGEX_BACKEND_PORT') or '45555'

    print(f"Starting backend on 127.0.0.1:{port} and frontend (Vite) ...")
    be_proc, be_t1, be_t2 = run_backend(port)
    time.sleep(1.0)
    fe_proc, fe_t1, fe_t2 = run_frontend(port)

    all_procs = [be_proc, fe_proc]
    all_threads = [be_t1, be_t2, fe_t1, fe_t2]

    try:
        while True:
            time.sleep(0.5)
            be_rc = be_proc.poll()
            fe_rc = fe_proc.poll()
            if be_rc is not None:
                print(f"[orchestrator] Backend exited with code {be_rc}; stopping frontend...")
                break
            if fe_rc is not None:
                print(f"[orchestrator] Frontend exited with code {fe_rc}; stopping backend...")
                break
    except KeyboardInterrupt:
        print("\n[orchestrator] Ctrl+C received; shutting down...")
    finally:
        for proc in all_procs:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass
        for t in all_threads:
            if t.is_alive():
                t.join(timeout=5)  # Give threads a chance to finish
        print("[orchestrator] Stopped.")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
import os
import sys
import threading
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
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
            tag = 'stderr' if is_err else 'stdout'
            print(f"[{prefix}] {line.rstrip()}")
        try:
            stream.close()
        except Exception:
            pass

    t1 = threading.Thread(target=reader, args=(proc.stdout, False), daemon=True)
    t2 = threading.Thread(target=reader, args=(proc.stderr, True), daemon=True)
    t1.start(); t2.start()
    return t1, t2


def run_backend(port: str) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault('FORGEX_BACKEND_PORT', port)
    # Optional other backend envs from backend/.env
    env.update(parse_env_file(BACKEND_DIR / '.env'))

    cmd = [sys.executable or 'python', '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', port]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stream_output(proc, 'backend')
    return proc


def run_frontend(port: str) -> subprocess.Popen:
    env = os.environ.copy()
    # Provide backend URL/WS to the Vite app
    env.setdefault('VITE_BACKEND_PORT', port)
    env.setdefault('VITE_BACKEND_URL', f'http://127.0.0.1:{port}')
    env.setdefault('VITE_BACKEND_WS', f'ws://127.0.0.1:{port}')
    # Load additional from frontend/.env (without overriding setdefault)
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
    stream_output(proc, 'frontend')
    return proc


def main():
    # Prefer explicit port from env or backend .env
    defaults = parse_env_file(BACKEND_DIR / '.env')
    port = os.getenv('FORGEX_BACKEND_PORT') or defaults.get('FORGEX_BACKEND_PORT') or '45555'

    print(f"Starting backend on 127.0.0.1:{port} and frontend (Vite) ...")
    be = run_backend(port)
    # Give backend a moment to bind
    time.sleep(1.0)
    fe = run_frontend(port)

    try:
        # Wait for either process to exit
        while True:
            time.sleep(0.5)
            be_rc = be.poll()
            fe_rc = fe.poll()
            if be_rc is not None:
                print(f"[orchestrator] Backend exited with code {be_rc}; stopping frontend...")
                break
            if fe_rc is not None:
                print(f"[orchestrator] Frontend exited with code {fe_rc}; stopping backend...")
                break
    except KeyboardInterrupt:
        print("\n[orchestrator] Ctrl+C received; shutting down...")
    finally:
        for proc, name in [(fe, 'frontend'), (be, 'backend')]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    # Grace period
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    pass
        print("[orchestrator] Stopped.")


if __name__ == '__main__':
    main()

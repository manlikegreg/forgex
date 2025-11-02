import os
import sys
import tempfile
import shutil
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from .fs_utils import ensure_dir


class Sandbox:
    def __init__(self, build_id: str):
        base = Path.home() / ".forgex" / "tmp"
        ensure_dir(str(base))
        self.root = Path(tempfile.mkdtemp(prefix=f"{build_id}_", dir=base))

    def path(self, *parts: str) -> Path:
        return self.root.joinpath(*parts)

    def cleanup(self):
        try:
            shutil.rmtree(self.root, ignore_errors=True)
        except Exception:
            pass


def create_venv(workdir: Path) -> Tuple[Path, Path, Path]:
    """Create a Python venv inside workdir and return (venv_dir, python, pip)."""
    venv_dir = workdir / ".venv"
    if not venv_dir.exists():
        import venv
        venv.EnvBuilder(with_pip=True).create(str(venv_dir))
    if os.name == 'nt':
        python = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        python = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
    return venv_dir, python, pip


async def ensure_venv_async(workdir: Path) -> Tuple[Path, Path, Path]:
    """Async variant that avoids blocking the event loop."""
    venv_dir = workdir / ".venv"
    if not venv_dir.exists():
        import venv
        await asyncio.to_thread(venv.EnvBuilder(with_pip=True).create, str(venv_dir))
    # Reuse create_venv path resolution
    return create_venv(workdir)

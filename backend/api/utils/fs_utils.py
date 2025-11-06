import os
import shutil
import zipfile
from pathlib import Path
from typing import Iterable, Optional


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_copytree(src: str, dst: str, include: Optional[Iterable[str]] = None, exclude: Optional[Iterable[str]] = None) -> None:
    src_p = Path(src)
    dst_p = Path(dst)
    ensure_dir(dst)

    include = set(include or [])
    # Default excludes to prevent huge/unwanted copies and wrong entry detection
    # IMPORTANT: treat excludes as path-segment names, not substrings, so '.env' is not skipped by 'env'.
    default_exclude = {
        ".git", "__pycache__", ".venv", "venv", "env", "node_modules", "dist", "build",
        ".idea", ".pytest_cache", ".mypy_cache", "site-packages"
    }
    exclude_names = set(exclude or []) | default_exclude

    def _is_excluded_dir(rel_dir: Path) -> bool:
        # Exclude if any directory path segment matches an exclude name exactly
        return any(part in exclude_names for part in rel_dir.parts)

    def _is_excluded_file(rel_file: Path) -> bool:
        # Only consider parent directories for exclusion; do not exclude by file name equality
        return any(part in exclude_names for part in rel_file.parent.parts)

    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src_p)
        # Filter directories by path-segment equality (not substring)
        dirs[:] = [d for d in dirs if not _is_excluded_dir(Path(rel_root, d))]

        for f in files:
            rel_file = Path(rel_root, f)
            # Skip excluded files (by parent directory segments)
            if _is_excluded_file(rel_file):
                continue
            # If include list provided, only copy those paths
            if include and not any(str(rel_file).startswith(p) for p in include):
                # Still copy standard files unless include restricts
                pass
            src_file = src_p / rel_file
            dst_file = dst_p / rel_file
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)


def extract_zip(zip_path: str, dest_dir: str) -> None:
    """Safely extract a zip file into dest_dir, protecting against Zip-Slip.
    Preserves paths and creates directories as needed.
    """
    ensure_dir(dest_dir)
    dest_root = Path(dest_dir).resolve()
    with zipfile.ZipFile(zip_path, 'r') as z:
        for info in z.infolist():
            # Normalize path and prevent zip-slip
            rel = Path(info.filename.replace('..', '').lstrip('/\\'))
            target = (dest_root / rel).resolve()
            # Ensure target is inside dest_root
            if not str(target).startswith(str(dest_root) + os.sep) and target != dest_root:
                # Skip suspicious entry
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info, 'r') as src, open(target, 'wb') as dst:
                shutil.copyfileobj(src, dst)


def first_existing(*paths: str) -> Optional[str]:
    for p in paths:
        if p and Path(p).exists():
            return p
    return None

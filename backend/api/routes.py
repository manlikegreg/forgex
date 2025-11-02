from __future__ import annotations
from typing import Dict, List, Optional
import json
import logging
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

from backend.api.models.build_models import BuildRequest
from backend.api.build_runner import build_controller
from backend.services import db
from backend.api.utils.fs_utils import ensure_dir, extract_zip

log = logging.getLogger("forgex.api")
router = APIRouter()


@router.post("/upload")
async def upload(
    files: Optional[List[UploadFile]] = File(default=None),
    files_alt: Optional[List[UploadFile]] = File(default=None, alias='files[]'),
    zip: Optional[UploadFile] = File(default=None)
):
    """Accept a zip (preferred) or a set of files (preserving relative paths) and stage them into a temp project folder."""
    import uuid
    from pathlib import Path as _P

    base = _P.home() / ".forgex" / "uploads"
    ensure_dir(str(base))

    if zip is not None:
        temp_zip = base / f"upload_{uuid.uuid4()}.zip"
        with temp_zip.open('wb') as f:
            # Stream to avoid loading entire file in memory
            while True:
                chunk = await zip.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        extract_dir = base / f"extracted_{uuid.uuid4()}"
        extract_zip(str(temp_zip), str(extract_dir))
        log.info(f"upload zip -> {extract_dir}")
        return {"project_path": str(extract_dir)}

    # Support both 'files' and 'files[]' field names
    file_list: List[UploadFile] = files or files_alt or []

    if file_list:
        # If it's a single .zip uploaded under 'files', treat like zip path
        if len(file_list) == 1 and (file_list[0].filename or '').lower().endswith('.zip'):
            temp_zip = base / f"upload_{uuid.uuid4()}.zip"
            with temp_zip.open('wb') as f:
                while True:
                    chunk = await file_list[0].read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            extract_dir = base / f"extracted_{uuid.uuid4()}"
            extract_zip(str(temp_zip), str(extract_dir))
            log.info(f"upload files(single-zip) -> {extract_dir}")
            return {"project_path": str(extract_dir)}

        out_dir = base / f"files_{uuid.uuid4()}"
        ensure_dir(str(out_dir))

        def _sanitize_rel_path(name: str) -> Path:
            # Normalize slashes and remove any .. or empty segments
            parts = []
            for seg in str(PurePosixPath(name.replace('\\\\', '/').replace('\\', '/'))).split('/'):
                if not seg or seg == '.' or seg == '..':
                    continue
                # basic hardening against weird names
                seg = seg.replace('\x00', '')
                parts.append(seg)
            rel = Path(*parts)
            # strip any leading absolute components (defense in depth)
            while rel.is_absolute():
                rel = Path(*rel.parts[1:])
            return rel

        for uf in file_list:
            name = uf.filename or ""
            rel = _sanitize_rel_path(name)
            target = out_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            # Stream write to disk to save memory
            with target.open('wb') as f:
                while True:
                    chunk = await uf.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
        log.info(f"upload files -> {out_dir}")
        return {"project_path": str(out_dir)}

    return {"error": "no_files"}


@router.post("/start-build")
async def start_build(req: BuildRequest):
    log.info(f"start-build: lang={req.language} out={req.output_type} wd={req.working_dir} icon={bool(req.icon_path)}")
    build_id = await build_controller.start(req)
    log.info(f"start-build queued id={build_id}")
    return {"build_id": build_id, "status": "queued"}


@router.post("/cancel-build")
async def cancel_build(payload: Dict[str, str]):
    build_id = payload.get("build_id")
    log.info(f"cancel-build id={build_id}")
    ok = await build_controller.cancel(build_id)
    return {"ok": ok}


@router.get("/build-status/{build_id}")
async def build_status(build_id: str):
    row = db.get_build(build_id)
    if not row:
        return {"error": "not_found"}
    # Convert include_env to bool if present
    include_env_val = row.get("include_env")
    include_env = bool(int(include_env_val)) if isinstance(include_env_val, (int, str)) and str(include_env_val).isdigit() else bool(include_env_val)
    resp = {
        "build_id": row["build_id"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "output_files": json.loads(row["output_files"]) if row["output_files"] else [],
        "error": row["error"],
        "language": row.get("language"),
        "start_command": row.get("start_command"),
        "working_dir": row.get("working_dir"),
        "output_type": row.get("output_type"),
        "include_env": include_env,
        "output_name": row.get("output_name"),
    }
    log.debug(f"build-status id={build_id} status={resp['status']} files={len(resp['output_files'])}")
    return resp


@router.get("/build-history")
async def build_history(limit: int = 50, offset: int = 0):
    rows = db.list_builds(limit=limit, offset=offset)
    out = []
    for r in rows:
        include_env_val = r.get("include_env")
        include_env = bool(int(include_env_val)) if isinstance(include_env_val, (int, str)) and str(include_env_val).isdigit() else bool(include_env_val)
        out.append({
            "build_id": r["build_id"],
            "status": r["status"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
            "output_files": json.loads(r["output_files"]) if r["output_files"] else [],
            "error": r["error"],
            "language": r.get("language"),
            "start_command": r.get("start_command"),
            "working_dir": r.get("working_dir"),
            "output_type": r.get("output_type"),
            "include_env": include_env,
            "output_name": r.get("output_name"),
        })
    log.debug(f"build-history count={len(out)}")
    return out


@router.post("/clear-history")
async def clear_history():
    # Wipe DB history and best-effort remove log files
    db.clear_builds()
    try:
        base = log_manager.base
        for p in base.glob("*.log"):
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass
    return {"ok": True}


@router.get("/download/{build_id}/{filename}")
async def download_artifact(build_id: str, filename: str):
    row = db.get_build(build_id)
    if not row:
        return {"error": "not_found"}
    files = json.loads(row.get("output_files") or "[]")
    target = None
    for p in files:
        if Path(p).name == filename:
            target = p
            break
    if not target:
        return {"error": "file_not_found"}
    log.info(f"download id={build_id} file={filename}")
    return FileResponse(target, filename=filename, media_type='application/octet-stream')

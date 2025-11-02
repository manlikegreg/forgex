from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

_DB_PATH = Path.home() / ".forgex" / "forgex.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as c:
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS builds (
                build_id TEXT PRIMARY KEY,
                project_path TEXT,
                working_dir TEXT,
                language TEXT,
                start_command TEXT,
                output_type TEXT,
                include_env INTEGER DEFAULT 0,
                output_name TEXT,
                status TEXT,
                started_at TEXT,
                finished_at TEXT,
                output_files TEXT,
                error TEXT,
                log_path TEXT
            )
            """
        )
        # Migrate older DBs: add include_env/output_name if missing
        cur = c.execute("PRAGMA table_info(builds)")
        cols = [row[1] for row in cur.fetchall()]
        if "include_env" not in cols:
            c.execute("ALTER TABLE builds ADD COLUMN include_env INTEGER DEFAULT 0")
        if "output_name" not in cols:
            c.execute("ALTER TABLE builds ADD COLUMN output_name TEXT")
        c.commit()


def insert_build(row: Dict[str, Any]) -> None:
    with _conn() as c:
        cols = ",".join(row.keys())
        qs = ",".join([":" + k for k in row.keys()])
        c.execute(f"INSERT INTO builds ({cols}) VALUES ({qs})", row)
        c.commit()


def update_build(build_id: str, **updates: Any) -> None:
    if not updates:
        return
    with _conn() as c:
        set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
        updates["build_id"] = build_id
        c.execute(f"UPDATE builds SET {set_clause} WHERE build_id = :build_id", updates)
        c.commit()


def get_build(build_id: str) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM builds WHERE build_id = ?", (build_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def list_builds(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM builds ORDER BY datetime(started_at) DESC LIMIT ? OFFSET ?", (limit, offset))
        return [dict(r) for r in cur.fetchall()]


def clear_builds() -> None:
    with _conn() as c:
        c.execute("DELETE FROM builds")
        c.commit()

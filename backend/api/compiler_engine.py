from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

PY_ENTRY_NAMES = ["app.py", "main.py", "run.py", "manage.py", "index.py"]


def _read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def detect_language(project_path: str) -> Tuple[str, Dict[str, float]]:
    """Return (best_language, confidences_by_lang)."""
    p = Path(project_path)
    confidences = {k: 0.0 for k in ["node", "python", "go", "rust", "java", "csharp", "batch"]}

    # Deterministic markers (priority order)
    if (p / "package.json").exists():
        confidences["node"] += 0.9
    if (p / "requirements.txt").exists() or (p / "pyproject.toml").exists():
        confidences["python"] += 0.8
    for f in p.rglob("*.py"):
        confidences["python"] += 0.02
        break
    if (p / "go.mod").exists():
        confidences["go"] += 0.8
    for f in p.rglob("*.go"):
        confidences["go"] += 0.02
        break
    if (p / "Cargo.toml").exists():
        confidences["rust"] += 0.8
    if (p / "pom.xml").exists() or (p / "build.gradle").exists():
        confidences["java"] += 0.7
    for f in p.rglob("*.java"):
        confidences["java"] += 0.02
        break
    for f in p.rglob("*.jar"):
        confidences["java"] += 0.05
        break
    for f in p.rglob("*.csproj"):
        confidences["csharp"] += 0.8
        break
    for f in list(p.rglob("*.bat")) + list(p.rglob("*.ps1")) + list(p.rglob("*.sh")):
        confidences["batch"] += 0.05
        break

    best_lang = max(confidences.items(), key=lambda kv: kv[1])[0]
    return best_lang, confidences


def find_python_entries(project_path: str, max_depth: int = 3) -> List[Tuple[str, float]]:
    p = Path(project_path)
    candidates: List[Tuple[str, float]] = []
    EXCLUDED_DIRS = {'.venv', 'venv', 'env', 'node_modules', 'dist', 'build', '__pycache__', '.git'}
    def _is_excluded(path: Path) -> bool:
        return any(part in EXCLUDED_DIRS for part in path.parts)
    for depth in range(max_depth + 1):
        for name in PY_ENTRY_NAMES:
            for match in p.glob('/'.join(['*'] * depth + [name]) if depth else name):
                if _is_excluded(match):
                    continue
                score = 0.5
                text = _read_text_safe(match)
                # Framework hints
                for key, bonus in [("flask", 0.2), ("fastapi", 0.25), ("django", 0.2), ("uvicorn", 0.1)]:
                    if key in text:
                        score += bonus
                candidates.append((str(match), min(score, 1.0)))
    # De-duplicate preferring higher score
    best: Dict[str, float] = {}
    for path, score in candidates:
        best[path] = max(score, best.get(path, 0.0))
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)


def suggest_command(language: str, project_path: str) -> str:
    if language == "node":
        pj = Path(project_path) / "package.json"
        if pj.exists():
            try:
                data = json.loads(pj.read_text(encoding="utf-8"))
                scripts = (data.get("scripts") or {})
                if scripts.get("start"):
                    return "npm run start"
                if data.get("main"):
                    return f"node {data['main']}"
            except Exception:
                pass
        return "node index.js"
    if language == "python":
        entries = find_python_entries(project_path)
        if entries:
            first = Path(entries[0][0])
            return f"python {first.relative_to(project_path)}"
        return "python main.py"
    return ""


def inspect_project(project_path: str) -> Dict:
    lang, scores = detect_language(project_path)
    candidates: List[Dict] = []
    if lang == "python":
        candidates = [{"path": p, "confidence": c} for p, c in find_python_entries(project_path)]
    elif lang == "node":
        # Look into package.json
        pj = Path(project_path) / "package.json"
        if pj.exists():
            try:
                data = json.loads(pj.read_text(encoding="utf-8"))
                main = data.get("main")
                if main:
                    candidates.append({"path": str(Path(project_path) / main), "confidence": 0.8})
                scripts = (data.get("scripts") or {})
                if scripts.get("start"):
                    candidates.append({"path": "scripts.start", "confidence": 0.7})
            except Exception:
                pass
    return {
        "language": lang,
        "scores": scores,
        "entry_candidates": candidates,
        "suggested_command": suggest_command(lang, project_path),
    }

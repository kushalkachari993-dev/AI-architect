from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.models import ArchitecturePackage

PROJECT_DIR = Path("data/projects")


def save_project(package: ArchitecturePackage) -> dict[str, str]:
    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    project_id = uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    payload = {
        "id": project_id,
        "created_at": created_at,
        "package": package.model_dump(),
    }
    _project_path(project_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"id": project_id, "created_at": created_at}


def list_projects(limit: int = 20) -> list[dict[str, str]]:
    if not PROJECT_DIR.exists():
        return []

    projects = []
    for path in PROJECT_DIR.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            package = payload["package"]
            projects.append(
                {
                    "id": payload["id"],
                    "created_at": payload["created_at"],
                    "project_name": package["project_name"],
                    "generation_mode": package["generation_mode"],
                }
            )
        except (KeyError, json.JSONDecodeError):
            continue

    return sorted(projects, key=lambda item: item["created_at"], reverse=True)[:limit]


def load_project(project_id: str) -> ArchitecturePackage | None:
    path = _project_path(project_id)
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ArchitecturePackage.model_validate(payload["package"])
    except (KeyError, json.JSONDecodeError):
        return None


def _project_path(project_id: str) -> Path:
    clean_id = "".join(char for char in project_id if char.isalnum())
    return PROJECT_DIR / f"{clean_id}.json"

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.models import ArchitecturePackage

LOCAL_PROJECT_DIR = Path("data/projects")
SERVERLESS_PROJECT_DIR = Path("/tmp/ai-architect/projects")
POSTGRES_ENV_NAMES = (
    "DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_PRISMA_URL",
    "PRISMA_DATABASE_URL",
)


def save_project(package: ArchitecturePackage) -> dict[str, str | bool]:
    project_id = uuid4().hex
    created_at = datetime.now(UTC).isoformat()
    payload = {
        "id": project_id,
        "created_at": created_at,
        "package": package.model_dump(),
    }
    if _postgres_url():
        try:
            _save_project_postgres(payload)
            return {"id": project_id, "created_at": created_at, "persisted": True}
        except Exception:
            pass

    try:
        project_dir = _project_dir()
        project_dir.mkdir(parents=True, exist_ok=True)
        _project_path(project_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return {"id": project_id, "created_at": created_at, "persisted": True}
    except OSError:
        return {"id": project_id, "created_at": created_at, "persisted": False}


def list_projects(limit: int = 20) -> list[dict[str, str]]:
    if _postgres_url():
        try:
            return _list_projects_postgres(limit)
        except Exception:
            return []

    project_dir = _project_dir()
    if not project_dir.exists():
        return []

    projects = []
    for path in project_dir.glob("*.json"):
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
    if _postgres_url():
        try:
            return _load_project_postgres(project_id)
        except Exception:
            return None

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
    return _project_dir() / f"{clean_id}.json"


def _project_dir() -> Path:
    configured = os.getenv("PROJECT_STORAGE_DIR")
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        return SERVERLESS_PROJECT_DIR
    return LOCAL_PROJECT_DIR


def _postgres_url() -> str | None:
    for name in POSTGRES_ENV_NAMES:
        value = os.getenv(name)
        if value:
            return value
    return None


def _connect_postgres():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required for Postgres storage") from exc

    return psycopg.connect(_postgres_url())


def _ensure_postgres_schema(connection: Any) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            create table if not exists architecture_projects (
                id text primary key,
                created_at timestamptz not null,
                project_name text not null,
                generation_mode text not null,
                payload jsonb not null
            )
            """
        )
    connection.commit()


def _save_project_postgres(payload: dict) -> None:
    package = payload["package"]
    with _connect_postgres() as connection:
        _ensure_postgres_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into architecture_projects (id, created_at, project_name, generation_mode, payload)
                values (%s, %s, %s, %s, %s::jsonb)
                on conflict (id) do update set
                    created_at = excluded.created_at,
                    project_name = excluded.project_name,
                    generation_mode = excluded.generation_mode,
                    payload = excluded.payload
                """,
                (
                    payload["id"],
                    payload["created_at"],
                    package["project_name"],
                    package["generation_mode"],
                    json.dumps(payload),
                ),
            )
        connection.commit()


def _list_projects_postgres(limit: int) -> list[dict[str, str]]:
    with _connect_postgres() as connection:
        _ensure_postgres_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select id, created_at, project_name, generation_mode
                from architecture_projects
                order by created_at desc
                limit %s
                """,
                (limit,),
            )
            return [
                {
                    "id": row[0],
                    "created_at": row[1].isoformat(),
                    "project_name": row[2],
                    "generation_mode": row[3],
                }
                for row in cursor.fetchall()
            ]


def _load_project_postgres(project_id: str) -> ArchitecturePackage | None:
    clean_id = "".join(char for char in project_id if char.isalnum())
    with _connect_postgres() as connection:
        _ensure_postgres_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "select payload from architecture_projects where id = %s",
                (clean_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            payload = row[0]
            if isinstance(payload, str):
                payload = json.loads(payload)
            return ArchitecturePackage.model_validate(payload["package"])

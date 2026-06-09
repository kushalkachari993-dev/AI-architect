from __future__ import annotations

import json
import re

from app.models import ApiEndpoint, Entity


def fastapi_files(project_name: str, entities: list[Entity], endpoints: list[ApiEndpoint]) -> dict[str, str]:
    return {
        "generated_fastapi/README.md": f"# {project_name} API\n\nGenerated starter API from the uploaded architecture package.\n",
        "generated_fastapi/requirements.txt": "fastapi==0.115.6\nuvicorn[standard]==0.34.0\npydantic==2.10.4\nsqlalchemy==2.0.36\nalembic==1.14.0\n",
        "generated_fastapi/app/__init__.py": "",
        "generated_fastapi/app/main.py": _fastapi_main(project_name, entities),
        "generated_fastapi/app/schemas.py": _schemas_file(entities),
        "generated_fastapi/app/routers/__init__.py": "",
        "generated_fastapi/app/routers/generated.py": _router_file(entities),
        "generated_fastapi/app/services.py": _service_file(entities),
        "generated_fastapi/app/repositories.py": _repository_file(),
        "generated_fastapi/alembic/README.md": "Add SQLAlchemy models and migrations here before production use.\n",
        "generated_fastapi/openapi_summary.md": _openapi_summary(endpoints),
        "generated_fastapi/openapi.yaml": openapi_yaml(project_name, endpoints),
    }


def docker_files(project_name: str) -> dict[str, str]:
    app_module = slug(project_name).replace("-", "_")
    return {
        "generated_docker/backend.Dockerfile": (
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "COPY . .\n"
            'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]\n'
        ),
        "generated_docker/frontend.Dockerfile": (
            "FROM node:22-alpine\n"
            "WORKDIR /app\n"
            "COPY package.json package-lock.json* ./\n"
            "RUN npm install\n"
            "COPY . .\n"
            'CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]\n'
        ),
        "generated_docker/docker-compose.yml": (
            "services:\n"
            "  backend:\n"
            "    build:\n"
            "      context: ../generated_fastapi\n"
            "      dockerfile: ../generated_docker/backend.Dockerfile\n"
            "    ports:\n"
            '      - "8000:8000"\n'
            "    environment:\n"
            "      - DATABASE_URL=postgresql://app:app@postgres:5432/app\n"
            "    depends_on:\n"
            "      - postgres\n"
            "  frontend:\n"
            "    build:\n"
            "      context: ../generated_react\n"
            "      dockerfile: ../generated_docker/frontend.Dockerfile\n"
            "    ports:\n"
            '      - "5173:5173"\n'
            "    environment:\n"
            "      - VITE_API_BASE_URL=http://localhost:8000\n"
            "    depends_on:\n"
            "      - backend\n"
            "  postgres:\n"
            "    image: postgres:16\n"
            "    environment:\n"
            "      - POSTGRES_USER=app\n"
            "      - POSTGRES_PASSWORD=app\n"
            "      - POSTGRES_DB=app\n"
            "    ports:\n"
            '      - "5432:5432"\n'
            "    volumes:\n"
            f"      - {app_module}_postgres:/var/lib/postgresql/data\n"
            "      - ../generated_database/schema.sql:/docker-entrypoint-initdb.d/001-schema.sql:ro\n"
            "volumes:\n"
            f"  {app_module}_postgres:\n"
        ),
    }


def react_files(project_name: str, entities: list[Entity]) -> dict[str, str]:
    return {
        "generated_react/package.json": json.dumps(
            {
                "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
                "dependencies": {
                    "@vitejs/plugin-react": "latest",
                    "vite": "latest",
                    "react": "latest",
                    "react-dom": "latest",
                },
                "devDependencies": {},
            },
            indent=2,
        ),
        "generated_react/index.html": '<div id="root"></div><script type="module" src="/src/main.jsx"></script>\n',
        "generated_react/src/main.jsx": _react_main(project_name, entities),
        "generated_react/src/styles.css": _react_css(),
        "generated_react/README.md": f"# {project_name} Frontend\n\nReact/Vite starter generated from the approved architecture.\n",
    }


def database_files(project_name: str, entities: list[Entity]) -> dict[str, str]:
    return {
        "generated_database/schema.sql": _schema_sql(entities),
        "generated_database/README.md": f"# {project_name} Database\n\nStarter PostgreSQL schema. Review indexes and constraints before production.\n",
    }


def terraform_files(project_name: str) -> dict[str, str]:
    name = slug(project_name)
    return {
        "generated_terraform/main.tf": (
            'terraform {\n  required_version = ">= 1.6.0"\n}\n\n'
            'provider "aws" {\n  region = var.aws_region\n}\n\n'
            'resource "aws_ecs_cluster" "main" {\n'
            f'  name = "{name}-cluster"\n'
            "}\n\n"
            'resource "aws_cloudwatch_log_group" "app" {\n'
            f'  name              = "/ecs/{name}"\n'
            "  retention_in_days = 30\n"
            "}\n"
        ),
        "generated_terraform/variables.tf": (
            'variable "aws_region" {\n'
            '  type    = string\n'
            '  default = "us-east-1"\n'
            "}\n"
        ),
        "generated_terraform/outputs.tf": (
            'output "cluster_name" {\n'
            "  value = aws_ecs_cluster.main.name\n"
            "}\n"
        ),
    }


def _fastapi_main(project_name: str, entities: list[Entity]) -> str:
    return (
        "from fastapi import FastAPI\n\n"
        "from app.routers.generated import router as generated_router\n\n"
        f'app = FastAPI(title="{project_name}")\n\n\n'
        '@app.get("/health")\n'
        "def health() -> dict[str, str]:\n"
        '    return {"status": "ok"}\n\n'
        "\napp.include_router(generated_router)\n"
    )


def _schemas_file(entities: list[Entity]) -> str:
    models = ["from pydantic import BaseModel\n"]
    for entity in entities:
        models.append(_model_def(entity))
    return "\n\n".join(models) + "\n"


def _model_def(entity: Entity) -> str:
    lines = [f"class {safe_class_name(entity.name)}(BaseModel):"]
    for field in entity.fields:
        if ":" not in field:
            continue
        name, raw_type = [part.strip() for part in field.split(":", 1)]
        lines.append(f"    {safe_field_name(name)}: {_python_type(raw_type)}")
    if len(lines) == 1:
        lines.append("    id: str")
    return "\n".join(lines)


def _router_file(entities: list[Entity]) -> str:
    imports = sorted({safe_class_name(entity.name) for entity in entities})
    lines = [
        "from fastapi import APIRouter, status\n",
        f"from app.schemas import {', '.join(imports)}",
        "from app.services import create_record, list_records\n\n",
        'router = APIRouter(prefix="/api", tags=["generated"])\n',
    ]
    for entity in entities:
        class_name = safe_class_name(entity.name)
        resource = resource_name(entity.name)
        fn_name = resource.replace("-", "_")
        lines.append(
            f'''
@router.get("/{resource}")
def list_{fn_name}() -> dict[str, list[{class_name}]]:
    return {{"items": list_records("{resource}")}}


@router.post("/{resource}", status_code=status.HTTP_201_CREATED)
def create_{fn_name}(payload: {class_name}) -> dict[str, str]:
    return create_record("{resource}", payload.model_dump())
'''
        )
    return "\n".join(lines)


def _service_file(entities: list[Entity]) -> str:
    resources = ", ".join(f'"{resource_name(entity.name)}": []' for entity in entities)
    return (
        "from uuid import uuid4\n\n"
        f"_STORE: dict[str, list[dict]] = {{{resources}}}\n\n\n"
        "def list_records(resource: str) -> list[dict]:\n"
        "    return _STORE.setdefault(resource, [])\n\n\n"
        "def create_record(resource: str, payload: dict) -> dict[str, str]:\n"
        "    record_id = str(uuid4())\n"
        "    payload = {**payload, \"id\": payload.get(\"id\") or record_id}\n"
        "    _STORE.setdefault(resource, []).append(payload)\n"
        "    return {\"id\": payload[\"id\"], \"status\": \"created\"}\n"
    )


def _repository_file() -> str:
    return (
        "class Repository:\n"
        "    def __init__(self, session):\n"
        "        self.session = session\n\n"
        "    def add(self, model):\n"
        "        self.session.add(model)\n"
        "        return model\n"
    )


def _react_main(project_name: str, entities: list[Entity]) -> str:
    resources = ",\n  ".join(
        f'{{ name: "{entity.name}", path: "/api/{resource_name(entity.name)}" }}' for entity in entities
    )
    return (
        "import React, { useEffect, useState } from 'react';\n"
        "import { createRoot } from 'react-dom/client';\n"
        "import './styles.css';\n\n"
        f"const resources = [\n  {resources}\n];\n"
        "const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';\n\n"
        "function App() {\n"
        "  const [health, setHealth] = useState('checking');\n"
        "  useEffect(() => {\n"
        "    fetch(`${apiBaseUrl}/health`).then((res) => res.json()).then((data) => setHealth(data.status)).catch(() => setHealth('offline'));\n"
        "  }, []);\n"
        "  return <main className=\"shell\"><section className=\"top\"><h1>"
        + project_name
        + "</h1><span>{health}</span></section><section className=\"grid\">{resources.map((resource) => <article key={resource.path}><h2>{resource.name}</h2><p>{resource.path}</p><button>Open</button></article>)}</section></main>;\n"
        "}\n\n"
        "createRoot(document.getElementById('root')).render(<App />);\n"
    )


def _react_css() -> str:
    return (
        "body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #f4f6f8; color: #17202a; }\n"
        ".shell { padding: 32px; }\n"
        ".top { display: flex; justify-content: space-between; align-items: center; background: #fff; border: 1px solid #d9e0e8; border-radius: 8px; padding: 18px; }\n"
        ".top h1 { margin: 0; font-size: 24px; }\n"
        ".top span { background: #dcfce7; color: #188a5a; border-radius: 999px; padding: 8px 12px; font-weight: 800; }\n"
        ".grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; margin-top: 18px; }\n"
        "article { background: #fff; border: 1px solid #d9e0e8; border-radius: 8px; padding: 16px; }\n"
        "article h2 { margin: 0 0 8px; font-size: 18px; }\n"
        "article p { color: #667085; }\n"
        "button { border: 0; border-radius: 8px; padding: 10px 12px; background: #2457d6; color: white; font-weight: 800; }\n"
    )


def _schema_sql(entities: list[Entity]) -> str:
    statements = []
    for entity in entities:
        columns = ["  id uuid primary key"]
        for field in entity.fields:
            if ":" not in field:
                continue
            name, raw_type = [part.strip() for part in field.split(":", 1)]
            column_name = safe_field_name(name)
            if column_name == "id":
                continue
            columns.append(f"  {column_name} {_sql_type(raw_type)}")
        columns.extend(["  created_at timestamptz default now()", "  updated_at timestamptz default now()"])
        statements.append(f"create table if not exists {resource_name(entity.name).replace('-', '_')} (\n" + ",\n".join(columns) + "\n);")
    return "\n\n".join(statements) + "\n"


def _sql_type(raw_type: str) -> str:
    normalized = raw_type.lower()
    if normalized in {"integer", "int"}:
        return "integer"
    if normalized in {"decimal", "float", "money"}:
        return "numeric"
    if normalized in {"datetime", "timestamp"}:
        return "timestamptz"
    if normalized in {"boolean", "bool"}:
        return "boolean"
    if normalized in {"uuid"}:
        return "uuid"
    if normalized in {"text"}:
        return "text"
    return "text"


def _python_type(raw_type: str) -> str:
    normalized = raw_type.lower()
    if normalized in {"integer", "int"}:
        return "int"
    if normalized in {"decimal", "float", "money"}:
        return "float"
    if normalized in {"boolean", "bool"}:
        return "bool"
    return "str"


def _openapi_summary(endpoints: list[ApiEndpoint]) -> str:
    rows = ["# API Design", "", "| Method | Path | Purpose |", "| --- | --- | --- |"]
    rows.extend(f"| {endpoint.method} | `{endpoint.path}` | {endpoint.purpose} |" for endpoint in endpoints)
    return "\n".join(rows) + "\n"


def openapi_yaml(project_name: str, endpoints: list[ApiEndpoint]) -> str:
    paths: dict[str, dict[str, object]] = {}
    for endpoint in endpoints:
        method = endpoint.method.lower()
        paths.setdefault(endpoint.path, {})[method] = {
            "summary": endpoint.purpose,
            "requestBody": {
                "required": bool(endpoint.request),
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                key: {"type": _openapi_type(value)} for key, value in endpoint.request.items()
                            },
                        }
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    key: {"type": _openapi_type(value)}
                                    for key, value in endpoint.response.items()
                                },
                            }
                        }
                    },
                }
            },
        }

    return json.dumps(
        {
            "openapi": "3.1.0",
            "info": {"title": project_name, "version": "1.0.0"},
            "paths": paths,
        },
        indent=2,
    )


def _openapi_type(value: str) -> str:
    normalized = value.lower()
    if "array" in normalized:
        return "array"
    if normalized in {"integer", "int"}:
        return "integer"
    if normalized in {"decimal", "float", "money"}:
        return "number"
    if normalized in {"boolean", "bool"}:
        return "boolean"
    return "string"


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "generated-platform"


def resource_name(name: str) -> str:
    return f"{re.sub(r'(?<!^)(?=[A-Z])', '-', name).lower()}s"


def safe_class_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", " ", value).title().replace(" ", "")
    if not cleaned or cleaned[0].isdigit():
        return "GeneratedModel"
    return cleaned


def safe_field_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value.strip().lower()).strip("_")
    if not cleaned or cleaned[0].isdigit():
        return "field"
    return cleaned

import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import load_dotenv
from app.models import ArchitecturePlan
from app.services.architect import generate_architecture_package, generate_package_from_plan
from app.services.render import package_to_zip
from app.services.storage import list_projects, load_project, save_project

load_dotenv()
MAX_INPUT_CHARS = 80_000

app = FastAPI(
    title="AI Software Architect Agent",
    description="Generate architecture, schema, API, services, cost, deployment, code, Docker, and Terraform from requirements.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "llm_configured": bool(os.getenv("OPENAI_API_KEY") or os.getenv("AI_ARCHITECT_LLM_API_KEY")),
        "model": os.getenv("AI_ARCHITECT_MODEL", "gpt-5-nano"),
        "base_url": os.getenv("AI_ARCHITECT_LLM_BASE_URL", "https://api.openai.com/v1"),
    }


@app.post("/generate")
async def generate(
    requirements_file: UploadFile | None = File(None),
    user_stories_file: UploadFile | None = File(None),
    requirements_text: str = Form(""),
    user_stories_text: str = Form(""),
    domain: str = Form("general"),
):
    requirements = await _read_upload_or_text(requirements_file, requirements_text, "requirements")
    user_stories = await _read_upload_or_text(user_stories_file, user_stories_text, "user stories")
    if domain and domain != "general":
        requirements = f"Domain: {domain}\n\n{requirements}"

    package = generate_architecture_package(requirements, user_stories)
    metadata = save_project(package)
    payload = package.model_dump()
    payload["project_id"] = metadata["id"]
    payload["created_at"] = metadata["created_at"]
    payload["project_persisted"] = metadata["persisted"]
    return payload


@app.post("/generate.zip")
async def generate_zip(
    requirements_file: UploadFile | None = File(None),
    user_stories_file: UploadFile | None = File(None),
    requirements_text: str = Form(""),
    user_stories_text: str = Form(""),
    domain: str = Form("general"),
):
    requirements = await _read_upload_or_text(requirements_file, requirements_text, "requirements")
    user_stories = await _read_upload_or_text(user_stories_file, user_stories_text, "user stories")
    if domain and domain != "general":
        requirements = f"Domain: {domain}\n\n{requirements}"
    package = generate_architecture_package(requirements, user_stories)
    zip_bytes = package_to_zip(package)

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=architecture-package.zip"},
    )


@app.get("/projects")
def projects() -> list[dict[str, str]]:
    return list_projects()


@app.get("/projects/{project_id}")
def project(project_id: str):
    package = load_project(project_id)
    if not package:
        raise HTTPException(status_code=404, detail="Project not found")
    return package.model_dump()


@app.get("/projects/{project_id}/zip")
def project_zip(project_id: str):
    package = load_project(project_id)
    if not package:
        raise HTTPException(status_code=404, detail="Project not found")
    return StreamingResponse(
        iter([package_to_zip(package)]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_id}-architecture-package.zip"},
    )


@app.post("/approve")
def approve(plan: ArchitecturePlan):
    package = generate_package_from_plan(plan)
    metadata = save_project(package)
    payload = package.model_dump()
    payload["project_id"] = metadata["id"]
    payload["created_at"] = metadata["created_at"]
    payload["project_persisted"] = metadata["persisted"]
    return payload


async def _read_text_file(upload: UploadFile) -> str:
    content = await upload.read()
    if not content:
        raise HTTPException(status_code=400, detail=f"{upload.filename} is empty")

    try:
        text = content.decode("utf-8")
        _validate_input_size(text, upload.filename or "uploaded file")
        return text
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{upload.filename} must be a UTF-8 text file",
        ) from exc


async def _read_upload_or_text(upload: UploadFile | None, text: str, label: str) -> str:
    if upload and upload.filename:
        return await _read_text_file(upload)

    if text.strip():
        clean_text = text.strip()
        _validate_input_size(clean_text, label)
        return clean_text

    raise HTTPException(status_code=400, detail=f"Provide a {label} file or paste {label} text")


def _validate_input_size(text: str, label: str) -> None:
    if len(text) > MAX_INPUT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"{label} is too large. Limit each input to {MAX_INPUT_CHARS:,} characters.",
        )

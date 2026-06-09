# AI Software Architect Agent

A FastAPI service that accepts a requirements document and user stories, then generates a software architecture package:

- Architecture diagram
- Database schema
- API design
- Microservices breakdown
- Cost estimation
- Deployment plan
- Bonus generated starter code, Docker files, and Terraform

The implementation is hybrid:

- If an LLM key is configured, the service asks the LLM to produce a strict architecture plan as JSON.
- Pydantic validates the plan.
- Deterministic templates generate FastAPI, Docker, and Terraform artifacts from the validated plan.
- If the LLM is unavailable, invalid, or not configured, the service falls back to the local deterministic generator.

## Quick Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the web UI or `http://127.0.0.1:8000/docs` for the API docs.

The UI supports pasted text, uploaded Markdown/text files, domain selection, project history, tabbed review, and ZIP downloads.

## Optional LLM Mode

Copy `.env.example` to `.env` and fill in your key:

```powershell
Copy-Item .env.example .env
```

Example `.env`:

```dotenv
OPENAI_API_KEY=sk-...
AI_ARCHITECT_MODEL=gpt-5-nano
AI_ARCHITECT_LLM_BASE_URL=https://api.openai.com/v1
AI_ARCHITECT_LLM_TIMEOUT_SECONDS=90
AI_ARCHITECT_LLM_MAX_OUTPUT_TOKENS=6000
```

Optional storage setting:

```dotenv
PROJECT_STORAGE_DIR=/tmp/ai-architect/projects
```

For durable project history with Prisma Postgres, set one of these environment variables to your Prisma Postgres connection URL:

```dotenv
PRISMA_DATABASE_URL=postgresql://...
```

The app also recognizes `DATABASE_URL`, `POSTGRES_URL`, and `POSTGRES_PRISMA_URL`.

If no Postgres URL is configured, local development uses `data/projects`. On Vercel/serverless deployments, the fallback is `/tmp`, which is writable but ephemeral.

Then start the API:

```powershell
uvicorn app.main:app --reload
```

The app loads `.env` at startup and lets project `.env` values override stale shell values from the current terminal session.

Responses include `generation_mode`:

- `hybrid-llm`: LLM planned the architecture, deterministic templates generated files.
- `deterministic-fallback`: local rules generated the package.

If the app falls back, responses include `llm_error` with a safe diagnostic such as missing API key, OpenAI auth failure, timeout, invalid JSON, or schema validation failure.

## Generate An Architecture Package

```powershell
curl.exe -X POST http://127.0.0.1:8000/generate `
  -F "requirements_file=@examples/requirements.md" `
  -F "user_stories_file=@examples/user_stories.md"
```

To download a zip containing generated files:

```powershell
curl.exe -X POST http://127.0.0.1:8000/generate.zip `
  -F "requirements_file=@examples/requirements.md" `
  -F "user_stories_file=@examples/user_stories.md" `
  --output architecture-package.zip
```

## Run Tests

```powershell
pytest
```

## Docker

```powershell
docker build -t ai-architect-agent .
docker run -p 8000:8000 ai-architect-agent
```

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from app.models import ArchitecturePlan


class LlmResult:
    def __init__(self, plan: ArchitecturePlan | None, error: str | None = None):
        self.plan = plan
        self.error = error


SYSTEM_PROMPT = """You are a senior software architect.
Return only valid JSON matching this exact shape:
{
  "project_name": "string",
  "summary": "string",
  "architecture_diagram_mermaid": "flowchart LR ...",
  "database_schema": [
    {"name": "EntityName", "fields": ["id: uuid"], "relationships": ["belongs to User"]}
  ],
  "api_design": [
    {
      "method": "GET",
      "path": "/resources",
      "purpose": "string",
      "request": {"field": "type"},
      "response": {"field": "type"}
    }
  ],
  "microservices": [
    {
      "name": "service-name",
      "responsibility": "string",
      "owns": ["EntityName"],
      "dependencies": ["postgres"]
    }
  ],
  "cost_estimate": [
    {"component": "string", "assumption": "string", "monthly_usd": 100}
  ],
  "deployment_plan": ["step"],
  "architecture_options": [
    {
      "name": "MVP Architecture",
      "description": "string",
      "pros": ["string"],
      "cons": ["string"],
      "recommended_for": "string"
    }
  ],
  "review_findings": [
    {
      "severity": "low|medium|high",
      "area": "Complexity|Cost|Schema|API|Security",
      "finding": "string",
      "recommendation": "string"
    }
  ],
  "scorecard": [
    {"category": "Complexity", "score": 1, "rationale": "string"}
  ],
  "non_functional_requirements": [
    {"category": "Security", "recommendation": "string"}
  ],
  "architecture_decision_records": [
    {
      "id": "ADR-001",
      "decision": "string",
      "rationale": "string",
      "alternatives": ["string"],
      "consequences": ["string"]
    }
  ]
}

Design practical cloud-native systems. Keep names implementation-safe.
Act as both architect and reviewer. Challenge your own design:
- Include MVP, scalable, and enterprise architecture options.
- Flag over-engineering and cost risks.
- Prefer modular monolith for small teams, low traffic, or budgets below $100/month.
- Include schema normalization/index concerns and business-semantic API recommendations.
- Include trade-offs, non-functional requirements, and ADRs.
For architecture_diagram_mermaid:
- Use Mermaid flowchart syntax.
- Put every node, edge, classDef, and class statement on its own line.
- Do not put multiple Mermaid statements on one line.
- Avoid parentheses in node labels; use square brackets or database cylinders.
"""


def generate_llm_plan(requirements: str, user_stories: str) -> LlmResult:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("AI_ARCHITECT_LLM_API_KEY")
    if not api_key:
        return LlmResult(None, "OPENAI_API_KEY or AI_ARCHITECT_LLM_API_KEY is not configured")

    provider = os.getenv("AI_ARCHITECT_LLM_PROVIDER", "openai-compatible").lower()
    if provider not in {"openai", "openai-compatible"}:
        return LlmResult(None, f"Unsupported LLM provider: {provider}")

    model = os.getenv("AI_ARCHITECT_MODEL", "gpt-5-nano")
    base_url = os.getenv("AI_ARCHITECT_LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    timeout = float(os.getenv("AI_ARCHITECT_LLM_TIMEOUT_SECONDS", "45"))
    if model.startswith("gpt-5"):
        timeout = max(timeout, 90)

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Requirements document:\n"
                    f"{requirements}\n\n"
                    "User stories:\n"
                    f"{user_stories}\n\n"
                    "Generate the architecture plan JSON now."
                ),
            },
        ],
    }
    if not model.startswith("gpt-5"):
        payload["temperature"] = 0.2

    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    last_error = "LLM request failed"
    for attempt in range(2):
        try:
            with urlopen(request, timeout=timeout) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            content = _extract_message_content(response_json)
            raw_plan = json.loads(content)
            normalized_plan = _normalize_plan_payload(raw_plan)
            return LlmResult(ArchitecturePlan.model_validate(normalized_plan))
        except HTTPError as exc:
            last_error = _http_error_message(exc, attempt)
        except URLError as exc:
            last_error = f"Network error contacting LLM: {exc.reason}"
        except TimeoutError:
            last_error = f"LLM request timed out after {timeout:g} seconds"
        except ValidationError as exc:
            last_error = f"LLM returned JSON that did not match the architecture schema: {_shorten(str(exc))}"
        except json.JSONDecodeError as exc:
            last_error = f"LLM returned invalid JSON: {_shorten(str(exc))}"
        except (KeyError, IndexError, TypeError) as exc:
            last_error = f"LLM response shape was unexpected: {type(exc).__name__}"
        except Exception as exc:
            last_error = f"Unexpected LLM error: {type(exc).__name__}"
        if attempt == 0:
            continue
    return LlmResult(None, last_error)


def _extract_message_content(response_json: dict[str, Any]) -> str:
    return response_json["choices"][0]["message"]["content"]


def _normalize_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = dict(payload)
    payload["api_design"] = [_normalize_endpoint(endpoint) for endpoint in payload.get("api_design", [])]
    payload["database_schema"] = [_normalize_entity(entity) for entity in payload.get("database_schema", [])]
    return payload


def _normalize_endpoint(endpoint: dict[str, Any]) -> dict[str, Any]:
    endpoint = dict(endpoint)
    endpoint["request"] = _flatten_schema(endpoint.get("request", {}))
    endpoint["response"] = _flatten_schema(endpoint.get("response", {}))
    return endpoint


def _normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    entity = dict(entity)
    entity["fields"] = [_field_to_string(field) for field in entity.get("fields", [])]
    entity["relationships"] = [str(item) for item in entity.get("relationships", [])]
    return entity


def _flatten_schema(value: Any, prefix: str = "") -> dict[str, str]:
    if not isinstance(value, dict):
        return {"value": _type_name(value)}

    flattened: dict[str, str] = {}
    for key, item in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, dict):
            if _looks_like_type_object(item):
                flattened[path] = _type_name(item)
            else:
                flattened.update(_flatten_schema(item, path))
        else:
            flattened[path] = _type_name(item)
    return flattened


def _looks_like_type_object(value: dict[str, Any]) -> bool:
    return any(key in value for key in {"type", "format", "description", "example"})


def _field_to_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name") or value.get("field") or value.get("column") or "field"
        return f"{name}: {_type_name(value)}"
    return str(value)


def _type_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "type" in value:
            raw_type = str(value["type"])
            if "format" in value:
                return f"{raw_type}:{value['format']}"
            return raw_type
        if "example" in value:
            return type(value["example"]).__name__
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    return type(value).__name__


def _http_error_message(exc: HTTPError, attempt: int) -> str:
    body = ""
    try:
        body = exc.read().decode("utf-8")
        parsed = json.loads(body)
        message = parsed.get("error", {}).get("message") or body
    except Exception:
        message = body or str(exc)

    if exc.code == 401:
        return "OpenAI authentication failed. Check OPENAI_API_KEY."
    if exc.code == 429:
        return f"OpenAI rate limit or quota error: {_shorten(message)}"
    if exc.code >= 500:
        return f"OpenAI server error on attempt {attempt + 1}: {_shorten(message)}"
    return f"OpenAI API error {exc.code}: {_shorten(message)}"


def _shorten(value: str, limit: int = 220) -> str:
    clean = " ".join(value.split())
    return clean if len(clean) <= limit else clean[:limit] + "..."

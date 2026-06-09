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
Return compact valid JSON matching this exact required shape:
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
  "deployment_plan": ["step"]
}

Design practical cloud-native systems. Keep names implementation-safe.
Keep output concise. The backend will generate reviews, ADRs, scorecards, validation, and files.
Limit database_schema to 4-8 important entities.
Limit api_design to 5-10 business-semantic endpoints.
Prefer MVP/modular monolith for small teams, low traffic, or budgets below $100/month.
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
    max_output_tokens = int(os.getenv("AI_ARCHITECT_LLM_MAX_OUTPUT_TOKENS", "6000"))
    if model.startswith("gpt-5"):
        timeout = max(timeout, 90)

    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_output_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Requirements document:\n"
                    f"{_trim_input(requirements)}\n\n"
                    "User stories:\n"
                    f"{_trim_input(user_stories)}\n\n"
                    "Generate the compact architecture plan JSON now."
                ),
            },
        ],
    }
    if not model.startswith("gpt-5"):
        payload["temperature"] = 0.2

    last_error = "LLM request failed"
    for attempt in range(2):
        try:
            attempt_payload = _payload_for_attempt(payload, attempt, max_output_tokens)
            request = Request(
                f"{base_url}/chat/completions",
                data=json.dumps(attempt_payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urlopen(request, timeout=timeout) as response:
                response_json = json.loads(response.read().decode("utf-8"))
            content = _extract_message_content(response_json)
            raw_plan = _parse_json_content(content, response_json)
            normalized_plan = _normalize_plan_payload(raw_plan)
            return LlmResult(ArchitecturePlan.model_validate(normalized_plan))
        except HTTPError as exc:
            last_error = _http_error_message(exc, attempt)
        except URLError as exc:
            last_error = f"Network error contacting LLM: {exc.reason}"
        except TimeoutError:
            return LlmResult(None, f"LLM request timed out after {timeout:g} seconds")
        except ValidationError as exc:
            last_error = f"LLM returned JSON that did not match the architecture schema: {_shorten(str(exc))}"
        except json.JSONDecodeError as exc:
            last_error = f"LLM returned invalid JSON: {_shorten(str(exc))}"
        except ValueError as exc:
            last_error = str(exc)
        except (KeyError, IndexError, TypeError) as exc:
            last_error = f"LLM response shape was unexpected: {type(exc).__name__}"
        except Exception as exc:
            last_error = f"Unexpected LLM error: {type(exc).__name__}"
        if attempt == 0:
            continue
    return LlmResult(None, last_error)


def _extract_message_content(response_json: dict[str, Any]) -> str:
    content = response_json["choices"][0]["message"].get("content")
    return content or ""


def _payload_for_attempt(payload: dict[str, Any], attempt: int, max_output_tokens: int) -> dict[str, Any]:
    if attempt == 0:
        return payload

    retry_payload = dict(payload)
    retry_payload["messages"] = list(payload["messages"]) + [
        {
            "role": "user",
            "content": (
                "Your previous response was empty or not parseable as JSON. "
                "Return only the compact JSON object, with no markdown and no commentary."
            ),
        }
    ]
    retry_payload["max_completion_tokens"] = min(max(max_output_tokens + 2000, 6000), 8000)
    return retry_payload


def _parse_json_content(content: str, response_json: dict[str, Any]) -> dict[str, Any]:
    cleaned = _clean_json_text(content)
    if not cleaned:
        finish_reason = response_json.get("choices", [{}])[0].get("finish_reason", "unknown")
        token_hint = response_json.get("usage", {})
        raise ValueError(
            "LLM returned an empty message"
            f" (finish_reason={finish_reason}, usage={token_hint}). "
            "Increase AI_ARCHITECT_LLM_MAX_OUTPUT_TOKENS or use a smaller input."
        )

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        extracted = _extract_json_object(cleaned)
        if extracted:
            return json.loads(extracted)
        finish_reason = response_json.get("choices", [{}])[0].get("finish_reason", "unknown")
        raise ValueError(
            "LLM returned text but no JSON object could be extracted"
            f" (finish_reason={finish_reason}, prefix={_shorten(cleaned[:500])})."
        ) from exc


def _clean_json_text(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _extract_json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


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


def _trim_input(value: str, limit: int = 12000) -> str:
    clean = value.strip()
    return clean if len(clean) <= limit else clean[:limit] + "\n\n[Input truncated for LLM latency.]"

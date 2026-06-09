from __future__ import annotations

import re

from app.models import Microservice


def normalize_mermaid(source: str) -> str:
    text = source.strip().strip("`").strip()
    if not text:
        return default_diagram()

    text = re.sub(r"^mermaid\s+", "", text, flags=re.IGNORECASE).strip()
    text = text.replace("\\n", "\n")
    text = re.sub(r"\s+", " ", text) if "\n" not in text else text

    if not re.match(r"^(flowchart|graph)\s+(TD|TB|BT|RL|LR)\b", text, flags=re.IGNORECASE):
        text = f"flowchart LR\n{text}"

    text = _split_one_line_mermaid(text)
    lines = []
    for line in text.splitlines():
        clean_line = line.strip().rstrip(";")
        if clean_line:
            lines.append(f"  {clean_line}" if lines else clean_line)

    return "\n".join(lines)


def service_diagram(services: list[Microservice]) -> str:
    gateway_id = "gateway"
    lines = [
        "flowchart LR",
        '  client["Web and Mobile Client"] --> gateway["API Gateway"]',
    ]
    service_ids = []
    for index, service in enumerate(services, start=1):
        node_id = f"svc{index}"
        label = _label(service.name)
        if service.name == "api-gateway":
            gateway_id = node_id
            service_ids.append((node_id, service))
            lines[1] = f'  client["Web and Mobile Client"] --> {node_id}["{label}"]'
        else:
            service_ids.append((node_id, service))
            lines.append(f'  {gateway_id} --> {node_id}["{label}"]')

    lines.extend(
        [
            '  db[("PostgreSQL")]',
            '  cache[("Redis Cache")]',
            '  bus["Event Bus"]',
            '  obs["Observability"]',
        ]
    )
    for node_id, service in service_ids:
        dependencies = {dependency.lower() for dependency in service.dependencies}
        if any("postgres" in dependency or "db" in dependency for dependency in dependencies):
            lines.append(f"  {node_id} --> db")
        if any("redis" in dependency or "cache" in dependency for dependency in dependencies):
            lines.append(f"  {node_id} --> cache")
        if any("event" in dependency or "bus" in dependency or "queue" in dependency for dependency in dependencies):
            lines.append(f"  {node_id} --> bus")
        lines.append(f"  {node_id} --> obs")

    return "\n".join(dict.fromkeys(lines))


def default_diagram() -> str:
    return "\n".join(
        [
            "flowchart LR",
            "  client[Client] --> gateway[API Gateway]",
            "  gateway --> service[Application Service]",
            "  service --> database[(Database)]",
        ]
    )


def _split_one_line_mermaid(text: str) -> str:
    if "\n" in text:
        return text

    text = re.sub(r"\s+(classDef\s+)", r"\n\1", text)
    text = re.sub(r"\s+(class\s+[A-Za-z0-9_,]+\s+)", r"\n\1", text)
    text = re.sub(r"\s+([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|-.->|==>))", r"\n\1", text)
    text = re.sub(
        r"(?<!>)\s+([A-Za-z][A-Za-z0-9_]*(?:\[[^\]]+\]|\(\([^)]+\)\)|\([^)]+\)))",
        r"\n\1",
        text,
    )
    text = re.sub(r"^(flowchart|graph)\s+(TD|TB|BT|RL|LR)\s+", r"\1 \2\n", text, flags=re.IGNORECASE)
    return text


def _label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9 /_-]+", "", value).replace('"', "").strip() or "Service"

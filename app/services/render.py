from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from app.models import ArchitecturePackage
from app.services.templates import openapi_yaml


def package_to_zip(package: ArchitecturePackage) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("architecture.md", _architecture_markdown(package))
        archive.writestr("openapi.yaml", openapi_yaml(package.project_name, package.api_design))
        for group in (
            package.generated_files.fastapi_code,
            package.generated_files.react_frontend,
            package.generated_files.database_files,
            package.generated_files.docker_files,
            package.generated_files.terraform,
        ):
            for path, content in group.items():
                archive.writestr(path, content)
    return output.getvalue()


def _architecture_markdown(package: ArchitecturePackage) -> str:
    cost_total = sum(item.monthly_usd for item in package.cost_estimate)
    lines = [
        f"# {package.project_name}",
        "",
        package.summary,
        "",
        "## Architecture Diagram",
        "",
        "```mermaid",
        package.architecture_diagram_mermaid,
        "```",
        "",
        "## Database Schema",
        "",
    ]
    for entity in package.database_schema:
        lines.append(f"### {entity.name}")
        lines.extend(f"- {field}" for field in entity.fields)
        if entity.relationships:
            lines.append(f"- relationships: {', '.join(entity.relationships)}")
        lines.append("")

    lines.extend(["## Microservices", ""])
    for service in package.microservices:
        lines.append(f"### {service.name}")
        lines.append(service.responsibility)
        lines.append(f"- owns: {', '.join(service.owns)}")
        lines.append(f"- dependencies: {', '.join(service.dependencies)}")
        lines.append("")

    lines.extend(["## Cost Estimate", "", "| Component | Assumption | Monthly USD |", "| --- | --- | ---: |"])
    lines.extend(f"| {item.component} | {item.assumption} | ${item.monthly_usd} |" for item in package.cost_estimate)
    lines.extend([f"| **Total** | Estimated baseline | **${cost_total}** |", "", "## Deployment Plan", ""])
    lines.extend(f"{index}. {step}" for index, step in enumerate(package.deployment_plan, start=1))
    lines.extend(["", "## Architecture Options", ""])
    for option in package.architecture_options:
        lines.append(f"### {option.name}")
        lines.append(option.description)
        lines.append(f"- recommended for: {option.recommended_for}")
        lines.append(f"- pros: {', '.join(option.pros)}")
        lines.append(f"- cons: {', '.join(option.cons)}")
        lines.append("")

    lines.extend(["## Architecture Review", ""])
    for finding in package.review_findings:
        lines.append(f"- **{finding.severity.upper()} / {finding.area}**: {finding.finding} Recommendation: {finding.recommendation}")

    lines.extend(["", "## Risk Scorecard", "", "Lower is better: 1 means low risk, 10 means high risk.", ""])
    lines.extend(["| Category | Risk Score | Rationale |", "| --- | ---: | --- |"])
    lines.extend(f"| {item.category} | {item.score}/10 | {item.rationale} |" for item in package.scorecard)

    lines.extend(["", "## Non-Functional Requirements", ""])
    lines.extend(f"- **{item.category}**: {item.recommendation}" for item in package.non_functional_requirements)

    lines.extend(["", "## Architecture Validation Report", ""])
    lines.extend(["| Check | Status | Details | Recommendation |", "| --- | --- | --- | --- |"])
    lines.extend(
        f"| {item.check} | {item.status} | {item.details} | {item.recommendation} |"
        for item in package.validation_report
    )

    lines.extend(["", "## Architecture Decision Records", ""])
    for adr in package.architecture_decision_records:
        lines.append(f"### {adr.id}: {adr.decision}")
        lines.append(adr.rationale)
        lines.append(f"- alternatives: {', '.join(adr.alternatives)}")
        lines.append(f"- consequences: {', '.join(adr.consequences)}")
        lines.append("")
    return "\n".join(lines) + "\n"

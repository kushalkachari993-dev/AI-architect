from __future__ import annotations

import re

from app.models import (
    ApiEndpoint,
    ArchitectureDecisionRecord,
    ArchitectureOption,
    ArchitecturePlan,
    ArchitecturePackage,
    CostLineItem,
    Entity,
    GeneratedFiles,
    Microservice,
    NonFunctionalRequirement,
    ReviewFinding,
    ScorecardItem,
    ValidationCheck,
)
from app.services.diagram import normalize_mermaid, service_diagram
from app.services.llm import generate_llm_plan
from app.services.templates import database_files, docker_files, fastapi_files, react_files, terraform_files


DOMAIN_HINTS = {
    "payment": ("Payment", ["id: uuid", "amount: decimal", "currency: string", "status: string"]),
    "order": ("Order", ["id: uuid", "user_id: uuid", "status: string", "total: decimal"]),
    "booking": ("Booking", ["id: uuid", "user_id: uuid", "start_time: datetime", "status: string"]),
    "inventory": ("InventoryItem", ["id: uuid", "sku: string", "quantity: integer", "location: string"]),
    "message": ("Message", ["id: uuid", "sender_id: uuid", "body: text", "created_at: datetime"]),
    "notification": ("Notification", ["id: uuid", "user_id: uuid", "channel: string", "status: string"]),
    "report": ("Report", ["id: uuid", "owner_id: uuid", "type: string", "generated_at: datetime"]),
}


def generate_architecture_package(requirements: str, user_stories: str) -> ArchitecturePackage:
    llm_result = generate_llm_plan(requirements, user_stories)
    if llm_result.plan:
        return _package_from_plan(llm_result.plan, generation_mode="hybrid-llm")

    return _package_from_plan(
        _deterministic_plan(requirements, user_stories),
        generation_mode="deterministic-fallback",
        llm_error=llm_result.error,
    )


def generate_package_from_plan(plan: ArchitecturePlan) -> ArchitecturePackage:
    return _package_from_plan(plan, generation_mode="approved-edit")


def _deterministic_plan(requirements: str, user_stories: str) -> ArchitecturePlan:
    text = f"{requirements}\n{user_stories}"
    project_name = _project_name(requirements)
    entities = _entities(text)
    services = _microservices(entities)
    endpoints = _endpoints(entities)

    return ArchitecturePlan(
        project_name=project_name,
        summary=_summary(requirements, user_stories),
        architecture_diagram_mermaid=_diagram(services),
        database_schema=entities,
        api_design=endpoints,
        microservices=services,
        cost_estimate=_cost_estimate(len(services)),
        deployment_plan=_deployment_plan(),
        architecture_options=_architecture_options(),
        review_findings=_review_findings(services, _cost_estimate(len(services))),
        scorecard=_scorecard(services, _cost_estimate(len(services))),
        non_functional_requirements=_non_functional_requirements(),
        architecture_decision_records=_architecture_decision_records(),
        validation_report=[],
    )


def _package_from_plan(plan: ArchitecturePlan, generation_mode: str, llm_error: str | None = None) -> ArchitecturePackage:
    plan_data = plan.model_dump()
    plan_data.pop("generation_mode", None)
    plan_data.pop("llm_error", None)
    plan_data.pop("generated_files", None)
    services = [Microservice.model_validate(item) for item in plan_data["microservices"]]
    plan_data["architecture_diagram_mermaid"] = normalize_mermaid(service_diagram(services))
    _fill_review_artifacts(plan_data)
    return ArchitecturePackage(
        **plan_data,
        generation_mode=generation_mode,
        llm_error=llm_error,
        generated_files=GeneratedFiles(
            fastapi_code=fastapi_files(plan.project_name, plan.database_schema, plan.api_design),
            react_frontend=react_files(plan.project_name, plan.database_schema),
            database_files=database_files(plan.project_name, plan.database_schema),
            docker_files=docker_files(plan.project_name),
            terraform=terraform_files(plan.project_name),
        ),
    )


def _fill_review_artifacts(plan_data: dict) -> None:
    services = [Microservice.model_validate(item) for item in plan_data["microservices"]]
    costs = [CostLineItem.model_validate(item) for item in plan_data["cost_estimate"]]
    if not plan_data.get("architecture_options"):
        plan_data["architecture_options"] = [item.model_dump() for item in _architecture_options()]
    if not plan_data.get("review_findings"):
        plan_data["review_findings"] = [item.model_dump() for item in _review_findings(services, costs)]
    if not plan_data.get("scorecard"):
        plan_data["scorecard"] = [item.model_dump() for item in _scorecard(services, costs)]
    if not plan_data.get("non_functional_requirements"):
        plan_data["non_functional_requirements"] = [item.model_dump() for item in _non_functional_requirements()]
    if not plan_data.get("architecture_decision_records"):
        plan_data["architecture_decision_records"] = [item.model_dump() for item in _architecture_decision_records()]
    if not plan_data.get("validation_report"):
        plan_data["validation_report"] = [item.model_dump() for item in _validation_report(plan_data)]


def _project_name(requirements: str) -> str:
    first_heading = re.search(r"^#\s+(.+)$", requirements, flags=re.MULTILINE)
    if first_heading:
        return _clean_name(first_heading.group(1))

    first_line = next((line.strip() for line in requirements.splitlines() if line.strip()), "")
    return _clean_name(first_line[:60] or "Generated Platform")


def _clean_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 ]+", "", value).strip()
    return value or "Generated Platform"


def _summary(requirements: str, user_stories: str) -> str:
    req = _first_sentence(requirements)
    stories = len(re.findall(r"\bAs a\b", user_stories, flags=re.IGNORECASE))
    return f"{req} The architecture is optimized for API-first delivery, service ownership, observability, and cloud deployment. Parsed {stories or 'multiple'} user story signals."


def _first_sentence(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip("# ").strip()
    if not compact:
        return "This platform supports the uploaded product requirements."
    match = re.match(r"(.{1,220}?)(?:[.!?]|$)", compact)
    return match.group(1).strip() if match else compact[:220]


def _entities(text: str) -> list[Entity]:
    lowered = text.lower()
    entities = [
        Entity(
            name="User",
            fields=["id: uuid", "email: string", "name: string", "role: string", "created_at: datetime"],
            relationships=["owns domain records", "authenticates API requests"],
        )
    ]

    for keyword, (name, fields) in DOMAIN_HINTS.items():
        if keyword in lowered:
            entities.append(
                Entity(
                    name=name,
                    fields=fields + ["created_at: datetime", "updated_at: datetime"],
                    relationships=["belongs to User"] if "user_id: uuid" in fields else [],
                )
            )

    if len(entities) == 1:
        entities.append(
            Entity(
                name="Workspace",
                fields=["id: uuid", "owner_id: uuid", "name: string", "status: string", "created_at: datetime"],
                relationships=["belongs to User"],
            )
        )

    entities.append(
        Entity(
            name="AuditEvent",
            fields=["id: uuid", "actor_id: uuid", "action: string", "resource: string", "created_at: datetime"],
            relationships=["records platform activity"],
        )
    )
    return entities


def _microservices(entities: list[Entity]) -> list[Microservice]:
    services = [
        Microservice(
            name="api-gateway",
            responsibility="Routes external traffic, enforces rate limits, and centralizes request authentication.",
            owns=["routing", "request validation"],
            dependencies=["auth-service", "domain services"],
        ),
        Microservice(
            name="auth-service",
            responsibility="Manages users, roles, sessions, and access policies.",
            owns=["User"],
            dependencies=["postgres", "redis"],
        ),
    ]

    domain_entities = [entity.name for entity in entities if entity.name not in {"User", "AuditEvent"}]
    services.append(
        Microservice(
            name="core-domain-service",
            responsibility="Owns primary product workflows and business invariants.",
            owns=domain_entities,
            dependencies=["postgres", "event-bus"],
        )
    )
    services.append(
        Microservice(
            name="audit-service",
            responsibility="Consumes domain events and persists searchable audit history.",
            owns=["AuditEvent"],
            dependencies=["event-bus", "postgres"],
        )
    )
    return services


def _endpoints(entities: list[Entity]) -> list[ApiEndpoint]:
    endpoints = [
        ApiEndpoint(
            method="POST",
            path="/auth/login",
            purpose="Authenticate a user and return an access token.",
            request={"email": "string", "password": "string"},
            response={"access_token": "string", "token_type": "bearer"},
        )
    ]

    for entity in entities:
        resource = _resource_name(entity.name)
        endpoints.extend(
            [
                ApiEndpoint(
                    method="GET",
                    path=f"/{resource}",
                    purpose=f"List {entity.name} records with pagination and filters.",
                    request={"limit": "integer", "cursor": "string"},
                    response={"items": f"array[{entity.name}]", "next_cursor": "string"},
                ),
                ApiEndpoint(
                    method="POST",
                    path=f"/{resource}",
                    purpose=f"Create a {entity.name} record.",
                    request={field.split(":")[0]: field.split(":")[1].strip() for field in entity.fields[:4]},
                    response={"id": "uuid", "status": "created"},
                ),
            ]
        )
    return endpoints


def _resource_name(name: str) -> str:
    snake = re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    return f"{snake}s"


def _diagram(services: list[Microservice]) -> str:
    lines = [
        "flowchart LR",
        "  client[Web / Mobile Client] --> gateway[API Gateway]",
        "  gateway --> auth[Auth Service]",
        "  gateway --> core[Core Domain Service]",
        "  core --> db[(PostgreSQL)]",
        "  auth --> db",
        "  core --> bus[Event Bus]",
        "  bus --> audit[Audit Service]",
        "  audit --> db",
        "  gateway --> obs[Observability]",
    ]
    for service in services:
        if "redis" in service.dependencies:
            lines.append("  auth --> cache[(Redis)]")
            break
    return "\n".join(lines)


def _cost_estimate(service_count: int) -> list[CostLineItem]:
    return [
        CostLineItem(component="Container compute", assumption=f"{service_count} small always-on services", monthly_usd=180),
        CostLineItem(component="PostgreSQL", assumption="Managed multi-AZ starter database", monthly_usd=120),
        CostLineItem(component="Redis", assumption="Small cache for sessions and rate limits", monthly_usd=35),
        CostLineItem(component="Event bus", assumption="Low to moderate async workload", monthly_usd=25),
        CostLineItem(component="Observability", assumption="Logs, metrics, traces with 30-day retention", monthly_usd=75),
        CostLineItem(component="Network and storage", assumption="Load balancer, object storage, backups", monthly_usd=65),
    ]


def _deployment_plan() -> list[str]:
    return [
        "Create isolated dev, staging, and production cloud accounts or projects.",
        "Provision VPC networking, managed PostgreSQL, Redis, object storage, and an event bus with Terraform.",
        "Build container images in CI and scan dependencies before publishing.",
        "Deploy services to ECS Fargate or Kubernetes behind an HTTPS load balancer.",
        "Run database migrations as a controlled release step before shifting traffic.",
        "Enable dashboards, alerts, distributed tracing, centralized logs, and backup restore checks.",
    ]


def _architecture_options() -> list[ArchitectureOption]:
    return [
        ArchitectureOption(
            name="MVP Architecture",
            description="Start with a modular monolith, PostgreSQL, background workers, and one deployable API.",
            pros=["Lowest operational cost", "Fastest delivery", "Simpler debugging"],
            cons=["Boundaries must be kept clean in code", "Independent scaling is limited"],
            recommended_for="Early validation, small teams, budget below $100/month",
        ),
        ArchitectureOption(
            name="Scalable Architecture",
            description="Use a small number of services around stable domain boundaries with shared observability.",
            pros=["Clearer ownership", "Selective scaling", "Balanced complexity"],
            cons=["Requires CI/CD discipline", "More runtime components than MVP"],
            recommended_for="Growing product with active users and a moderate budget",
        ),
        ArchitectureOption(
            name="Enterprise Architecture",
            description="Use dedicated microservices, event-driven integration, hardened security, and multi-environment infrastructure.",
            pros=["Strong isolation", "Team autonomy", "High scalability ceiling"],
            cons=["Highest cost", "Operationally complex", "Requires platform maturity"],
            recommended_for="Large teams, strict compliance, high traffic, or multi-region requirements",
        ),
    ]


def _review_findings(services: list[Microservice], costs: list[CostLineItem]) -> list[ReviewFinding]:
    total_cost = sum(item.monthly_usd for item in costs)
    findings = []
    if len(services) > 5:
        findings.append(
            ReviewFinding(
                severity="medium",
                area="Complexity",
                finding=f"The design has {len(services)} services, which may be too much for an MVP.",
                recommendation="Consider a modular monolith or combine low-change domains until traffic and team size justify separation.",
            )
        )
    if total_cost > 300:
        findings.append(
            ReviewFinding(
                severity="medium",
                area="Cost",
                finding=f"The baseline estimate is ${total_cost}/month before real traffic growth.",
                recommendation="Create a budget profile and offer a low-cost MVP deployment option.",
            )
        )
    findings.extend(
        [
            ReviewFinding(
                severity="high",
                area="Data Modeling",
                finding="Generated schemas need explicit foreign keys, indexes, and lifecycle rules before implementation.",
                recommendation="Review normalized relationships, add indexes for list/filter paths, and define cascade or archival behavior.",
            ),
            ReviewFinding(
                severity="medium",
                area="API Semantics",
                finding="CRUD endpoints are useful scaffolding but should be refined around business workflows.",
                recommendation="Add domain-specific commands such as quote pricing, approve order, reserve inventory, or invite member.",
            ),
        ]
    )
    return findings


def _scorecard(services: list[Microservice], costs: list[CostLineItem]) -> list[ScorecardItem]:
    total_cost = sum(item.monthly_usd for item in costs)
    complexity = 8 if len(services) <= 4 else 5
    cost = 8 if total_cost <= 250 else 5
    return [
        ScorecardItem(category="Complexity", score=complexity, rationale="Lower service count is easier to operate for an MVP."),
        ScorecardItem(category="Scalability", score=7, rationale="The design can scale, but scaling strategy should follow measured bottlenecks."),
        ScorecardItem(category="Maintainability", score=7, rationale="Domain ownership is clear; implementation needs clean module boundaries."),
        ScorecardItem(category="Cost", score=cost, rationale="Managed services improve reliability but can be excessive for early-stage usage."),
        ScorecardItem(category="Security", score=6, rationale="Authentication is included; secrets, RBAC, audit, and threat modeling need deeper design."),
    ]


def _non_functional_requirements() -> list[NonFunctionalRequirement]:
    return [
        NonFunctionalRequirement(category="Security", recommendation="Use RBAC, encrypted secrets, TLS everywhere, audit trails, and least-privilege IAM."),
        NonFunctionalRequirement(category="Reliability", recommendation="Define SLOs, health checks, retry policies, backups, and restore drills."),
        NonFunctionalRequirement(category="Scalability", recommendation="Start simple, monitor bottlenecks, then scale read paths, queues, and workers selectively."),
        NonFunctionalRequirement(category="Observability", recommendation="Capture structured logs, metrics, traces, dashboards, and alert rules from day one."),
        NonFunctionalRequirement(category="Data Protection", recommendation="Document retention, deletion, backup encryption, and disaster recovery objectives."),
    ]


def _architecture_decision_records() -> list[ArchitectureDecisionRecord]:
    return [
        ArchitectureDecisionRecord(
            id="ADR-001",
            decision="Use PostgreSQL as the primary database.",
            rationale="Most business workflows need transactional consistency, relational queries, and mature operational tooling.",
            alternatives=["MongoDB", "DynamoDB"],
            consequences=["Strong relational model", "Schema migrations are required", "Good fit for reporting and joins"],
        ),
        ArchitectureDecisionRecord(
            id="ADR-002",
            decision="Start with modular boundaries before splitting every domain into microservices.",
            rationale="Most early products benefit more from delivery speed and low operational burden than service isolation.",
            alternatives=["Full microservices from day one", "Single unstructured monolith"],
            consequences=["Lower MVP cost", "Clear path to extract services later", "Requires code discipline"],
        ),
        ArchitectureDecisionRecord(
            id="ADR-003",
            decision="Use asynchronous events only for workflows that do not need immediate consistency.",
            rationale="Events are valuable for notifications, audit, and reporting, but add complexity to core transactions.",
            alternatives=["Synchronous-only integration", "Event sourcing for all workflows"],
            consequences=["Simpler core flows", "Better resilience for side effects", "Requires idempotent consumers"],
        ),
    ]


def _validation_report(plan_data: dict) -> list[ValidationCheck]:
    services = [Microservice.model_validate(item) for item in plan_data["microservices"]]
    entities = [Entity.model_validate(item) for item in plan_data["database_schema"]]
    endpoints = [ApiEndpoint.model_validate(item) for item in plan_data["api_design"]]
    costs = [CostLineItem.model_validate(item) for item in plan_data["cost_estimate"]]
    total_cost = sum(item.monthly_usd for item in costs)

    return [
        ValidationCheck(
            check="Architecture complexity",
            status="warning" if len(services) > 5 else "pass",
            details=f"{len(services)} deployable service boundaries detected.",
            recommendation="Use MVP or modular monolith first unless team size and traffic justify service extraction.",
        ),
        ValidationCheck(
            check="Budget fit",
            status="warning" if total_cost > 300 else "pass",
            details=f"Estimated baseline infrastructure cost is ${total_cost}/month.",
            recommendation="Keep a low-cost deployment profile for early customers and demos.",
        ),
        ValidationCheck(
            check="Schema normalization",
            status="warning" if len(entities) < 3 else "pass",
            details=f"{len(entities)} entities generated. Relationships must be reviewed before implementation.",
            recommendation="Add explicit foreign keys, indexes, uniqueness constraints, and lifecycle rules.",
        ),
        ValidationCheck(
            check="API business semantics",
            status="warning" if all(endpoint.path.count("/") <= 1 for endpoint in endpoints) else "pass",
            details=f"{len(endpoints)} endpoints generated.",
            recommendation="Replace generic CRUD where needed with workflow APIs such as approve, reserve, quote, invite, or reconcile.",
        ),
        ValidationCheck(
            check="Non-functional coverage",
            status="pass" if plan_data.get("non_functional_requirements") else "fail",
            details="Security, reliability, scalability, observability, and data protection should be explicitly covered.",
            recommendation="Review NFRs before approving generated code or infrastructure.",
        ),
    ]

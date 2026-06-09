from app.services.architect import generate_architecture_package, generate_package_from_plan
from app.services.diagram import normalize_mermaid, service_diagram
from app.services.render import package_to_zip


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return (
            b'{"choices":[{"message":{"content":"{'
            b'\\"project_name\\":\\"LLM Planned Platform\\",'
            b'\\"summary\\":\\"LLM generated architecture plan.\\",'
            b'\\"architecture_diagram_mermaid\\":\\"flowchart LR\\\\n  client --> api\\",'
            b'\\"database_schema\\":[{\\"name\\":\\"User\\",\\"fields\\":[\\"id: uuid\\"],\\"relationships\\":[]}],'
            b'\\"api_design\\":[{\\"method\\":\\"GET\\",\\"path\\":\\"/users\\",\\"purpose\\":\\"List users\\",\\"request\\":{},\\"response\\":{\\"items\\":\\"array[User]\\"}}],'
            b'\\"microservices\\":[{\\"name\\":\\"user-service\\",\\"responsibility\\":\\"Manage users\\",\\"owns\\":[\\"User\\"],\\"dependencies\\":[\\"postgres\\"]}],'
            b'\\"cost_estimate\\":[{\\"component\\":\\"PostgreSQL\\",\\"assumption\\":\\"Managed database\\",\\"monthly_usd\\":120}],'
            b'\\"deployment_plan\\":[\\"Deploy with containers\\"]'
            b'}"}}]}'
        )


def test_generates_domain_specific_architecture() -> None:
    package = generate_architecture_package(
        "# Order Platform\nUsers can place orders and payments.",
        "As a buyer, I want to submit payment for an order.",
    )

    entity_names = {entity.name for entity in package.database_schema}
    assert {"User", "Order", "Payment", "AuditEvent"}.issubset(entity_names)
    assert "flowchart LR" in package.architecture_diagram_mermaid
    assert package.generation_mode == "deterministic-fallback"
    assert package.generated_files.fastapi_code["generated_fastapi/app/main.py"]
    assert package.generated_files.fastapi_code["generated_fastapi/openapi.yaml"]
    assert package.architecture_options
    assert package.review_findings
    assert package.scorecard
    assert package.non_functional_requirements
    assert package.architecture_decision_records
    assert package.validation_report
    assert package.generated_files.react_frontend
    assert package.generated_files.database_files


def test_package_zip_contains_artifacts() -> None:
    package = generate_architecture_package("Inventory app", "As an operator, I manage inventory.")
    zipped = package_to_zip(package)

    assert len(zipped) > 500


def test_uses_llm_plan_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("app.services.llm.urlopen", lambda *_args, **_kwargs: FakeResponse())

    package = generate_architecture_package("Anything", "As a user, I want useful software.")

    assert package.generation_mode == "hybrid-llm"
    assert package.project_name == "LLM Planned Platform"
    assert "generated_fastapi/app/main.py" in package.generated_files.fastapi_code
    assert package.review_findings


def test_normalizes_single_line_mermaid() -> None:
    source = "flowchart LR U[User] --> APIGW[API Gateway] APIGW --> CF[Catalog Service] classDef cloud fill:#eef6ff,stroke:#cbd5e1 class APIGW,CF cloud"

    normalized = normalize_mermaid(source)

    assert "flowchart LR\n" in normalized
    assert "\n  APIGW --> CF[Catalog Service]" in normalized
    assert "\n  classDef cloud" in normalized


def test_normalizes_inline_database_node_definitions() -> None:
    source = "flowchart LR CF --> DB CatalogDB[(Postgres - Catalog DB)] PF --> DB PricingDB[(Postgres - Pricing DB)]"

    normalized = normalize_mermaid(source)

    assert "\n  CatalogDB[(Postgres - Catalog DB)]" in normalized
    assert "\n  PF --> DB" in normalized
    assert "\n  PricingDB[(Postgres - Pricing DB)]" in normalized


def test_service_diagram_uses_safe_labels() -> None:
    package = generate_architecture_package(
        "Natural rubber app with pricing and procurement",
        "As a buyer, I want catalog and pricing workflows.",
    )

    diagram = service_diagram(package.microservices)

    assert 'client["Web and Mobile Client"]' in diagram
    assert "flowchart LR" in diagram
    assert "PostgreSQL" in diagram


def test_approved_plan_regenerates_full_stack_files() -> None:
    package = generate_architecture_package("Inventory app", "As an operator, I manage inventory.")

    approved = generate_package_from_plan(package)

    assert approved.generation_mode == "approved-edit"
    assert "generated_react/src/main.jsx" in approved.generated_files.react_frontend
    assert "generated_database/schema.sql" in approved.generated_files.database_files
    assert "generated_docker/docker-compose.yml" in approved.generated_files.docker_files

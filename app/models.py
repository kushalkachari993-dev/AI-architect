from pydantic import BaseModel, Field


class Entity(BaseModel):
    name: str
    fields: list[str]
    relationships: list[str] = Field(default_factory=list)


class ApiEndpoint(BaseModel):
    method: str
    path: str
    purpose: str
    request: dict[str, str]
    response: dict[str, str]


class Microservice(BaseModel):
    name: str
    responsibility: str
    owns: list[str]
    dependencies: list[str]


class CostLineItem(BaseModel):
    component: str
    assumption: str
    monthly_usd: int


class ArchitectureOption(BaseModel):
    name: str
    description: str
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    recommended_for: str


class ReviewFinding(BaseModel):
    severity: str
    area: str
    finding: str
    recommendation: str


class ScorecardItem(BaseModel):
    category: str
    score: int
    rationale: str


class NonFunctionalRequirement(BaseModel):
    category: str
    recommendation: str


class ArchitectureDecisionRecord(BaseModel):
    id: str
    decision: str
    rationale: str
    alternatives: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class ValidationCheck(BaseModel):
    check: str
    status: str
    details: str
    recommendation: str


class GeneratedFiles(BaseModel):
    fastapi_code: dict[str, str] = Field(default_factory=dict)
    react_frontend: dict[str, str] = Field(default_factory=dict)
    database_files: dict[str, str] = Field(default_factory=dict)
    docker_files: dict[str, str] = Field(default_factory=dict)
    terraform: dict[str, str] = Field(default_factory=dict)


class ArchitecturePlan(BaseModel):
    project_name: str
    summary: str
    architecture_diagram_mermaid: str
    database_schema: list[Entity]
    api_design: list[ApiEndpoint]
    microservices: list[Microservice]
    cost_estimate: list[CostLineItem]
    deployment_plan: list[str]
    architecture_options: list[ArchitectureOption] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    scorecard: list[ScorecardItem] = Field(default_factory=list)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(default_factory=list)
    architecture_decision_records: list[ArchitectureDecisionRecord] = Field(default_factory=list)
    validation_report: list[ValidationCheck] = Field(default_factory=list)


class ArchitecturePackage(ArchitecturePlan):
    generation_mode: str
    generated_files: GeneratedFiles

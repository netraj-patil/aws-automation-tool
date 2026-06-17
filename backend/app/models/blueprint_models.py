"""Data models for CloudForge deployment blueprints."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    NonNegativeFloat,
    conint,
    root_validator,
)


BlueprintStatus = Literal[
    "draft",
    "saved",
    "approved",
    "deploying",
    "deployed",
    "failed",
    "cancelled",
]
RiskLevel = Literal["low", "medium", "high", "critical"]
ResourceVisibility = Literal["public", "private", "internal"]
DeploymentStatus = Literal["deploying", "deployed", "failed", "cancelled"]
WarningSeverity = Literal["info", "low", "medium", "high", "critical"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictBlueprintModel(BaseModel):
    """Shared strict model behavior for planner-facing contracts."""

    class Config:
        extra = "forbid"
        allow_population_by_field_name = True
        populate_by_name = True


class CostEstimate(StrictBlueprintModel):
    """Estimated monthly cost for a blueprint or resource group."""

    currency: str = Field(default="USD", min_length=3, max_length=3)
    estimated_monthly_total: NonNegativeFloat
    breakdown: dict[str, NonNegativeFloat] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class SecurityWarning(StrictBlueprintModel):
    """A security concern found while reviewing the blueprint."""

    severity: WarningSeverity
    message: str = Field(min_length=1)
    resource_id: str | None = None
    recommendation: str | None = None


class SecurityReview(StrictBlueprintModel):
    """Security summary for a blueprint before deployment."""

    risk_level: RiskLevel
    security_score: conint(ge=0, le=100) = 100
    passed: bool
    warnings: list[SecurityWarning] = Field(default_factory=list)
    summary: str = ""


class BlueprintResource(StrictBlueprintModel):
    """A cloud resource described by a deployment blueprint."""

    id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    service: str = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    visibility: ResourceVisibility
    estimated_monthly_cost: NonNegativeFloat
    risk_level: RiskLevel


class BlueprintConnection(StrictBlueprintModel):
    """A directional relationship between two blueprint resources."""

    from_resource: str = Field(
        min_length=1,
        alias="from",
    )
    to_resource: str = Field(
        min_length=1,
        alias="to",
    )
    type: str = Field(min_length=1)
    description: str = Field(min_length=1)


class DeploymentRecord(StrictBlueprintModel):
    """Deployment lifecycle record for a blueprint execution attempt."""

    record_id: str = Field(min_length=1)
    blueprint_id: str = Field(min_length=1)
    status: DeploymentStatus
    started_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None
    logs: list[str] = Field(default_factory=list)
    error: str | None = None

    @root_validator(skip_on_failure=True)
    def validate_finished_after_started(cls, values: dict) -> dict:
        started_at = values.get("started_at")
        finished_at = values.get("finished_at")
        if finished_at and started_at and finished_at < started_at:
            raise ValueError("finished_at must be after started_at")
        return values


class DeploymentBlueprint(StrictBlueprintModel):
    """First-class cloud architecture plan produced before execution."""

    blueprint_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    status: BlueprintStatus
    user_prompt: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    resources: list[BlueprintResource] = Field(default_factory=list)
    connections: list[BlueprintConnection] = Field(default_factory=list)
    diagram_mermaid: str | None = None
    estimated_cost: CostEstimate
    security_review: SecurityReview
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @root_validator(skip_on_failure=True)
    def validate_updated_after_created(cls, values: dict) -> dict:
        created_at = values.get("created_at")
        updated_at = values.get("updated_at")
        if created_at and updated_at and updated_at < created_at:
            raise ValueError("updated_at must be after created_at")
        return values


DeploymentLog = DeploymentRecord

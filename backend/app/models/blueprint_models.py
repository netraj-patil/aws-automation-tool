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

from app.models.deployment_models import (
    DeploymentLog,
    DeploymentRecord,
    DeploymentResource,
    DeploymentStatus,
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

class BlueprintExecutionRequest(StrictBlueprintModel):
    """Request body for executing an approved deployment blueprint."""

    override_high_risk: bool = False


class PlannedResource(DeploymentResource):
    """A dry-run resource action planned from a blueprint resource."""


class BlueprintExecutionResponse(StrictBlueprintModel):
    """Response returned after a blueprint execution attempt."""

    deployment_id: str = Field(min_length=1)
    blueprint_id: str = Field(min_length=1)
    status: DeploymentStatus
    logs: list[str] = Field(default_factory=list)
    planned_resources: list[PlannedResource] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

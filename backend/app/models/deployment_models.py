"""Data models for CloudForge deployment execution records."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, root_validator


DeploymentStatus = Literal["deploying", "deployed", "failed", "cancelled"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictDeploymentModel(BaseModel):
    """Shared strict model behavior for deployment-facing contracts."""

    class Config:
        extra = "forbid"
        allow_population_by_field_name = True
        populate_by_name = True


class DeploymentResource(StrictDeploymentModel):
    """A resource captured on a deployment execution record."""

    resource_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    service: str = Field(min_length=1)
    type: str = Field(min_length=1)
    action: str = Field(default="prepare")


class DeploymentRecord(StrictDeploymentModel):
    """Persistent lifecycle record for a blueprint execution attempt."""

    deployment_id: str = Field(min_length=1)
    blueprint_id: str = Field(min_length=1)
    status: DeploymentStatus
    logs: list[str] = Field(default_factory=list)
    planned_resources: list[DeploymentResource] = Field(default_factory=list)
    aws_resources: list[dict[str, Any]] = Field(default_factory=list)
    error: str | None = None
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

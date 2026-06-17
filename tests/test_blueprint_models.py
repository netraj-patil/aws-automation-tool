"""Unit tests for CloudForge blueprint data contracts."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.blueprint_models import (
    BlueprintConnection,
    BlueprintResource,
    CostEstimate,
    DeploymentBlueprint,
    SecurityReview,
    SecurityWarning,
)


def _resource() -> dict:
    return {
        "id": "vpc-main",
        "type": "network",
        "name": "main-vpc",
        "service": "ec2",
        "config": {
            "cidr_block": "10.0.0.0/16",
            "tags": {"environment": "dev"},
        },
        "visibility": "private",
        "estimated_monthly_cost": 0,
        "risk_level": "low",
    }


def _blueprint() -> dict:
    return {
        "blueprint_id": "bp-123",
        "name": "Static site foundation",
        "status": "draft",
        "user_prompt": "Create a private VPC for a static site.",
        "summary": "Private networking foundation for future resources.",
        "resources": [_resource()],
        "connections": [
            {
                "from": "vpc-main",
                "to": "subnet-public",
                "type": "contains",
                "description": "VPC contains the public subnet.",
            }
        ],
        "diagram_mermaid": "graph TD\n  vpc-main --> subnet-public",
        "estimated_cost": {
            "estimated_monthly_total": 0,
            "breakdown": {"vpc-main": 0},
            "assumptions": ["No paid resources are included yet."],
        },
        "security_review": {
            "risk_level": "low",
            "passed": True,
            "warnings": [],
            "summary": "No public resources in this blueprint.",
        },
    }


def test_blueprint_accepts_valid_statuses() -> None:
    for status in (
        "draft",
        "saved",
        "approved",
        "deploying",
        "deployed",
        "failed",
        "cancelled",
    ):
        blueprint = DeploymentBlueprint(**{**_blueprint(), "status": status})

        assert blueprint.status == status


def test_blueprint_rejects_invalid_status() -> None:
    with pytest.raises(ValidationError):
        DeploymentBlueprint(**{**_blueprint(), "status": "running"})


def test_resource_shape_is_strict_but_config_is_flexible() -> None:
    resource = BlueprintResource(**_resource())

    assert resource.config["tags"]["environment"] == "dev"

    with pytest.raises(ValidationError):
        BlueprintResource(**{**_resource(), "estimated_monthly_cost": -1})

    with pytest.raises(ValidationError):
        BlueprintResource(**{**_resource(), "unexpected": "planner noise"})


def test_connection_shape_supports_python_names_and_api_aliases() -> None:
    python_named = BlueprintConnection(
        from_resource="vpc-main",
        to_resource="subnet-public",
        type="contains",
        description="VPC contains the public subnet.",
    )
    api_named = BlueprintConnection(
        **{
            "from": "subnet-public",
            "to": "internet-gateway",
            "type": "routes-to",
            "description": "Subnet routes through the gateway.",
        }
    )

    assert python_named.from_resource == "vpc-main"
    assert api_named.to_resource == "internet-gateway"
    assert api_named.dict(by_alias=True)["from"] == "subnet-public"

    with pytest.raises(ValidationError):
        BlueprintConnection(
            **{
                "from": "vpc-main",
                "to": "subnet-public",
                "type": "contains",
            }
        )


def test_complete_blueprint_preserves_nested_models() -> None:
    blueprint = DeploymentBlueprint(**_blueprint())

    assert blueprint.resources[0].id == "vpc-main"
    assert blueprint.connections[0].from_resource == "vpc-main"
    assert isinstance(blueprint.estimated_cost, CostEstimate)
    assert isinstance(blueprint.security_review, SecurityReview)


def test_security_warning_and_timestamp_validation() -> None:
    warning = SecurityWarning(
        severity="medium",
        message="S3 bucket should block public access.",
        resource_id="bucket-assets",
        recommendation="Enable block public access.",
    )

    assert warning.severity == "medium"

    with pytest.raises(ValidationError):
        DeploymentBlueprint(
            **{
                **_blueprint(),
                "created_at": datetime(2026, 1, 2, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        )

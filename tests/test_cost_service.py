"""Unit tests for static blueprint cost estimation."""

from app.models.blueprint_models import (
    CostEstimate,
    DeploymentBlueprint,
    SecurityReview,
)
from app.services.cost_service import CostService


def _blueprint(resources: list[dict]) -> DeploymentBlueprint:
    return DeploymentBlueprint(
        blueprint_id="bp_cost_test",
        name="Cost Test Blueprint",
        status="draft",
        user_prompt="Estimate cost.",
        summary="Blueprint used for cost tests.",
        resources=resources,
        connections=[],
        diagram_mermaid=None,
        estimated_cost=CostEstimate(
            estimated_monthly_total=0,
            breakdown={},
            assumptions=[],
        ),
        security_review=SecurityReview(
            risk_level="low",
            passed=True,
            warnings=[],
            summary="Not reviewed.",
        ),
    )


def _resource(resource_id: str, service: str, resource_type: str) -> dict:
    return {
        "id": resource_id,
        "type": resource_type,
        "name": resource_id.replace("-", " "),
        "service": service,
        "config": {},
        "visibility": "private",
        "estimated_monthly_cost": 0,
        "risk_level": "low",
    }


def test_cost_total_is_calculated_from_static_prices() -> None:
    blueprint = _blueprint(
        [
            _resource("app-compute", "ecs", "compute"),
            _resource("postgres-database", "rds", "database"),
            _resource("object-storage", "s3", "storage"),
            _resource("https-load-balancer", "elasticloadbalancing", "load_balancer"),
            _resource("monitoring", "cloudwatch", "monitoring"),
        ]
    )

    estimated = CostService().estimate(blueprint)

    assert estimated.estimated_cost.estimated_monthly_total == 46
    assert estimated.estimated_cost.breakdown == {
        "app-compute": 8,
        "postgres-database": 15,
        "object-storage": 2,
        "https-load-balancer": 18,
        "monitoring": 3,
    }
    assert estimated.resources[0].estimated_monthly_cost == 8

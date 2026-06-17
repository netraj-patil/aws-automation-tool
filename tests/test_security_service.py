"""Unit tests for rule-based blueprint security review."""

from app.models.blueprint_models import (
    CostEstimate,
    DeploymentBlueprint,
    SecurityReview,
)
from app.services.security_service import SecurityService


def _blueprint(resources: list[dict]) -> DeploymentBlueprint:
    return DeploymentBlueprint(
        blueprint_id="bp_security_test",
        name="Security Test Blueprint",
        status="draft",
        user_prompt="Review security.",
        summary="Blueprint used for security tests.",
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


def _resource(
    resource_id: str,
    service: str,
    resource_type: str,
    *,
    visibility: str = "private",
    config: dict | None = None,
) -> dict:
    return {
        "id": resource_id,
        "type": resource_type,
        "name": resource_id.replace("-", " "),
        "service": service,
        "config": config or {},
        "visibility": visibility,
        "estimated_monthly_cost": 0,
        "risk_level": "low",
    }


def test_public_s3_and_rds_create_high_warnings() -> None:
    blueprint = _blueprint(
        [
            _resource(
                "postgres-database",
                "rds",
                "database",
                visibility="public",
                config={"backup_retention_days": 7},
            ),
            _resource(
                "object-storage",
                "s3",
                "storage",
                visibility="public",
            ),
            _resource(
                "https-load-balancer",
                "elasticloadbalancing",
                "load_balancer",
                visibility="public",
                config={"listener_protocol": "HTTPS"},
            ),
            _resource("monitoring", "cloudwatch", "monitoring"),
        ]
    )

    reviewed = SecurityService().review(blueprint)
    high_warnings = [
        warning for warning in reviewed.security_review.warnings if warning.severity == "high"
    ]

    assert {warning.resource_id for warning in high_warnings} == {
        "postgres-database",
        "object-storage",
    }
    assert reviewed.security_review.risk_level == "high"
    assert reviewed.resources[0].risk_level == "high"
    assert reviewed.resources[1].risk_level == "high"


def test_missing_monitoring_creates_medium_warning() -> None:
    blueprint = _blueprint(
        [
            _resource(
                "https-load-balancer",
                "elasticloadbalancing",
                "load_balancer",
                visibility="public",
                config={"listener_protocol": "HTTPS"},
            )
        ]
    )

    reviewed = SecurityService().review(blueprint)

    assert any(
        warning.severity == "medium" and "monitoring" in warning.message.lower()
        for warning in reviewed.security_review.warnings
    )
    assert reviewed.security_review.security_score < 100

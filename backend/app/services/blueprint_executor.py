"""Dry-run execution for approved deployment blueprints."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3
from pydantic import ValidationError

from app.models.blueprint_models import (
    BlueprintExecutionResponse,
    DeploymentBlueprint,
    PlannedResource,
)


class BlueprintValidationError(ValueError):
    """Raised when a stored blueprint no longer matches the schema."""


class MissingAwsCredentialsError(ValueError):
    """Raised when no usable AWS credentials are available."""


class BlueprintExecutor:
    """Execute deployment blueprints using a safe dry-run strategy."""

    def validate_blueprint(
        self, blueprint: DeploymentBlueprint
    ) -> DeploymentBlueprint:
        """Re-validate a blueprint before it is allowed to execute."""
        try:
            payload = self._dump_blueprint(blueprint)
            if hasattr(DeploymentBlueprint, "model_validate"):
                return DeploymentBlueprint.model_validate(payload)
            return DeploymentBlueprint.parse_obj(payload)
        except ValidationError as exc:
            raise BlueprintValidationError(str(exc)) from exc

    def check_credentials(
        self, credentials: dict[str, str | None]
    ) -> None:
        """Build a boto3 session from request/profile credentials."""
        session_kwargs = {
            key: value
            for key, value in credentials.items()
            if value and key in {
                "aws_access_key_id",
                "aws_secret_access_key",
                "aws_session_token",
            }
        }
        session = boto3.Session(**session_kwargs)
        if session.get_credentials() is None:
            raise MissingAwsCredentialsError(
                "AWS credentials are required before blueprint execution."
            )

    def has_high_risk_warnings(
        self, blueprint: DeploymentBlueprint
    ) -> bool:
        """Return True when the security review contains high-risk warnings."""
        warnings = blueprint.security_review.warnings
        return any(
            warning.severity in {"high", "critical"}
            for warning in warnings
        )

    def dry_run(
        self,
        blueprint: DeploymentBlueprint,
        *,
        override_high_risk: bool = False,
    ) -> BlueprintExecutionResponse:
        """Return ordered dry-run logs and resources from the blueprint."""
        now = datetime.now(timezone.utc)
        logs = [
            "Validating blueprint",
            "Checking approval",
            "Reviewing security warnings",
        ]
        if override_high_risk:
            logs.append("High-risk override accepted for dry-run execution")

        if blueprint.connections:
            logs.append(
                f"Resolving {len(blueprint.connections)} blueprint connections"
            )

        for label, resources in self._resource_groups(blueprint).items():
            if resources:
                logs.append(label)

        logs.append("Deployment dry-run completed")
        return BlueprintExecutionResponse(
            deployment_id=f"dep_{uuid4().hex[:12]}",
            blueprint_id=blueprint.blueprint_id,
            status="deployed",
            logs=logs,
            planned_resources=[
                PlannedResource(
                    resource_id=resource.id,
                    name=resource.name,
                    service=resource.service,
                    type=resource.type,
                )
                for resource in blueprint.resources
            ],
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _dump_blueprint(blueprint: DeploymentBlueprint) -> dict[str, Any]:
        if hasattr(blueprint, "model_dump"):
            return blueprint.model_dump(by_alias=True)
        return blueprint.dict(by_alias=True)

    @staticmethod
    def _resource_groups(
        blueprint: DeploymentBlueprint,
    ) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "Preparing network resources": [],
            "Preparing load balancer": [],
            "Preparing compute resources": [],
            "Preparing database": [],
            "Preparing storage": [],
            "Preparing monitoring": [],
            "Preparing additional resources": [],
        }

        for resource in blueprint.resources:
            haystack = " ".join(
                [
                    resource.id,
                    resource.name,
                    resource.service,
                    resource.type,
                    str(resource.config),
                ]
            ).lower()

            if any(
                term in haystack
                for term in [
                    "vpc",
                    "subnet",
                    "route",
                    "gateway",
                    "nat",
                    "security group",
                    "security_group",
                    "network",
                ]
            ):
                groups["Preparing network resources"].append(resource.id)
            elif any(term in haystack for term in ["load", "balancer", "alb", "elb"]):
                groups["Preparing load balancer"].append(resource.id)
            elif any(
                term in haystack
                for term in [
                    "ec2",
                    "ecs",
                    "fargate",
                    "lambda",
                    "compute",
                    "autoscaling",
                    "application",
                    "app",
                ]
            ):
                groups["Preparing compute resources"].append(resource.id)
            elif any(
                term in haystack
                for term in [
                    "rds",
                    "aurora",
                    "database",
                    "postgres",
                    "mysql",
                    "dynamodb",
                    "db",
                ]
            ):
                groups["Preparing database"].append(resource.id)
            elif any(
                term in haystack
                for term in ["s3", "bucket", "storage", "efs", "volume"]
            ):
                groups["Preparing storage"].append(resource.id)
            elif any(
                term in haystack
                for term in [
                    "cloudwatch",
                    "monitoring",
                    "alarm",
                    "metric",
                    "log",
                ]
            ):
                groups["Preparing monitoring"].append(resource.id)
            else:
                groups["Preparing additional resources"].append(resource.id)

        return groups


blueprint_executor = BlueprintExecutor()

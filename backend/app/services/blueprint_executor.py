"""Dry-run execution for approved deployment blueprints."""

from typing import Any

import boto3
from pydantic import ValidationError

from app.models.blueprint_models import (
    BlueprintExecutionResponse,
    DeploymentBlueprint,
    PlannedResource,
)
from app.services.aws_credentials import (
    MissingAwsCredentialsError,
    explicit_session_kwargs,
)


class BlueprintValidationError(ValueError):
    """Raised when a stored blueprint no longer matches the schema."""


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
        """Build a boto3 session from user-provided credentials only."""
        session_kwargs = explicit_session_kwargs(credentials)
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
            deployment_id="pending",
            blueprint_id=blueprint.blueprint_id,
            status="deployed",
            logs=logs,
            planned_resources=self.planned_resources(blueprint),
        )

    def planned_resources(
        self,
        blueprint: DeploymentBlueprint,
    ) -> list[PlannedResource]:
        """Return dry-run resource actions for the blueprint."""
        return [
            PlannedResource(
                resource_id=resource.id,
                name=resource.name,
                service=resource.service,
                type=resource.type,
            )
            for resource in blueprint.resources
        ]

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

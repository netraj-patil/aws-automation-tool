"""In-memory storage for CloudForge deployment execution records."""

from datetime import datetime, timezone
from uuid import uuid4

from app.models.deployment_models import (
    DeploymentRecord,
    DeploymentResource,
    DeploymentStatus,
)


class DeploymentNotFoundError(KeyError):
    """Raised when an operation references an unknown deployment ID."""


class InvalidDeploymentTransitionError(ValueError):
    """Raised when a deployment lifecycle transition is not allowed."""


class DeploymentStore:
    """Store deployment records by deployment ID."""

    def __init__(self) -> None:
        self._deployments: dict[str, DeploymentRecord] = {}
        self._blueprint_index: dict[str, list[str]] = {}

    def create(
        self,
        blueprint_id: str,
        *,
        planned_resources: list[DeploymentResource] | None = None,
        aws_resources: list[dict] | None = None,
    ) -> DeploymentRecord:
        """Create a deploying record for a blueprint execution attempt."""
        now = self._utc_now()
        deployment = DeploymentRecord(
            deployment_id=self._new_deployment_id(),
            blueprint_id=blueprint_id,
            status="deploying",
            planned_resources=planned_resources or [],
            aws_resources=aws_resources or [],
            created_at=now,
            updated_at=now,
        )
        self._deployments[deployment.deployment_id] = deployment
        self._blueprint_index.setdefault(blueprint_id, []).append(
            deployment.deployment_id
        )
        return self._copy_deployment(deployment)

    def get(self, deployment_id: str) -> DeploymentRecord:
        """Return a copy of the requested deployment record."""
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(deployment_id)
        return self._copy_deployment(deployment)

    def list_for_blueprint(self, blueprint_id: str) -> list[DeploymentRecord]:
        """Return deployment records for a blueprint, newest first."""
        deployment_ids = self._blueprint_index.get(blueprint_id, [])
        deployments = [
            self._deployments[deployment_id]
            for deployment_id in deployment_ids
            if deployment_id in self._deployments
        ]
        return [
            self._copy_deployment(deployment)
            for deployment in sorted(
                deployments,
                key=lambda deployment: deployment.created_at,
                reverse=True,
            )
        ]

    def list_all(self) -> list[DeploymentRecord]:
        """Return all deployment records, newest first."""
        return [
            self._copy_deployment(deployment)
            for deployment in sorted(
                self._deployments.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
        ]

    def append_log(
        self,
        deployment_id: str,
        message: str,
    ) -> DeploymentRecord:
        """Append one ordered log message to a deployment record."""
        deployment = self._get_mutable(deployment_id)
        deployment.logs.append(message)
        deployment.updated_at = self._utc_now()
        return self._copy_deployment(deployment)

    def complete(
        self,
        deployment_id: str,
        *,
        planned_resources: list[DeploymentResource] | None = None,
        aws_resources: list[dict] | None = None,
    ) -> DeploymentRecord:
        """Mark a deploying record as deployed."""
        return self._finalize(
            deployment_id,
            "deployed",
            planned_resources=planned_resources,
            aws_resources=aws_resources,
        )

    def fail(
        self,
        deployment_id: str,
        error: str,
        *,
        planned_resources: list[DeploymentResource] | None = None,
        aws_resources: list[dict] | None = None,
    ) -> DeploymentRecord:
        """Mark a deploying record as failed and append the error log."""
        deployment = self._get_mutable(deployment_id)
        if not deployment.logs or deployment.logs[-1] != error:
            deployment.logs.append(error)
        deployment.error = error
        return self._finalize(
            deployment_id,
            "failed",
            planned_resources=planned_resources,
            aws_resources=aws_resources,
        )

    def cancel(self, deployment_id: str) -> DeploymentRecord:
        """Mark a deploying record as cancelled."""
        return self._finalize(deployment_id, "cancelled")

    def clear_all(self) -> None:
        """Delete all deployment records; intended for tests only."""
        self._deployments.clear()
        self._blueprint_index.clear()

    def _finalize(
        self,
        deployment_id: str,
        status: DeploymentStatus,
        *,
        planned_resources: list[DeploymentResource] | None = None,
        aws_resources: list[dict] | None = None,
    ) -> DeploymentRecord:
        deployment = self._get_mutable(deployment_id)
        if deployment.status != "deploying":
            raise InvalidDeploymentTransitionError(
                f"Cannot mark deployment from status '{deployment.status}'"
            )

        deployment.status = status
        if planned_resources is not None:
            deployment.planned_resources = planned_resources
        if aws_resources is not None:
            deployment.aws_resources = aws_resources
        deployment.updated_at = self._utc_now()
        return self._copy_deployment(deployment)

    @staticmethod
    def _new_deployment_id() -> str:
        return f"dep_{uuid4().hex[:12]}"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _copy_deployment(deployment: DeploymentRecord) -> DeploymentRecord:
        if hasattr(deployment, "model_copy"):
            return deployment.model_copy(deep=True)
        return deployment.copy(deep=True)

    def _get_mutable(self, deployment_id: str) -> DeploymentRecord:
        deployment = self._deployments.get(deployment_id)
        if deployment is None:
            raise DeploymentNotFoundError(deployment_id)
        return deployment


deployment_store = DeploymentStore()

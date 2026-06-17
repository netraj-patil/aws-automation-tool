"""In-memory storage for deployment blueprints."""

from datetime import datetime, timezone
from uuid import uuid4

from app.models.blueprint_models import (
    CostEstimate,
    DeploymentBlueprint,
    SecurityReview,
)


class BlueprintNotFoundError(KeyError):
    """Raised when an operation references an unknown blueprint ID."""


class InvalidBlueprintTransitionError(ValueError):
    """Raised when a blueprint lifecycle transition is not allowed."""


class BlueprintStore:
    """Store deployment blueprints by blueprint ID."""

    def __init__(self) -> None:
        self._blueprints: dict[str, DeploymentBlueprint] = {}

    def create_from_prompt(self, prompt: str) -> DeploymentBlueprint:
        """Create a placeholder draft blueprint from the user's prompt."""
        blueprint_id = self._new_blueprint_id()
        blueprint = DeploymentBlueprint(
            blueprint_id=blueprint_id,
            name="Draft Deployment Blueprint",
            status="draft",
            user_prompt=prompt,
            summary="Placeholder deployment blueprint generated from the prompt.",
            resources=[],
            connections=[],
            diagram_mermaid=None,
            estimated_cost=CostEstimate(
                estimated_monthly_total=0,
                breakdown={},
                assumptions=["Placeholder estimate until the planner runs."],
            ),
            security_review=SecurityReview(
                risk_level="low",
                passed=True,
                warnings=[],
                summary="Placeholder review until the planner runs.",
            ),
        )
        self._blueprints[blueprint_id] = blueprint
        return self._copy_blueprint(blueprint)

    def add(self, blueprint: DeploymentBlueprint) -> DeploymentBlueprint:
        """Store an already-generated deployment blueprint."""
        self._blueprints[blueprint.blueprint_id] = self._copy_blueprint(blueprint)
        return self._copy_blueprint(blueprint)

    def get(self, blueprint_id: str) -> DeploymentBlueprint:
        """Return a copy of the requested blueprint."""
        blueprint = self._blueprints.get(blueprint_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        return self._copy_blueprint(blueprint)

    def save(self, blueprint_id: str) -> DeploymentBlueprint:
        """Move a draft blueprint into the saved state."""
        blueprint = self._get_mutable(blueprint_id)
        if blueprint.status != "draft":
            raise InvalidBlueprintTransitionError(
                f"Cannot save blueprint from status '{blueprint.status}'"
            )

        blueprint.status = "saved"
        blueprint.updated_at = self._utc_now()
        return self._copy_blueprint(blueprint)

    def approve(self, blueprint_id: str) -> DeploymentBlueprint:
        """Approve a draft or saved blueprint."""
        blueprint = self._get_mutable(blueprint_id)
        if blueprint.status not in {"draft", "saved"}:
            raise InvalidBlueprintTransitionError(
                f"Cannot approve blueprint from status '{blueprint.status}'"
            )

        blueprint.status = "approved"
        blueprint.updated_at = self._utc_now()
        return self._copy_blueprint(blueprint)

    def mark_deploying(self, blueprint_id: str) -> DeploymentBlueprint:
        """Move an approved blueprint into the deploying state."""
        blueprint = self._get_mutable(blueprint_id)
        if blueprint.status != "approved":
            raise InvalidBlueprintTransitionError(
                f"Cannot deploy blueprint from status '{blueprint.status}'"
            )

        blueprint.status = "deploying"
        blueprint.updated_at = self._utc_now()
        return self._copy_blueprint(blueprint)

    def mark_deployed(self, blueprint_id: str) -> DeploymentBlueprint:
        """Move a deploying blueprint into the deployed state."""
        blueprint = self._get_mutable(blueprint_id)
        if blueprint.status != "deploying":
            raise InvalidBlueprintTransitionError(
                f"Cannot complete blueprint from status '{blueprint.status}'"
            )

        blueprint.status = "deployed"
        blueprint.updated_at = self._utc_now()
        return self._copy_blueprint(blueprint)

    def mark_failed(self, blueprint_id: str) -> DeploymentBlueprint:
        """Move a deploying blueprint into the failed state."""
        blueprint = self._get_mutable(blueprint_id)
        if blueprint.status != "deploying":
            raise InvalidBlueprintTransitionError(
                f"Cannot fail blueprint from status '{blueprint.status}'"
            )

        blueprint.status = "failed"
        blueprint.updated_at = self._utc_now()
        return self._copy_blueprint(blueprint)

    def clear_all(self) -> None:
        """Delete all blueprints in this store; intended for tests only."""
        self._blueprints.clear()

    @staticmethod
    def _new_blueprint_id() -> str:
        return f"bp_{uuid4().hex[:12]}"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _copy_blueprint(
        blueprint: DeploymentBlueprint,
    ) -> DeploymentBlueprint:
        if hasattr(blueprint, "model_copy"):
            return blueprint.model_copy(deep=True)
        return blueprint.copy(deep=True)

    def _get_mutable(self, blueprint_id: str) -> DeploymentBlueprint:
        blueprint = self._blueprints.get(blueprint_id)
        if blueprint is None:
            raise BlueprintNotFoundError(blueprint_id)
        return blueprint


blueprint_store = BlueprintStore()

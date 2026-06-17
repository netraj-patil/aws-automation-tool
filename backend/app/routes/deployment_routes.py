"""HTTP routes for deployment execution records."""

from fastapi import APIRouter, HTTPException, status

from app.models.agent_models import ErrorResponse
from app.models.deployment_models import DeploymentRecord
from app.services.deployment_store import (
    DeploymentNotFoundError,
    deployment_store,
)


router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])


def _not_found(exc: DeploymentNotFoundError) -> HTTPException:
    deployment_id = exc.args[0] if exc.args else None
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "Deployment not found",
            "detail": str(deployment_id) if deployment_id else None,
        },
    )


@router.get(
    "/{deployment_id}",
    response_model=DeploymentRecord,
    responses={404: {"model": ErrorResponse}},
)
def get_deployment(deployment_id: str) -> DeploymentRecord:
    """Return a stored deployment record."""
    try:
        return deployment_store.get(deployment_id)
    except DeploymentNotFoundError as exc:
        raise _not_found(exc) from exc

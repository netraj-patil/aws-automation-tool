"""HTTP routes for deployment blueprint drafts and approvals."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.agent_models import ErrorResponse
from app.models.blueprint_models import DeploymentBlueprint
from app.services.blueprint_store import (
    BlueprintNotFoundError,
    InvalidBlueprintTransitionError,
    blueprint_store,
)


router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])


class GenerateBlueprintRequest(BaseModel):
    """Request body for creating a draft deployment blueprint."""

    prompt: str = Field(min_length=1)


def _not_found(exc: BlueprintNotFoundError) -> HTTPException:
    blueprint_id = exc.args[0] if exc.args else None
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": "Blueprint not found",
            "detail": str(blueprint_id) if blueprint_id else None,
        },
    )


def _invalid_transition(exc: InvalidBlueprintTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": "Invalid blueprint transition", "detail": str(exc)},
    )


@router.post(
    "/generate",
    response_model=DeploymentBlueprint,
    responses={400: {"model": ErrorResponse}},
)
def generate_blueprint(
    request: GenerateBlueprintRequest,
) -> DeploymentBlueprint:
    """Create a placeholder draft blueprint from a natural language prompt."""
    return blueprint_store.create_from_prompt(request.prompt)


@router.get(
    "/{blueprint_id}",
    response_model=DeploymentBlueprint,
    responses={404: {"model": ErrorResponse}},
)
def get_blueprint(blueprint_id: str) -> DeploymentBlueprint:
    """Return the stored blueprint for the requested ID."""
    try:
        return blueprint_store.get(blueprint_id)
    except BlueprintNotFoundError as exc:
        raise _not_found(exc) from exc


@router.post(
    "/{blueprint_id}/save",
    response_model=DeploymentBlueprint,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def save_blueprint(blueprint_id: str) -> DeploymentBlueprint:
    """Save a draft blueprint."""
    try:
        return blueprint_store.save(blueprint_id)
    except BlueprintNotFoundError as exc:
        raise _not_found(exc) from exc
    except InvalidBlueprintTransitionError as exc:
        raise _invalid_transition(exc) from exc


@router.post(
    "/{blueprint_id}/approve",
    response_model=DeploymentBlueprint,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def approve_blueprint(blueprint_id: str) -> DeploymentBlueprint:
    """Approve a draft or saved blueprint."""
    try:
        return blueprint_store.approve(blueprint_id)
    except BlueprintNotFoundError as exc:
        raise _not_found(exc) from exc
    except InvalidBlueprintTransitionError as exc:
        raise _invalid_transition(exc) from exc

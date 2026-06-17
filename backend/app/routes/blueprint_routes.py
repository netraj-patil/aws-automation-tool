"""HTTP routes for deployment blueprint drafts, approvals, and execution."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.agent_models import ErrorResponse
from app.models.blueprint_models import (
    BlueprintExecutionRequest,
    BlueprintExecutionResponse,
    DeploymentBlueprint,
)
from app.services.blueprint_executor import (
    BlueprintValidationError,
    MissingAwsCredentialsError,
    blueprint_executor,
)
from app.services.blueprint_store import (
    BlueprintNotFoundError,
    InvalidBlueprintTransitionError,
    blueprint_store,
)
from app.services.blueprint_planner import blueprint_planner
from app.services.cost_service import cost_service
from app.services.security_service import security_service


router = APIRouter(prefix="/api/v1/blueprints", tags=["blueprints"])


class GenerateBlueprintRequest(BaseModel):
    """Request body for creating a draft deployment blueprint."""

    prompt: str = Field(min_length=1)


APPROVAL_REQUIRED_MESSAGE = "Blueprint must be approved before execution."


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


def _credentials(request: Request) -> dict[str, str | None]:
    """Read the active browser profile, falling back to boto3's chain."""
    return {
        "aws_access_key_id": request.headers.get("X-AWS-Access-Key-Id"),
        "aws_secret_access_key": request.headers.get(
            "X-AWS-Secret-Access-Key"
        ),
        "aws_session_token": request.headers.get("X-AWS-Session-Token"),
    }


@router.post(
    "/generate",
    response_model=DeploymentBlueprint,
    responses={400: {"model": ErrorResponse}},
)
def generate_blueprint(
    request: GenerateBlueprintRequest,
) -> DeploymentBlueprint:
    """Create a draft blueprint from a natural language prompt."""
    blueprint = blueprint_planner.generate(request.prompt)
    blueprint = cost_service.estimate(blueprint)
    blueprint = security_service.review(blueprint)
    return blueprint_store.add(blueprint)


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


@router.post(
    "/{blueprint_id}/execute",
    response_model=BlueprintExecutionResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def execute_blueprint(
    blueprint_id: str,
    http_request: Request,
    execute_request: BlueprintExecutionRequest | None = None,
) -> BlueprintExecutionResponse:
    """Execute an approved blueprint using the dry-run executor."""
    request = execute_request or BlueprintExecutionRequest()
    try:
        blueprint = blueprint_store.get(blueprint_id)
    except BlueprintNotFoundError as exc:
        raise _not_found(exc) from exc

    try:
        blueprint = blueprint_executor.validate_blueprint(blueprint)
    except BlueprintValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Invalid blueprint schema",
                "detail": str(exc),
            },
        ) from exc

    if blueprint.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": APPROVAL_REQUIRED_MESSAGE,
                "detail": f"Current status is '{blueprint.status}'.",
            },
        )

    if (
        blueprint_executor.has_high_risk_warnings(blueprint)
        and not request.override_high_risk
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "High-risk security warnings require override.",
                "detail": (
                    "Set override_high_risk to true to execute the dry-run."
                ),
            },
        )

    try:
        blueprint_executor.check_credentials(_credentials(http_request))
    except MissingAwsCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "AWS credentials required", "detail": str(exc)},
        ) from exc

    try:
        blueprint_store.mark_deploying(blueprint.blueprint_id)
        result = blueprint_executor.dry_run(
            blueprint,
            override_high_risk=request.override_high_risk,
        )
        deployed = blueprint_store.mark_deployed(blueprint.blueprint_id)
        result.status = "deployed"
        result.updated_at = deployed.updated_at
        return result
    except Exception as exc:
        try:
            blueprint_store.mark_failed(blueprint.blueprint_id)
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Blueprint execution failed", "detail": str(exc)},
        ) from exc

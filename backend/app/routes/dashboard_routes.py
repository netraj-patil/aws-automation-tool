"""Read-only endpoints that power the AWS dashboard."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request, status

from app.services.aws_credentials import (
    MissingAwsCredentialsError,
    credentials_from_headers,
)
from app.services.blueprint_store import blueprint_store
from app.services.dashboard_service import dashboard_service
from app.services.deployment_store import deployment_store
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


PERMISSION_ERROR_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "AuthorizationError",
    "UnauthorizedOperation",
}


def _credentials(request: Request) -> dict[str, str | None]:
    """Read the active browser profile without using server env credentials."""
    return credentials_from_headers(request)


def _optional_credentials(request: Request) -> dict[str, str | None]:
    """Read browser credentials when present; missing credentials trigger demo mode."""
    return {
        "aws_access_key_id": request.headers.get("X-AWS-Access-Key-Id"),
        "aws_secret_access_key": request.headers.get(
            "X-AWS-Secret-Access-Key"
        ),
        "aws_session_token": request.headers.get("X-AWS-Session-Token"),
    }


def _is_permission_error(exc: Exception) -> bool:
    if not isinstance(exc, ClientError):
        return False
    code = str(exc.response.get("Error", {}).get("Code", ""))
    return code in PERMISSION_ERROR_CODES or "AccessDenied" in code


def _aws_error(exc: Exception) -> HTTPException:
    logger.warning(
        "Dashboard AWS request failed",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    if _is_permission_error(exc):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "aws_permission_required",
                "message": (
                    "Additional AWS read permission is needed for this "
                    "dashboard section."
                ),
            },
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to load data from AWS. Check the active credentials and region.",
    )


def _missing_credentials_error(exc: MissingAwsCredentialsError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "aws_credentials_required",
            "message": str(exc),
        },
    )


@router.get("")
def dashboard(
    request: Request,
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    """Return the complete AWS Agent Dashboard response."""
    try:
        blueprints = blueprint_store.list_all()
    except Exception:
        blueprints = []
    try:
        deployments = deployment_store.list_all()
    except Exception:
        deployments = []
    return dashboard_service.get_dashboard(
        region,
        _optional_credentials(request),
        blueprints=blueprints,
        deployments=deployments,
    )


@router.get("/summary")
def summary(
    request: Request,
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    """Return the dashboard resource summary."""
    try:
        return dashboard_service.get_summary(
            region, _credentials(request)
        )
    except HTTPException:
        raise
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/costs")
def costs(request: Request) -> dict[str, Any]:
    """Return the latest 30 days of Cost Explorer data."""
    try:
        return dashboard_service.get_costs(_credentials(request))
    except HTTPException:
        raise
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/ec2")
def recent_ec2(
    request: Request,
    region: str = Query(default="us-east-1", min_length=3),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Return recently launched EC2 instances."""
    try:
        return dashboard_service.get_recent_instances(
            region,
            _credentials(request),
            limit,
        )
    except HTTPException:
        raise
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc

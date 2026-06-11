"""Read-only endpoints that power the AWS dashboard."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, status

from app.services.dashboard_service import dashboard_service
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


def _credentials() -> dict[str, str | None]:
    """Use only boto3's server-side credential chain for dashboard reads."""
    return {}


def _aws_error(exc: Exception) -> HTTPException:
    logger.warning(
        "Dashboard AWS request failed",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to load data from AWS. Check the active credentials and region.",
    )


@router.get("/summary")
def summary(
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    """Return the dashboard resource summary."""
    try:
        return dashboard_service.get_summary(
            region, _credentials()
        )
    except HTTPException:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/costs")
def costs() -> dict[str, Any]:
    """Return the latest 30 days of Cost Explorer data."""
    try:
        return dashboard_service.get_costs(_credentials())
    except HTTPException:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/ec2")
def recent_ec2(
    region: str = Query(default="us-east-1", min_length=3),
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    """Return recently launched EC2 instances."""
    try:
        return dashboard_service.get_recent_instances(
            region,
            _credentials(),
            limit,
        )
    except HTTPException:
        raise
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc

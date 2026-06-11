"""Read-only endpoints for the Resource Explorer view."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, status

from app.services.resource_service import resource_service
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


def _credentials() -> dict[str, str | None]:
    """Use boto3's server-side credential chain for inventory reads."""
    return {}


def _aws_error(exc: Exception) -> HTTPException:
    logger.warning(
        "Resource Explorer AWS request failed",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to load AWS resources. Check the active credentials and permissions.",
    )


@router.get("/search")
def search_resources(
    q: str = Query(min_length=1),
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    try:
        return resource_service.search_resources(q, _credentials(), region)
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/ec2")
def ec2_instances(
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    try:
        return resource_service.get_ec2_instances(_credentials(), region)
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/s3")
def s3_buckets() -> dict[str, Any]:
    try:
        return resource_service.get_s3_buckets(_credentials())
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/s3/{bucket}/objects")
def s3_objects(
    bucket: str,
    prefix: str = Query(default=""),
) -> dict[str, Any]:
    try:
        return resource_service.get_s3_objects(
            bucket, prefix, _credentials()
        )
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc

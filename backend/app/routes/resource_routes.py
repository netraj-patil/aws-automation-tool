"""Read-only endpoints for the Resource Explorer view."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, Request, status

from app.services.aws_credentials import (
    MissingAwsCredentialsError,
    credentials_from_headers,
)
from app.services.resource_service import resource_service
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/resources", tags=["resources"])


def _credentials(request: Request) -> dict[str, str | None]:
    """Read AWS credentials from the active browser profile only."""
    return credentials_from_headers(request)


def _aws_error(exc: Exception) -> HTTPException:
    logger.warning(
        "Resource Explorer AWS request failed",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Unable to load AWS resources. Check the active credentials and permissions.",
    )


def _missing_credentials_error(exc: MissingAwsCredentialsError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "aws_credentials_required",
            "message": str(exc),
        },
    )


@router.get("/search")
def search_resources(
    request: Request,
    q: str = Query(default="*", min_length=0),
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    try:
        return resource_service.search_resources(q, _credentials(request), region)
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/ec2")
def ec2_instances(
    request: Request,
    region: str = Query(default="us-east-1", min_length=3),
) -> dict[str, Any]:
    try:
        return resource_service.get_ec2_instances(_credentials(request), region)
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/s3")
def s3_buckets(request: Request) -> dict[str, Any]:
    try:
        return resource_service.get_s3_buckets(_credentials(request))
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc


@router.get("/s3/{bucket}/objects")
def s3_objects(
    request: Request,
    bucket: str,
    prefix: str = Query(default=""),
) -> dict[str, Any]:
    try:
        return resource_service.get_s3_objects(
            bucket, prefix, _credentials(request)
        )
    except MissingAwsCredentialsError as exc:
        raise _missing_credentials_error(exc) from exc
    except (BotoCoreError, ClientError) as exc:
        raise _aws_error(exc) from exc

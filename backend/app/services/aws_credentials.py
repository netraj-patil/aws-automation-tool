"""Helpers for AWS credentials supplied by the browser session."""

from fastapi import Request


class MissingAwsCredentialsError(ValueError):
    """Raised when AWS credentials were not provided by the user."""


AWS_CREDENTIAL_KEYS = {
    "aws_access_key_id",
    "aws_secret_access_key",
    "aws_session_token",
}


def credentials_from_headers(request: Request) -> dict[str, str | None]:
    """Read AWS credentials from explicit browser request headers only."""
    credentials = {
        "aws_access_key_id": request.headers.get("X-AWS-Access-Key-Id"),
        "aws_secret_access_key": request.headers.get(
            "X-AWS-Secret-Access-Key"
        ),
        "aws_session_token": request.headers.get("X-AWS-Session-Token"),
    }
    require_explicit_credentials(credentials)
    return credentials


def explicit_session_kwargs(
    credentials: dict[str, str | None],
) -> dict[str, str]:
    """Return boto3 Session kwargs without falling back to env/profile config."""
    require_explicit_credentials(credentials)
    return {
        key: value
        for key, value in credentials.items()
        if key in AWS_CREDENTIAL_KEYS and value
    }


def require_explicit_credentials(
    credentials: dict[str, str | None],
) -> None:
    """Require the access key and secret key to come from user input."""
    if not credentials.get("aws_access_key_id") or not credentials.get(
        "aws_secret_access_key"
    ):
        raise MissingAwsCredentialsError(
            "Add AWS credentials in Temporary Credentials or Profile settings before loading AWS data."
        )

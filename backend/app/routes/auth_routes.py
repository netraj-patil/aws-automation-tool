"""HTTP routes for local account registration and login."""

from fastapi import APIRouter, HTTPException, status

from app.models.auth_models import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    auth_service,
)


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


def _response(token: str, user: dict[str, str]) -> AuthResponse:
    return AuthResponse(access_token=token, user=UserResponse(**user))


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(request: RegisterRequest) -> AuthResponse:
    """Create an account and immediately return an access token."""
    try:
        token, user = auth_service.register(
            request.name, request.email, request.password
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    return _response(token, user)


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest) -> AuthResponse:
    """Authenticate an account and return an access token."""
    try:
        token, user = auth_service.login(request.email, request.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        ) from exc
    return _response(token, user)

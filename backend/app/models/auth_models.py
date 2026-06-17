"""Request and response models for local user authentication."""

from pydantic import BaseModel, Field, field_validator


class UserResponse(BaseModel):
    """Public user fields returned to the frontend."""

    id: str
    name: str
    email: str


class RegisterRequest(BaseModel):
    """Payload for creating a local account."""

    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=256)

    @field_validator("name", "email")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return normalized


class LoginRequest(BaseModel):
    """Payload for signing in to a local account."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class AuthResponse(BaseModel):
    """JWT and user details returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse

"""Pydantic request and response models for the agent API."""

from typing import Any, Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Start or continue an agent planning session."""

    session_id: str | None = None
    message: str
    aws_access_key_id: str
    aws_secret_access_key: str
    region: str = "us-east-1"


class ApprovalRequest(BaseModel):
    """Approve the current plan or request a refinement."""

    session_id: str
    approved: bool
    refinement_message: str | None = None


class PlanResponse(BaseModel):
    """A reviewed plan awaiting user approval."""

    session_id: str
    phase: Literal["planning"]
    plan: list[dict[str, Any]]
    jury_verdict: dict[str, Any]
    formatted_plan: str


class ExecutionResponse(BaseModel):
    """The result of executing an approved plan."""

    session_id: str
    phase: Literal["done", "error"]
    results: list[dict[str, Any]]
    summary: str


class ErrorResponse(BaseModel):
    """Standard API error payload."""

    error: str
    detail: str | None = None

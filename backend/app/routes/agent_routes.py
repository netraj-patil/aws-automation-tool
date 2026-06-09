"""HTTP routes for planning and executing AWS automation requests."""

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status

from app.models.agent_models import (
    ApprovalRequest,
    ChatRequest,
    ErrorResponse,
    ExecutionResponse,
    PlanResponse,
)
from app.services.graph import agent_graph, run_agent, session_store
from app.services.session_store import SessionNotFoundError
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1")


def _server_error(exc: Exception) -> HTTPException:
    logger.exception(
        "Agent API request failed",
        extra={"error_type": type(exc).__name__, "error": str(exc)},
    )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "Internal server error", "detail": str(exc)},
    )


async def _plan_response(
    session_id: str, result: dict[str, Any]
) -> PlanResponse:
    if result.get("phase") == "error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Agent planning failed",
                "detail": result.get("message"),
            },
        )

    verdict = result.get("jury_verdict")
    if verdict is None:
        snapshot = await agent_graph.aget_state(
            {"configurable": {"thread_id": session_id}}
        )
        verdict = snapshot.values.get("jury_verdict") or {}

    return PlanResponse(
        session_id=session_id,
        phase="planning",
        plan=result.get("plan") or [],
        jury_verdict=verdict,
        formatted_plan=str(result.get("message") or ""),
    )


@router.post(
    "/chat",
    response_model=PlanResponse,
    responses={500: {"model": ErrorResponse}},
)
async def chat(request: ChatRequest) -> PlanResponse:
    """Create or continue a session and return a reviewed plan."""
    session_id = request.session_id or str(uuid4())
    credentials = {
        "aws_access_key_id": request.aws_access_key_id,
        "aws_secret_access_key": request.aws_secret_access_key,
        "region": request.region,
    }

    try:
        if session_store.session_exists(session_id):
            session_store.update_credentials(session_id, credentials)
        else:
            session_store.create_session(session_id, credentials)
        result = await run_agent(
            session_id, request.message, plan_approved=False
        )
        return await _plan_response(session_id, result)
    except HTTPException:
        raise
    except Exception as exc:
        raise _server_error(exc) from exc


@router.post(
    "/approve",
    response_model=PlanResponse | ExecutionResponse,
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def approve(
    request: ApprovalRequest,
) -> PlanResponse | ExecutionResponse:
    """Approve the current plan or send it back for refinement."""
    if not session_store.session_exists(request.session_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "detail": request.session_id},
        )

    try:
        result = await run_agent(
            request.session_id,
            request.refinement_message or "approved",
            plan_approved=request.approved,
        )
        if not request.approved:
            return await _plan_response(request.session_id, result)

        phase = result.get("phase", "error")
        return ExecutionResponse(
            session_id=request.session_id,
            phase=phase if phase in {"done", "error"} else "error",
            results=result.get("results") or [],
            summary=str(result.get("message") or ""),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _server_error(exc) from exc


@router.get(
    "/session/{session_id}",
    response_model=list[dict[str, str]],
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_session(session_id: str) -> list[dict[str, str]]:
    """Return the stored message history for a session."""
    try:
        return session_store.get_messages(session_id)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "detail": session_id},
        ) from exc
    except Exception as exc:
        raise _server_error(exc) from exc


@router.delete(
    "/session/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def delete_session(session_id: str) -> Response:
    """Delete a session and all of its stored data."""
    try:
        session_store.delete_session(session_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except SessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "detail": session_id},
        ) from exc
    except Exception as exc:
        raise _server_error(exc) from exc

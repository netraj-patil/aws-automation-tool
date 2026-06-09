"""API contract tests for the FastAPI agent routes."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes import agent_routes
from app.services.session_store import SessionStore


def _client(monkeypatch) -> TestClient:
    store = SessionStore()
    monkeypatch.setattr(agent_routes, "session_store", store)
    return TestClient(app)


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_chat_creates_session_and_returns_plan(monkeypatch) -> None:
    client = _client(monkeypatch)

    async def fake_run_agent(
        session_id: str, message: str, plan_approved: bool
    ) -> dict:
        assert message == "List buckets"
        assert plan_approved is False
        return {
            "phase": "awaiting_approval",
            "plan": [{"step_number": 1}],
            "jury_verdict": {"risk_level": "low"},
            "message": "Review this plan",
        }

    monkeypatch.setattr(agent_routes, "run_agent", fake_run_agent)
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "List buckets",
            "aws_access_key_id": "key",
            "aws_secret_access_key": "secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "planning"
    assert payload["jury_verdict"] == {"risk_level": "low"}
    assert payload["session_id"]


def test_approve_missing_session_returns_error_response(monkeypatch) -> None:
    client = _client(monkeypatch)
    response = client.post(
        "/api/v1/approve",
        json={"session_id": "missing", "approved": True},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": "Session not found",
        "detail": "missing",
    }


def test_delete_session_returns_no_content(monkeypatch) -> None:
    client = _client(monkeypatch)
    agent_routes.session_store.create_session("session-1", {})

    response = client.delete("/api/v1/session/session-1")

    assert response.status_code == 204
    assert response.content == b""

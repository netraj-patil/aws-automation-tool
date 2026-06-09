from fastapi.testclient import TestClient

from app.main import app
from app.routes import agent_routes
from app.services.session_store import SessionStore


def _client(mocker) -> tuple[TestClient, SessionStore]:
    store = SessionStore("memory")
    mocker.patch.object(agent_routes, "session_store", store)
    return TestClient(app), store


def test_planning_phase_returns_plan(mocker, fake_credentials) -> None:
    client, _ = _client(mocker)
    run_agent = mocker.patch.object(
        agent_routes,
        "run_agent",
        return_value={
            "phase": "awaiting_approval",
            "plan": [{"step_number": 1, "tool_name": "list_s3_buckets"}],
            "jury_verdict": {"risk_level": "low"},
            "message": "Review the plan",
        },
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "List buckets",
            **fake_credentials,
        },
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "planning"
    assert response.json()["plan"]
    run_agent.assert_awaited_once()


def test_approval_triggers_execution(mocker, fake_credentials) -> None:
    client, store = _client(mocker)
    store.create_session("session-1", fake_credentials)
    run_agent = mocker.patch.object(
        agent_routes,
        "run_agent",
        return_value={
            "phase": "done",
            "results": [{"status": "success"}],
            "message": "Executed",
        },
    )

    response = client.post(
        "/api/v1/approve",
        json={"session_id": "session-1", "approved": True},
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "done"
    run_agent.assert_awaited_once_with(
        "session-1", "approved", plan_approved=True
    )


def test_re_plan_on_rejection(mocker, fake_credentials) -> None:
    client, store = _client(mocker)
    store.create_session("session-1", fake_credentials)
    run_agent = mocker.patch.object(
        agent_routes,
        "run_agent",
        return_value={
            "phase": "awaiting_approval",
            "plan": [{"step_number": 1, "tool_name": "get_vpc_details"}],
            "jury_verdict": {"risk_level": "low"},
            "message": "Revised plan",
        },
    )

    response = client.post(
        "/api/v1/approve",
        json={
            "session_id": "session-1",
            "approved": False,
            "refinement_message": "Use us-west-2 instead",
        },
    )

    assert response.status_code == 200
    assert response.json()["phase"] == "planning"
    run_agent.assert_awaited_once_with(
        "session-1", "Use us-west-2 instead", plan_approved=False
    )

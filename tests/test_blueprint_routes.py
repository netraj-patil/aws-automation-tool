"""API contract tests for deployment blueprint routes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import blueprint_routes
from app.services.blueprint_store import BlueprintStore


@pytest.fixture
def client(monkeypatch) -> TestClient:
    store = BlueprintStore()
    monkeypatch.delenv("BLUEPRINT_PLANNER_MODE", raising=False)
    monkeypatch.setattr(blueprint_routes, "blueprint_store", store)
    return TestClient(app)


def test_generate_blueprint(client: TestClient) -> None:
    response = client.post(
        "/api/v1/blueprints/generate",
        json={
            "prompt": (
                "Deploy a production-ready FastAPI app with PostgreSQL, "
                "S3 storage, and HTTPS."
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    resource_ids = {resource["id"] for resource in payload["resources"]}
    assert payload["blueprint_id"].startswith("bp_")
    assert payload["status"] == "draft"
    assert payload["user_prompt"] == (
        "Deploy a production-ready FastAPI app with PostgreSQL, "
        "S3 storage, and HTTPS."
    )
    assert {
        "app-compute",
        "postgres-database",
        "object-storage",
        "https-load-balancer",
        "monitoring",
    } <= resource_ids
    assert payload["estimated_cost"]["estimated_monthly_total"] > 0
    assert payload["security_review"]["passed"] is True


def test_get_blueprint(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway"},
    ).json()

    response = client.get(f"/api/v1/blueprints/{created['blueprint_id']}")

    assert response.status_code == 200
    assert response.json()["blueprint_id"] == created["blueprint_id"]


def test_save_blueprint(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy ECS service"},
    ).json()

    response = client.post(
        f"/api/v1/blueprints/{created['blueprint_id']}/save"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "saved"


def test_approve_blueprint(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy RDS database"},
    ).json()

    response = client.post(
        f"/api/v1/blueprints/{created['blueprint_id']}/approve"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_unknown_blueprint_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/blueprints/bp_missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": "Blueprint not found",
        "detail": "bp_missing",
    }


def test_invalid_transition_returns_400(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy VPC"},
    ).json()
    blueprint_id = created["blueprint_id"]

    approve_response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/approve"
    )
    save_response = client.post(f"/api/v1/blueprints/{blueprint_id}/save")

    assert approve_response.status_code == 200
    assert save_response.status_code == 400
    assert save_response.json()["error"] == "Invalid blueprint transition"

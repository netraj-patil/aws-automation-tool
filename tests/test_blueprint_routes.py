"""API contract tests for deployment blueprint routes."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.blueprint_models import (
    CostEstimate,
    DeploymentBlueprint,
    SecurityReview,
    SecurityWarning,
)
from app.routes import blueprint_routes, deployment_routes
from app.services.deployment_store import DeploymentStore
from app.services.blueprint_store import BlueprintStore


@pytest.fixture
def store(monkeypatch) -> BlueprintStore:
    store = BlueprintStore()
    monkeypatch.delenv("BLUEPRINT_PLANNER_MODE", raising=False)
    monkeypatch.setattr(blueprint_routes, "blueprint_store", store)
    return store


@pytest.fixture
def deployments(monkeypatch) -> DeploymentStore:
    store = DeploymentStore()
    monkeypatch.setattr(blueprint_routes, "deployment_store", store)
    monkeypatch.setattr(deployment_routes, "deployment_store", store)
    return store


@pytest.fixture
def client(store: BlueprintStore, deployments: DeploymentStore) -> TestClient:
    return TestClient(app)


AWS_HEADERS = {
    "X-AWS-Access-Key-Id": "AKIATEST",
    "X-AWS-Secret-Access-Key": "fakesecret",
}


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
    assert payload["diagram_mermaid"].startswith("graph TD")
    assert (
        'node_app_compute["FastAPI application compute"]'
        in payload["diagram_mermaid"]
    )
    assert (
        "node_app_compute --> node_postgres_database"
        in payload["diagram_mermaid"]
    )
    assert payload["estimated_cost"]["estimated_monthly_total"] == 46
    assert payload["estimated_cost"]["breakdown"] == {
        "app-compute": 8.0,
        "postgres-database": 15.0,
        "object-storage": 2.0,
        "https-load-balancer": 18.0,
        "monitoring": 3.0,
    }
    assert payload["security_review"]["security_score"] == 100
    assert payload["security_review"]["passed"] is True
    assert payload["security_review"]["warnings"] == []


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


def test_draft_blueprint_cannot_execute(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy ECS service"},
    ).json()

    response = client.post(
        f"/api/v1/blueprints/{created['blueprint_id']}/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"] == (
        "Blueprint must be approved before execution."
    )


def test_saved_blueprint_cannot_execute(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy ECS service"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/save")

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"] == (
        "Blueprint must be approved before execution."
    )


def test_approved_blueprint_can_execute(client: TestClient) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={
            "prompt": (
                "Deploy a production-ready FastAPI app with PostgreSQL, "
                "S3 storage, and HTTPS."
            )
        },
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["deployment_id"].startswith("dep_")
    assert payload["blueprint_id"] == blueprint_id
    assert payload["status"] == "deployed"
    assert "Deployment dry-run completed" in payload["logs"]
    assert {resource["resource_id"] for resource in payload["planned_resources"]}
    assert payload["error"] is None


def test_approved_blueprint_without_credentials_does_not_use_env_chain(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    response = client.post(f"/api/v1/blueprints/{blueprint_id}/execute")

    assert response.status_code == 400
    assert response.json()["error"] == "AWS credentials required"


def test_execution_creates_deployment_record(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    execute_response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )
    deployment_id = execute_response.json()["deployment_id"]
    get_response = client.get(f"/api/v1/deployments/{deployment_id}")

    assert execute_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["deployment_id"] == deployment_id
    assert get_response.json()["blueprint_id"] == blueprint_id


def test_deployment_logs_are_returned_in_order(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={
            "prompt": (
                "Deploy a production-ready FastAPI app with PostgreSQL, "
                "S3 storage, and HTTPS."
            )
        },
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 200
    logs = response.json()["logs"]
    assert logs[:3] == [
        "Validating blueprint",
        "Checking approval",
        "Reviewing security warnings",
    ]
    assert logs.index("Preparing load balancer") < logs.index(
        "Deployment dry-run completed"
    )
    assert logs.index("Preparing compute resources") < logs.index(
        "Deployment dry-run completed"
    )
    assert logs[-1] == "Deployment dry-run completed"


def test_successful_execution_stores_deployed_status(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy private VPC"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )
    deployment = client.get(
        f"/api/v1/deployments/{response.json()['deployment_id']}"
    ).json()

    assert response.status_code == 200
    assert deployment["status"] == "deployed"


def test_failed_execution_stores_failed_status_and_error(
    client: TestClient,
    monkeypatch,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    def fail_dry_run(*args, **kwargs):
        raise RuntimeError("simulated execution failure")

    monkeypatch.setattr(
        blueprint_routes.blueprint_executor,
        "dry_run",
        fail_dry_run,
    )

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )
    history = client.get(
        f"/api/v1/blueprints/{blueprint_id}/deployments"
    ).json()

    assert response.status_code == 500
    assert history[0]["status"] == "failed"
    assert history[0]["error"] == "simulated execution failure"
    assert history[0]["logs"][-1] == "simulated execution failure"


def test_high_risk_blueprint_blocks_without_override(
    client: TestClient,
    store: BlueprintStore,
) -> None:
    blueprint = store.add(_high_risk_blueprint())

    response = client.post(
        f"/api/v1/blueprints/{blueprint.blueprint_id}/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 409
    assert response.json()["error"] == (
        "High-risk security warnings require override."
    )
    assert store.get(blueprint.blueprint_id).status == "approved"


def test_high_risk_blueprint_executes_with_override(
    client: TestClient,
    store: BlueprintStore,
) -> None:
    blueprint = store.add(_high_risk_blueprint())

    response = client.post(
        f"/api/v1/blueprints/{blueprint.blueprint_id}/execute",
        json={"override_high_risk": True},
        headers=AWS_HEADERS,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "deployed"
    assert "High-risk override accepted for dry-run execution" in payload["logs"]
    assert store.get(blueprint.blueprint_id).status == "deployed"


def test_blueprint_deployment_history_returns_records(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")
    deployment = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    ).json()

    response = client.get(f"/api/v1/blueprints/{blueprint_id}/deployments")

    assert response.status_code == 200
    assert response.json()[0]["deployment_id"] == deployment["deployment_id"]
    assert response.json()[0]["blueprint_id"] == blueprint_id


def test_execution_updates_status_and_returns_logs(
    client: TestClient,
    store: BlueprintStore,
) -> None:
    created = client.post(
        "/api/v1/blueprints/generate",
        json={"prompt": "Deploy Lambda behind API Gateway with CloudWatch"},
    ).json()
    blueprint_id = created["blueprint_id"]
    client.post(f"/api/v1/blueprints/{blueprint_id}/approve")

    response = client.post(
        f"/api/v1/blueprints/{blueprint_id}/execute",
        headers=AWS_HEADERS,
    )

    payload = response.json()
    assert response.status_code == 200
    assert store.get(blueprint_id).status == "deployed"
    assert payload["logs"][:3] == [
        "Validating blueprint",
        "Checking approval",
        "Reviewing security warnings",
    ]
    assert "created_at" in payload
    assert "updated_at" in payload


def test_missing_blueprint_execute_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/blueprints/bp_missing/execute",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": "Blueprint not found",
        "detail": "bp_missing",
    }


def test_unknown_deployment_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/deployments/dep_missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": "Deployment not found",
        "detail": "dep_missing",
    }


def _high_risk_blueprint() -> DeploymentBlueprint:
    return DeploymentBlueprint(
        blueprint_id="bp_high_risk",
        name="High Risk Blueprint",
        status="approved",
        user_prompt="Deploy a public database",
        summary="A blueprint with a high-risk security warning.",
        resources=[
            {
                "id": "public-db",
                "type": "database",
                "name": "Public PostgreSQL database",
                "service": "rds",
                "config": {"publicly_accessible": True},
                "visibility": "public",
                "estimated_monthly_cost": 15,
                "risk_level": "high",
            }
        ],
        connections=[],
        estimated_cost=CostEstimate(
            estimated_monthly_total=15,
            breakdown={"public-db": 15},
            assumptions=[],
        ),
        security_review=SecurityReview(
            risk_level="high",
            security_score=70,
            passed=True,
            warnings=[
                SecurityWarning(
                    severity="high",
                    message="RDS database is publicly reachable.",
                    resource_id="public-db",
                    recommendation="Place RDS in private subnets.",
                )
            ],
            summary="High-risk warning found.",
        ),
    )

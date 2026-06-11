"""API contract tests for the read-only dashboard endpoints."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes import dashboard_routes


class FakeDashboardService:
    def __init__(self) -> None:
        self.calls = []

    def get_summary(self, region, credentials):
        self.calls.append(("summary", region, credentials))
        return {
            "region": region,
            "ec2": {"running": 2, "total": 3},
            "s3": {"total": 4},
            "rds": {"total": 1},
            "iam": {"total": 5},
            "vpc": {"active": 2},
        }

    def get_costs(self, credentials):
        self.calls.append(("costs", credentials))
        return {
            "currency": "USD",
            "total": 12.5,
            "previous_total": 10,
            "delta_percent": 25,
            "daily": [],
        }

    def get_recent_instances(self, region, credentials, limit):
        self.calls.append(("ec2", region, credentials, limit))
        return {"region": region, "instances": []}


def test_summary_uses_server_credentials_only(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary?region=ap-south-1",
        headers={
            "X-AWS-Access-Key-Id": "AKIATEST",
            "X-AWS-Secret-Access-Key": "secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["ec2"] == {"running": 2, "total": 3}
    assert service.calls[0] == (
        "summary",
        "ap-south-1",
        {},
    )


def test_costs_and_recent_ec2_contract(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    costs = client.get("/api/v1/dashboard/costs")
    instances = client.get(
        "/api/v1/dashboard/ec2?region=eu-west-1&limit=10"
    )

    assert costs.status_code == 200
    assert costs.json()["delta_percent"] == 25
    assert instances.status_code == 200
    assert instances.json() == {"region": "eu-west-1", "instances": []}


def test_dashboard_ignores_temporary_credential_headers(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary",
        headers={"X-AWS-Access-Key-Id": "AKIATEST"},
    )

    assert response.status_code == 200
    assert service.calls[0][2] == {}

"""API contract tests for the read-only dashboard endpoints."""

from botocore.exceptions import ClientError
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
            "vpc": {"custom": 2},
            "permission_warnings": [],
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


def test_summary_uses_active_profile_credentials(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary?region=ap-south-1",
        headers={
            "X-AWS-Access-Key-Id": "AKIATEST",
            "X-AWS-Secret-Access-Key": "secret",
            "X-AWS-Session-Token": "session",
        },
    )

    assert response.status_code == 200
    assert response.json()["ec2"] == {"running": 2, "total": 3}
    assert service.calls[0] == (
        "summary",
        "ap-south-1",
        {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "aws_session_token": "session",
        },
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


def test_dashboard_falls_back_to_credential_chain_without_headers(
    monkeypatch,
) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary",
    )

    assert response.status_code == 200
    assert service.calls[0][2] == {
        "aws_access_key_id": None,
        "aws_secret_access_key": None,
        "aws_session_token": None,
    }


def test_permission_error_returns_neutral_contract(monkeypatch) -> None:
    class PermissionDeniedService(FakeDashboardService):
        def get_costs(self, credentials):
            raise ClientError(
                {
                    "Error": {
                        "Code": "AccessDeniedException",
                        "Message": "Denied",
                    }
                },
                "GetCostAndUsage",
            )

    monkeypatch.setattr(
        dashboard_routes, "dashboard_service", PermissionDeniedService()
    )
    client = TestClient(app)

    response = client.get("/api/v1/dashboard/costs")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "aws_permission_required"

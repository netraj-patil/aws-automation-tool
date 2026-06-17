"""API contract tests for the read-only dashboard endpoints."""

from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app.main import app
from app.routes import dashboard_routes


AWS_HEADERS = {
    "X-AWS-Access-Key-Id": "AKIATEST",
    "X-AWS-Secret-Access-Key": "secret",
    "X-AWS-Session-Token": "session",
}


class FakeDashboardService:
    def __init__(self) -> None:
        self.calls = []

    def get_dashboard(self, region, credentials, *, blueprints=None, deployments=None):
        self.calls.append(
            (
                "dashboard",
                region,
                credentials,
                len(blueprints or []),
                len(deployments or []),
            )
        )
        return {
            "mode": "live",
            "banner": None,
            "warnings": [],
            "summary": {
                "total_resources": 0,
                "running_resources": 0,
                "broken_resources": 0,
                "monthly_cost_estimate": 0,
                "pending_agent_actions": 0,
                "pending_approvals": 0,
            },
            "resources": [],
            "running_resources": [],
            "broken_resources": [],
            "costs": {
                "currency": "USD",
                "today": 0,
                "month_to_date": 0,
                "monthly_estimate": 0,
                "by_service": [],
                "daily_trend": [],
            },
            "agent_next_actions": [],
            "pending_approvals": [],
            "recent_activity": [],
        }

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
        headers=AWS_HEADERS,
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


def test_dashboard_returns_demo_without_credentials() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/dashboard?region=ap-south-1")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo"
    assert body["banner"] == (
        "Showing default demo data. Add AWS credentials to monitor your real AWS account."
    )
    assert body["summary"]["total_resources"] > 0
    assert body["resources"]
    assert body["agent_next_actions"]


def test_dashboard_uses_optional_browser_credentials(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard?region=eu-west-1",
        headers=AWS_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert service.calls[0] == (
        "dashboard",
        "eu-west-1",
        {
            "aws_access_key_id": "AKIATEST",
            "aws_secret_access_key": "secret",
            "aws_session_token": "session",
        },
        0,
        0,
    )


def test_costs_and_recent_ec2_contract(monkeypatch) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    costs = client.get("/api/v1/dashboard/costs", headers=AWS_HEADERS)
    instances = client.get(
        "/api/v1/dashboard/ec2?region=eu-west-1&limit=10",
        headers=AWS_HEADERS,
    )

    assert costs.status_code == 200
    assert costs.json()["delta_percent"] == 25
    assert instances.status_code == 200
    assert instances.json() == {"region": "eu-west-1", "instances": []}


def test_dashboard_requires_browser_credentials_without_headers(
    monkeypatch,
) -> None:
    service = FakeDashboardService()
    monkeypatch.setattr(dashboard_routes, "dashboard_service", service)
    client = TestClient(app)

    response = client.get(
        "/api/v1/dashboard/summary",
    )

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "aws_credentials_required"
    assert service.calls == []


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

    response = client.get("/api/v1/dashboard/costs", headers=AWS_HEADERS)

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "aws_permission_required"

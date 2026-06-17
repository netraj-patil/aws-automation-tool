"""API contract tests for Resource Explorer endpoints."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes import resource_routes


AWS_HEADERS = {
    "X-AWS-Access-Key-Id": "AKIATEST",
    "X-AWS-Secret-Access-Key": "secret",
}


class FakeResourceService:
    def __init__(self) -> None:
        self.calls = []

    def search_resources(self, query, credentials, region):
        self.calls.append(("search", query, credentials, region))
        return {"query": query, "resources": []}

    def get_ec2_instances(self, credentials, region):
        self.calls.append(("ec2", credentials, region))
        return {"regions": [region], "instances": []}

    def get_s3_buckets(self, credentials):
        self.calls.append(("s3", credentials))
        return {"buckets": []}

    def get_s3_objects(self, bucket, prefix, credentials):
        self.calls.append(("objects", bucket, prefix, credentials))
        return {"bucket": bucket, "prefix": prefix, "objects": []}


def test_resource_explorer_contract(monkeypatch) -> None:
    service = FakeResourceService()
    monkeypatch.setattr(resource_routes, "resource_service", service)
    client = TestClient(app)

    search = client.get(
        "/api/v1/resources/search?q=production&region=ap-south-1",
        headers=AWS_HEADERS,
    )
    ec2 = client.get("/api/v1/resources/ec2?region=eu-west-1", headers=AWS_HEADERS)
    s3 = client.get("/api/v1/resources/s3", headers=AWS_HEADERS)
    objects = client.get(
        "/api/v1/resources/s3/my-bucket/objects?prefix=logs%2F",
        headers=AWS_HEADERS,
    )

    assert search.status_code == 200
    assert ec2.status_code == 200
    assert s3.status_code == 200
    assert objects.status_code == 200
    assert service.calls == [
        (
            "search",
            "production",
            {
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secret",
                "aws_session_token": None,
            },
            "ap-south-1",
        ),
        (
            "ec2",
            {
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secret",
                "aws_session_token": None,
            },
            "eu-west-1",
        ),
        (
            "s3",
            {
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secret",
                "aws_session_token": None,
            },
        ),
        (
            "objects",
            "my-bucket",
            "logs/",
            {
                "aws_access_key_id": "AKIATEST",
                "aws_secret_access_key": "secret",
                "aws_session_token": None,
            },
        ),
    ]


def test_resource_explorer_requires_browser_credentials(monkeypatch) -> None:
    service = FakeResourceService()
    monkeypatch.setattr(resource_routes, "resource_service", service)
    client = TestClient(app)

    response = client.get("/api/v1/resources/ec2?region=eu-west-1")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "aws_credentials_required"
    assert service.calls == []

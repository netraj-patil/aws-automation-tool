"""API contract tests for Resource Explorer endpoints."""

from fastapi.testclient import TestClient

from app.main import app
from app.routes import resource_routes


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
        "/api/v1/resources/search?q=production&region=ap-south-1"
    )
    ec2 = client.get("/api/v1/resources/ec2?region=eu-west-1")
    s3 = client.get("/api/v1/resources/s3")
    objects = client.get(
        "/api/v1/resources/s3/my-bucket/objects?prefix=logs%2F"
    )

    assert search.status_code == 200
    assert ec2.status_code == 200
    assert s3.status_code == 200
    assert objects.status_code == 200
    assert service.calls == [
        ("search", "production", {}, "ap-south-1"),
        ("ec2", {}, "eu-west-1"),
        ("s3", {}),
        ("objects", "my-bucket", "logs/", {}),
    ]

"""Unit tests for dashboard metric collection."""

from botocore.exceptions import ClientError

from app.services.dashboard_service import DashboardService


class FakePaginator:
    def __init__(self, pages=None, error=None):
        self.pages = pages or []
        self.error = error

    def paginate(self):
        if self.error:
            raise self.error
        return self.pages


class FakeClient:
    def __init__(self, paginators=None, responses=None):
        self.paginators = paginators or {}
        self.responses = responses or {}

    def get_paginator(self, operation):
        return self.paginators[operation]

    def list_buckets(self):
        return self.responses["list_buckets"]

    def describe_vpcs(self):
        return self.responses["describe_vpcs"]


class FakeSession:
    def __init__(self, clients):
        self.clients = clients

    def client(self, service, region_name=None):
        return self.clients[service]


def test_summary_excludes_default_vpc(monkeypatch) -> None:
    ec2 = FakeClient(
        paginators={
            "describe_instances": FakePaginator(
                [{"Reservations": []}]
            )
        },
        responses={
            "describe_vpcs": {
                "Vpcs": [
                    {
                        "VpcId": "vpc-default",
                        "State": "available",
                        "IsDefault": True,
                    },
                    {
                        "VpcId": "vpc-custom",
                        "State": "available",
                        "IsDefault": False,
                    },
                ]
            }
        },
    )
    session = FakeSession(
        {
            "ec2": ec2,
            "s3": FakeClient(
                responses={"list_buckets": {"Buckets": []}}
            ),
            "rds": FakeClient(
                paginators={
                    "describe_db_instances": FakePaginator(
                        [{"DBInstances": []}]
                    )
                }
            ),
            "iam": FakeClient(
                paginators={
                    "list_users": FakePaginator([{"Users": []}])
                }
            ),
        }
    )
    service = DashboardService()
    monkeypatch.setattr(service, "_session", lambda credentials: session)

    summary = service.get_summary("ap-south-1", {})

    assert summary["vpc"] == {"custom": 1}
    assert summary["permission_warnings"] == []


def test_summary_keeps_other_metrics_when_permission_is_missing(
    monkeypatch,
) -> None:
    denied = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "Denied"}},
        "ListUsers",
    )
    ec2 = FakeClient(
        paginators={
            "describe_instances": FakePaginator(
                [{"Reservations": []}]
            )
        },
        responses={"describe_vpcs": {"Vpcs": []}},
    )
    session = FakeSession(
        {
            "ec2": ec2,
            "s3": FakeClient(
                responses={"list_buckets": {"Buckets": []}}
            ),
            "rds": FakeClient(
                paginators={
                    "describe_db_instances": FakePaginator(
                        [{"DBInstances": []}]
                    )
                }
            ),
            "iam": FakeClient(
                paginators={"list_users": FakePaginator(error=denied)}
            ),
        }
    )
    service = DashboardService()
    monkeypatch.setattr(service, "_session", lambda credentials: session)

    summary = service.get_summary("ap-south-1", {})

    assert summary["iam"]["total"] is None
    assert summary["s3"]["total"] == 0
    assert summary["permission_warnings"] == ["IAM users"]

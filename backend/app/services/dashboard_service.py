"""Read-only AWS data used by the dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import boto3


class DashboardService:
    """Collect dashboard metrics directly from boto3 clients."""

    def _session(self, credentials: dict[str, str | None]) -> boto3.Session:
        session_kwargs = {
            key: value
            for key, value in credentials.items()
            if value
        }
        return boto3.Session(**session_kwargs)

    @staticmethod
    def _client(session: boto3.Session, service: str, region: str) -> Any:
        if service in {"s3", "iam", "ce"}:
            service_region = "us-east-1"
        else:
            service_region = region
        return session.client(service, region_name=service_region)

    @staticmethod
    def _count_pages(client: Any, operation: str, result_key: str) -> int:
        paginator = client.get_paginator(operation)
        return sum(
            len(page.get(result_key, []))
            for page in paginator.paginate()
        )

    def get_summary(
        self,
        region: str,
        credentials: dict[str, str | None],
    ) -> dict[str, Any]:
        """Return resource counts for the selected AWS region."""
        session = self._session(credentials)
        ec2 = self._client(session, "ec2", region)
        reservations = ec2.get_paginator("describe_instances").paginate()
        instances = [
            instance
            for page in reservations
            for reservation in page.get("Reservations", [])
            for instance in reservation.get("Instances", [])
            if instance.get("State", {}).get("Name") != "terminated"
        ]

        s3 = self._client(session, "s3", region)
        rds = self._client(session, "rds", region)
        iam = self._client(session, "iam", region)
        vpcs = self._client(session, "ec2", region).describe_vpcs().get(
            "Vpcs", []
        )

        return {
            "region": region,
            "ec2": {
                "running": sum(
                    instance.get("State", {}).get("Name") == "running"
                    for instance in instances
                ),
                "total": len(instances),
            },
            "s3": {"total": len(s3.list_buckets().get("Buckets", []))},
            "rds": {
                "total": self._count_pages(
                    rds, "describe_db_instances", "DBInstances"
                )
            },
            "iam": {
                "total": self._count_pages(iam, "list_users", "Users")
            },
            "vpc": {
                "active": sum(vpc.get("State") == "available" for vpc in vpcs)
            },
        }

    def get_costs(
        self,
        credentials: dict[str, str | None],
        today: date | None = None,
    ) -> dict[str, Any]:
        """Return daily unblended spend for the latest 30-day window."""
        current_day = today or datetime.now(timezone.utc).date()
        current_start = current_day - timedelta(days=29)
        current_end = current_day + timedelta(days=1)
        previous_start = current_start - timedelta(days=30)

        session = self._session(credentials)
        client = self._client(session, "ce", "us-east-1")
        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": previous_start.isoformat(),
                "End": current_end.isoformat(),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )

        amounts = {
            item["TimePeriod"]["Start"]: float(
                item.get("Total", {})
                .get("UnblendedCost", {})
                .get("Amount", 0)
            )
            for item in response.get("ResultsByTime", [])
        }
        currency = next(
            (
                item.get("Total", {})
                .get("UnblendedCost", {})
                .get("Unit")
                for item in response.get("ResultsByTime", [])
                if item.get("Total", {}).get("UnblendedCost", {}).get("Unit")
            ),
            "USD",
        )

        daily = []
        for offset in range(30):
            day = current_start + timedelta(days=offset)
            daily.append(
                {"date": day.isoformat(), "amount": amounts.get(day.isoformat(), 0)}
            )

        current_total = sum(item["amount"] for item in daily)
        previous_total = sum(
            amounts.get((previous_start + timedelta(days=offset)).isoformat(), 0)
            for offset in range(30)
        )
        delta_percent = (
            ((current_total - previous_total) / previous_total) * 100
            if previous_total
            else (100.0 if current_total else 0.0)
        )

        return {
            "currency": currency,
            "total": round(current_total, 4),
            "previous_total": round(previous_total, 4),
            "delta_percent": round(delta_percent, 1),
            "daily": daily,
        }

    def get_recent_instances(
        self,
        region: str,
        credentials: dict[str, str | None],
        limit: int = 10,
    ) -> dict[str, Any]:
        """Return the most recently launched EC2 instances."""
        session = self._session(credentials)
        ec2 = self._client(session, "ec2", region)
        pages = ec2.get_paginator("describe_instances").paginate()
        instances = [
            instance
            for page in pages
            for reservation in page.get("Reservations", [])
            for instance in reservation.get("Instances", [])
        ]
        instances.sort(
            key=lambda item: item.get(
                "LaunchTime", datetime.min.replace(tzinfo=timezone.utc)
            ),
            reverse=True,
        )

        def instance_name(instance: dict[str, Any]) -> str:
            return next(
                (
                    tag.get("Value", "")
                    for tag in instance.get("Tags", [])
                    if tag.get("Key") == "Name"
                ),
                "",
            )

        return {
            "region": region,
            "instances": [
                {
                    "id": instance.get("InstanceId", ""),
                    "name": instance_name(instance)
                    or instance.get("InstanceId", "Unnamed"),
                    "type": instance.get("InstanceType", ""),
                    "state": instance.get("State", {}).get("Name", "unknown"),
                    "region": region,
                    "launch_time": instance.get("LaunchTime").isoformat()
                    if instance.get("LaunchTime")
                    else None,
                }
                for instance in instances[:limit]
            ],
        }


dashboard_service = DashboardService()

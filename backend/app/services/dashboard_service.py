"""Read-only AWS data used by the dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.models.blueprint_models import DeploymentBlueprint
from app.models.deployment_models import DeploymentRecord
from app.services.aws_credentials import (
    MissingAwsCredentialsError,
    explicit_session_kwargs,
)


PERMISSION_ERROR_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "AuthorizationError",
    "UnauthorizedOperation",
}

AUTH_ERROR_CODES = {
    "AuthFailure",
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidAccessKeyId",
    "InvalidClientTokenId",
    "SignatureDoesNotMatch",
    "TokenRefreshRequired",
    "UnrecognizedClientException",
}

DEMO_BANNER = (
    "Showing default demo data. Add AWS credentials to monitor your real AWS account."
)


class DashboardService:
    """Collect normalized control-room dashboard data."""

    def _session(self, credentials: dict[str, str | None]) -> boto3.Session:
        return boto3.Session(**explicit_session_kwargs(credentials))

    @staticmethod
    def _client(session: boto3.Session, service: str, region: str) -> Any:
        if service in {"s3", "iam", "ce", "cloudfront"}:
            service_region = "us-east-1"
        else:
            service_region = region
        return session.client(service, region_name=service_region)

    @staticmethod
    def _count_pages(client: Any, operation: str, result_key: str) -> int:
        paginator = client.get_paginator(operation)
        return sum(len(page.get(result_key, [])) for page in paginator.paginate())

    @staticmethod
    def _error_code(exc: Exception) -> str:
        if not isinstance(exc, ClientError):
            return type(exc).__name__
        return str(exc.response.get("Error", {}).get("Code", ""))

    @classmethod
    def _is_permission_error(cls, exc: Exception) -> bool:
        code = cls._error_code(exc)
        return code in PERMISSION_ERROR_CODES or "AccessDenied" in code

    @classmethod
    def _is_auth_error(cls, exc: Exception) -> bool:
        return cls._error_code(exc) in AUTH_ERROR_CODES

    def _optional_metric(
        self,
        label: str,
        loader: Callable[[], Any],
        permission_warnings: list[str],
    ) -> Any:
        try:
            return loader()
        except ClientError as exc:
            if not self._is_permission_error(exc):
                raise
            permission_warnings.append(label)
            return None

    def get_dashboard(
        self,
        region: str,
        credentials: dict[str, str | None],
        *,
        blueprints: list[DeploymentBlueprint] | None = None,
        deployments: list[DeploymentRecord] | None = None,
    ) -> dict[str, Any]:
        """Return one normalized dashboard response for live or demo mode."""
        blueprints = blueprints or []
        deployments = deployments or []
        try:
            session = self._session(credentials)
        except MissingAwsCredentialsError:
            return self.demo_dashboard(blueprints=blueprints, deployments=deployments)

        warnings: list[str] = []
        live_auth_failures = 0
        collector_failures = 0

        def collect(label: str, loader: Callable[[], Any], fallback: Any) -> Any:
            nonlocal live_auth_failures, collector_failures
            try:
                return loader()
            except Exception as exc:
                collector_failures += 1
                if self._is_auth_error(exc):
                    live_auth_failures += 1
                elif self._is_permission_error(exc):
                    warnings.append(f"{label} needs additional AWS read permission.")
                else:
                    warnings.append(f"{label} could not be loaded from AWS.")
                return fallback

        resources = collect(
            "Resource inventory",
            lambda: self._collect_resources(session, region, warnings),
            [],
        )
        broken_resources = collect(
            "Health signals",
            lambda: self._collect_broken_resources(session, region, deployments, warnings),
            self._broken_from_failed_deployments(deployments),
        )
        costs = collect(
            "Cost Explorer",
            lambda: self._collect_costs(session),
            self._empty_costs(),
        )

        if collector_failures and live_auth_failures == collector_failures:
            return self.demo_dashboard(blueprints=blueprints, deployments=deployments)

        agent_next_actions = self._agent_next_actions(blueprints)
        pending_approvals = self._pending_approvals(blueprints)
        running_resources = [
            self._running_payload(resource)
            for resource in resources
            if resource["status"] in {"running", "active"}
        ]
        recent_activity = self._recent_activity(
            blueprints,
            deployments,
            resources,
            broken_resources,
            warnings,
        )

        return {
            "mode": "live",
            "banner": None,
            "warnings": warnings,
            "summary": {
                "total_resources": len(resources),
                "running_resources": len(running_resources),
                "broken_resources": len(broken_resources),
                "monthly_cost_estimate": costs["monthly_estimate"],
                "pending_agent_actions": len(agent_next_actions),
                "pending_approvals": len(pending_approvals),
            },
            "resources": resources,
            "running_resources": running_resources,
            "broken_resources": broken_resources,
            "costs": costs,
            "agent_next_actions": agent_next_actions,
            "pending_approvals": pending_approvals,
            "recent_activity": recent_activity,
        }

    def demo_dashboard(
        self,
        *,
        blueprints: list[DeploymentBlueprint] | None = None,
        deployments: list[DeploymentRecord] | None = None,
    ) -> dict[str, Any]:
        """Return realistic static data when live AWS data is unavailable."""
        blueprints = blueprints or []
        deployments = deployments or []
        today = datetime.now(timezone.utc).date()
        resources = [
            {
                "id": "lambda-portfolio-api",
                "name": "portfolio-api",
                "service": "Lambda",
                "type": "Function",
                "region": "us-east-1",
                "status": "running",
                "cost_impact": "low",
                "created_at": (today - timedelta(days=11)).isoformat(),
                "tags": {"environment": "demo", "owner": "cloudforge"},
            },
            {
                "id": "s3-frontend-bucket",
                "name": "frontend-bucket",
                "service": "S3",
                "type": "Bucket",
                "region": "us-east-1",
                "status": "active",
                "cost_impact": "low",
                "created_at": (today - timedelta(days=20)).isoformat(),
                "tags": {"app": "frontend"},
            },
            {
                "id": "rds-user-db",
                "name": "user-db",
                "service": "RDS",
                "type": "PostgreSQL",
                "region": "us-east-1",
                "status": "warning",
                "cost_impact": "medium",
                "created_at": (today - timedelta(days=38)).isoformat(),
                "tags": {"tier": "database"},
            },
            {
                "id": "i-testserver",
                "name": "test-server",
                "service": "EC2",
                "type": "t3.micro",
                "region": "us-east-1",
                "status": "stopped",
                "cost_impact": "none",
                "created_at": (today - timedelta(days=6)).isoformat(),
                "tags": {"purpose": "testing"},
            },
            {
                "id": "stack-main",
                "name": "main-stack",
                "service": "CloudFormation",
                "type": "Stack",
                "region": "us-east-1",
                "status": "active",
                "cost_impact": "none",
                "created_at": (today - timedelta(days=16)).isoformat(),
                "tags": {"managed-by": "cloudformation"},
            },
            {
                "id": "ecs-worker-service",
                "name": "worker-service",
                "service": "ECS",
                "type": "Service",
                "region": "us-east-1",
                "status": "warning",
                "cost_impact": "medium",
                "created_at": None,
                "tags": {"service": "worker"},
            },
        ]
        broken_resources = [
            {
                "id": "rds-user-db-storage",
                "name": "user-db",
                "service": "RDS",
                "severity": "high",
                "problem": "RDS free storage is low.",
                "recommended_fix": "Increase allocated storage or clean up unused tables and indexes.",
                "source": "CloudWatch",
            },
            {
                "id": "ecs-worker-service-desired-count",
                "name": "worker-service",
                "service": "ECS",
                "severity": "medium",
                "problem": "Desired count is 2 but running count is 1.",
                "recommended_fix": "Inspect failed task logs and redeploy the ECS service.",
                "source": "ECS",
            },
            {
                "id": "lambda-portfolio-api-errors",
                "name": "portfolio-api",
                "service": "Lambda",
                "severity": "medium",
                "problem": "Lambda has recent errors.",
                "recommended_fix": "Review CloudWatch logs and add retry or validation handling.",
                "source": "Lambda",
            },
        ]
        costs = {
            "currency": "USD",
            "today": 1.18,
            "month_to_date": 34.72,
            "monthly_estimate": 62.4,
            "by_service": [
                {"service": "Amazon RDS", "amount": 24.2},
                {"service": "Amazon EC2", "amount": 16.4},
                {"service": "AWS Lambda", "amount": 5.6},
                {"service": "Amazon S3", "amount": 3.9},
            ],
            "daily_trend": [
                {
                    "date": (today - timedelta(days=offset)).isoformat(),
                    "amount": round(0.65 + ((offset % 5) * 0.18), 2),
                }
                for offset in reversed(range(14))
            ],
        }
        next_actions = self._agent_next_actions(blueprints) or [
            {
                "plan_id": "demo-plan-fastapi",
                "title": "Deploy FastAPI backend to Lambda",
                "action_type": "create",
                "target_services": ["Lambda", "API Gateway", "IAM"],
                "estimated_cost": 8.4,
                "risk_level": "medium",
                "status": "planned",
                "created_at": (today - timedelta(days=1)).isoformat(),
            },
            {
                "plan_id": "demo-plan-cloudfront",
                "title": "Add CloudFront in front of S3 frontend",
                "action_type": "create",
                "target_services": ["CloudFront", "S3", "ACM"],
                "estimated_cost": 12.5,
                "risk_level": "low",
                "status": "planned",
                "created_at": today.isoformat(),
            },
            {
                "plan_id": "demo-plan-rds-resize",
                "title": "Resize RDS instance",
                "action_type": "update",
                "target_services": ["RDS"],
                "estimated_cost": 18.0,
                "risk_level": "medium",
                "status": "planned",
                "created_at": today.isoformat(),
            },
        ]
        approvals = self._pending_approvals(blueprints) or [
            {
                "plan_id": "demo-approval-fastapi",
                "user_prompt": "Deploy FastAPI backend",
                "summary": "Create Lambda, API Gateway, and IAM execution role for the backend API.",
                "services_to_create": ["Lambda", "API Gateway", "IAM"],
                "services_to_modify": [],
                "services_to_delete": [],
                "estimated_monthly_cost": 8.4,
                "risk_level": "medium",
                "approval_actions": ["approve", "reject", "edit_plan"],
            }
        ]
        running_resources = [
            self._running_payload(resource)
            for resource in resources
            if resource["status"] in {"running", "active"}
        ]
        activity = self._recent_activity(
            blueprints,
            deployments,
            resources,
            broken_resources,
            ["Demo data is active until AWS credentials are added."],
        )
        if not activity:
            activity = [
                {
                    "id": "demo-activity-plan",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "plan",
                    "title": "Plan generated",
                    "description": "Deploy FastAPI backend to Lambda is ready for review.",
                    "status": "info",
                },
                {
                    "id": "demo-activity-warning",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "warning",
                    "title": "Broken resource detected",
                    "description": "worker-service is below desired ECS task count.",
                    "status": "warning",
                },
            ]

        return {
            "mode": "demo",
            "banner": DEMO_BANNER,
            "warnings": [],
            "summary": {
                "total_resources": len(resources),
                "running_resources": len(running_resources),
                "broken_resources": len(broken_resources),
                "monthly_cost_estimate": costs["monthly_estimate"],
                "pending_agent_actions": len(next_actions),
                "pending_approvals": len(approvals),
            },
            "resources": resources,
            "running_resources": running_resources,
            "broken_resources": broken_resources,
            "costs": costs,
            "agent_next_actions": next_actions,
            "pending_approvals": approvals,
            "recent_activity": activity[:12],
        }

    def _collect_resources(
        self,
        session: boto3.Session,
        region: str,
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        resources: list[dict[str, Any]] = []
        for label, loader in [
            ("EC2 inventory", lambda: self._ec2_resources(session, region)),
            ("Lambda inventory", lambda: self._lambda_resources(session, region)),
            ("S3 inventory", lambda: self._s3_resources(session)),
            ("RDS inventory", lambda: self._rds_resources(session, region)),
            ("ECS inventory", lambda: self._ecs_resources(session, region)),
            (
                "CloudFormation inventory",
                lambda: self._cloudformation_resources(session, region),
            ),
            (
                "Tagged resource inventory",
                lambda: self._tagged_resources(session, region),
            ),
        ]:
            try:
                resources.extend(loader())
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                if self._is_permission_error(exc):
                    warnings.append(f"{label} needs additional AWS read permission.")
                else:
                    warnings.append(f"{label} could not be loaded from AWS.")

        deduped: dict[str, dict[str, Any]] = {}
        for resource in resources:
            deduped.setdefault(resource["id"], resource)
        return sorted(
            deduped.values(),
            key=lambda item: (item["service"], item["name"]),
        )

    def _ec2_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        ec2 = self._client(session, "ec2", region)
        resources: list[dict[str, Any]] = []
        for page in ec2.get_paginator("describe_instances").paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    state = instance.get("State", {}).get("Name", "unknown")
                    if state == "terminated":
                        continue
                    resources.append(
                        {
                            "id": instance.get("InstanceId", ""),
                            "name": self._tag_name(instance.get("Tags", []))
                            or instance.get("InstanceId", "Unnamed EC2"),
                            "service": "EC2",
                            "type": instance.get("InstanceType", "Instance"),
                            "region": region,
                            "status": "running"
                            if state == "running"
                            else "stopped"
                            if state == "stopped"
                            else "warning"
                            if state in {"pending", "stopping"}
                            else "unknown",
                            "cost_impact": "medium" if state == "running" else "none",
                            "created_at": self._iso(instance.get("LaunchTime")),
                            "tags": self._tags(instance.get("Tags", [])),
                        }
                    )
        return resources

    def _lambda_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        client = self._client(session, "lambda", region)
        resources: list[dict[str, Any]] = []
        for page in client.get_paginator("list_functions").paginate():
            for item in page.get("Functions", []):
                state = item.get("State", "Unknown")
                last_update = item.get("LastUpdateStatus", "Unknown")
                healthy = state == "Active" and last_update in {"Successful", "Unknown"}
                resources.append(
                    {
                        "id": item.get("FunctionArn", item.get("FunctionName", "")),
                        "name": item.get("FunctionName", "Unnamed Lambda"),
                        "service": "Lambda",
                        "type": item.get("Runtime", "Function"),
                        "region": region,
                        "status": "running"
                        if healthy
                        else "failed"
                        if state == "Failed" or last_update == "Failed"
                        else "warning",
                        "cost_impact": "low",
                        "created_at": item.get("LastModified"),
                        "tags": {},
                    }
                )
        return resources

    def _s3_resources(self, session: boto3.Session) -> list[dict[str, Any]]:
        s3 = self._client(session, "s3", "us-east-1")
        resources = []
        for bucket in s3.list_buckets().get("Buckets", []):
            name = bucket.get("Name", "")
            region = "us-east-1"
            try:
                region = s3.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
            except ClientError:
                pass
            resources.append(
                {
                    "id": f"s3:{name}",
                    "name": name,
                    "service": "S3",
                    "type": "Bucket",
                    "region": region,
                    "status": "active",
                    "cost_impact": "low",
                    "created_at": self._iso(bucket.get("CreationDate")),
                    "tags": {},
                }
            )
        return resources

    def _rds_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        rds = self._client(session, "rds", region)
        resources = []
        for page in rds.get_paginator("describe_db_instances").paginate():
            for item in page.get("DBInstances", []):
                status = item.get("DBInstanceStatus", "unknown")
                resources.append(
                    {
                        "id": item.get("DBInstanceArn", item.get("DBInstanceIdentifier", "")),
                        "name": item.get("DBInstanceIdentifier", "Unnamed RDS"),
                        "service": "RDS",
                        "type": item.get("Engine", "DBInstance"),
                        "region": region,
                        "status": "active"
                        if status == "available"
                        else "failed"
                        if "failed" in status.lower()
                        else "warning",
                        "cost_impact": "high"
                        if item.get("MultiAZ")
                        else "medium",
                        "created_at": self._iso(item.get("InstanceCreateTime")),
                        "tags": {},
                    }
                )
        return resources

    def _ecs_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        ecs = self._client(session, "ecs", region)
        resources = []
        cluster_arns = ecs.list_clusters().get("clusterArns", [])
        for cluster_arn in cluster_arns:
            service_arns = ecs.list_services(cluster=cluster_arn).get("serviceArns", [])
            for chunk in self._chunks(service_arns, 10):
                if not chunk:
                    continue
                response = ecs.describe_services(cluster=cluster_arn, services=chunk)
                for service in response.get("services", []):
                    desired = int(service.get("desiredCount", 0))
                    running = int(service.get("runningCount", 0))
                    status = "active" if desired == running else "warning"
                    resources.append(
                        {
                            "id": service.get("serviceArn", service.get("serviceName", "")),
                            "name": service.get("serviceName", "Unnamed ECS service"),
                            "service": "ECS",
                            "type": "Service",
                            "region": region,
                            "status": status,
                            "cost_impact": "medium" if desired else "none",
                            "created_at": self._iso(service.get("createdAt")),
                            "tags": {},
                        }
                    )
        return resources

    def _cloudformation_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        cfn = self._client(session, "cloudformation", region)
        resources = []
        for page in cfn.get_paginator("describe_stacks").paginate():
            for stack in page.get("Stacks", []):
                status = stack.get("StackStatus", "UNKNOWN")
                resources.append(
                    {
                        "id": stack.get("StackId", stack.get("StackName", "")),
                        "name": stack.get("StackName", "Unnamed stack"),
                        "service": "CloudFormation",
                        "type": "Stack",
                        "region": region,
                        "status": "active"
                        if status.endswith("COMPLETE")
                        else "failed"
                        if any(term in status for term in ["FAILED", "ROLLBACK", "DELETE_FAILED"])
                        else "warning",
                        "cost_impact": "none",
                        "created_at": self._iso(stack.get("CreationTime")),
                        "tags": self._tags(stack.get("Tags", [])),
                    }
                )
        return resources

    def _tagged_resources(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        client = self._client(session, "resourcegroupstaggingapi", region)
        resources = []
        paginator = client.get_paginator("get_resources")
        for page in paginator.paginate(ResourcesPerPage=100):
            for item in page.get("ResourceTagMappingList", []):
                arn = item.get("ResourceARN", "")
                service = self._service_from_arn(arn)
                resources.append(
                    {
                        "id": arn,
                        "name": arn.rsplit("/", 1)[-1].rsplit(":", 1)[-1] or arn,
                        "service": service,
                        "type": "Tagged resource",
                        "region": self._region_from_arn(arn) or region,
                        "status": "unknown",
                        "cost_impact": "none",
                        "created_at": None,
                        "tags": self._tags(item.get("Tags", [])),
                    }
                )
        return resources

    def _collect_broken_resources(
        self,
        session: boto3.Session,
        region: str,
        deployments: list[DeploymentRecord],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        broken = self._broken_from_failed_deployments(deployments)
        for label, loader in [
            ("CloudWatch alarms", lambda: self._broken_cloudwatch(session, region)),
            ("CloudFormation events", lambda: self._broken_cloudformation(session, region)),
            ("EC2 status checks", lambda: self._broken_ec2_status(session, region)),
            ("ECS services", lambda: self._broken_ecs(session, region)),
            ("Lambda metrics", lambda: self._broken_lambda(session, region)),
        ]:
            try:
                broken.extend(loader())
            except Exception as exc:
                if self._is_auth_error(exc):
                    raise
                if self._is_permission_error(exc):
                    warnings.append(f"{label} needs additional AWS read permission.")
                else:
                    warnings.append(f"{label} could not be inspected.")
        return broken

    def _broken_cloudwatch(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        cloudwatch = self._client(session, "cloudwatch", region)
        broken = []
        for page in cloudwatch.get_paginator("describe_alarms").paginate(StateValue="ALARM"):
            for alarm in page.get("MetricAlarms", []):
                broken.append(
                    {
                        "id": alarm.get("AlarmArn", alarm.get("AlarmName", "")),
                        "name": alarm.get("AlarmName", "CloudWatch alarm"),
                        "service": alarm.get("Namespace", "CloudWatch").replace("AWS/", ""),
                        "severity": "high",
                        "problem": "CloudWatch alarm is in ALARM state.",
                        "recommended_fix": "Open the alarm graph, inspect the breached metric, and remediate the affected resource.",
                        "source": "CloudWatch",
                    }
                )
        return broken

    def _broken_cloudformation(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        cfn = self._client(session, "cloudformation", region)
        broken = []
        for page in cfn.get_paginator("describe_stacks").paginate():
            for stack in page.get("Stacks", []):
                status = stack.get("StackStatus", "")
                if any(term in status for term in ["FAILED", "ROLLBACK", "DELETE_FAILED"]):
                    broken.append(
                        {
                            "id": stack.get("StackId", stack.get("StackName", "")),
                            "name": stack.get("StackName", "CloudFormation stack"),
                            "service": "CloudFormation",
                            "severity": "high",
                            "problem": f"Stack status is {status}.",
                            "recommended_fix": "Check CloudFormation rollback events and repair the failed resource.",
                            "source": "CloudFormation",
                        }
                    )
        return broken

    def _broken_ec2_status(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        ec2 = self._client(session, "ec2", region)
        response = ec2.describe_instance_status(IncludeAllInstances=True)
        broken = []
        for item in response.get("InstanceStatuses", []):
            system_status = item.get("SystemStatus", {}).get("Status")
            instance_status = item.get("InstanceStatus", {}).get("Status")
            if system_status == "ok" and instance_status == "ok":
                continue
            broken.append(
                {
                    "id": item.get("InstanceId", ""),
                    "name": item.get("InstanceId", "EC2 instance"),
                    "service": "EC2",
                    "severity": "high" if system_status != "ok" else "medium",
                    "problem": "EC2 system or instance status check failed.",
                    "recommended_fix": "Restart, resize, or inspect the unhealthy EC2 instance.",
                    "source": "EC2",
                }
            )
        return broken

    def _broken_ecs(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        ecs = self._client(session, "ecs", region)
        broken = []
        for cluster_arn in ecs.list_clusters().get("clusterArns", []):
            service_arns = ecs.list_services(cluster=cluster_arn).get("serviceArns", [])
            for chunk in self._chunks(service_arns, 10):
                if not chunk:
                    continue
                response = ecs.describe_services(cluster=cluster_arn, services=chunk)
                for service in response.get("services", []):
                    desired = int(service.get("desiredCount", 0))
                    running = int(service.get("runningCount", 0))
                    if desired > running:
                        broken.append(
                            {
                                "id": service.get("serviceArn", service.get("serviceName", "")),
                                "name": service.get("serviceName", "ECS service"),
                                "service": "ECS",
                                "severity": "medium",
                                "problem": f"Desired count is {desired} but running count is {running}.",
                                "recommended_fix": "Increase task capacity or inspect container logs for placement and startup failures.",
                                "source": "ECS",
                            }
                        )
        return broken

    def _broken_lambda(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        lambda_client = self._client(session, "lambda", region)
        cloudwatch = self._client(session, "cloudwatch", region)
        now = datetime.now(timezone.utc)
        broken = []
        for page in lambda_client.get_paginator("list_functions").paginate():
            for item in page.get("Functions", []):
                name = item.get("FunctionName", "")
                errors = self._lambda_metric(cloudwatch, name, "Errors", now)
                throttles = self._lambda_metric(cloudwatch, name, "Throttles", now)
                if errors or throttles:
                    broken.append(
                        {
                            "id": item.get("FunctionArn", name),
                            "name": name,
                            "service": "Lambda",
                            "severity": "medium" if errors else "low",
                            "problem": "Lambda has recent errors or throttles.",
                            "recommended_fix": "Review Lambda error logs, reserved concurrency, and retry behavior.",
                            "source": "Lambda",
                        }
                    )
        return broken

    def _collect_costs(self, session: boto3.Session) -> dict[str, Any]:
        client = self._client(session, "ce", "us-east-1")
        today = datetime.now(timezone.utc).date()
        month_start = today.replace(day=1)
        end = today + timedelta(days=1)
        daily_response = client.get_cost_and_usage(
            TimePeriod={"Start": month_start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
        service_response = client.get_cost_and_usage(
            TimePeriod={"Start": month_start.isoformat(), "End": end.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        daily = []
        currency = "USD"
        for item in daily_response.get("ResultsByTime", []):
            metric = item.get("Total", {}).get("UnblendedCost", {})
            currency = metric.get("Unit") or currency
            daily.append(
                {
                    "date": item.get("TimePeriod", {}).get("Start"),
                    "amount": round(float(metric.get("Amount", 0)), 4),
                }
            )
        by_service = []
        for result in service_response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                metric = group.get("Metrics", {}).get("UnblendedCost", {})
                amount = round(float(metric.get("Amount", 0)), 4)
                if amount:
                    by_service.append(
                        {
                            "service": group.get("Keys", ["Unknown"])[0],
                            "amount": amount,
                        }
                    )
        by_service.sort(key=lambda item: item["amount"], reverse=True)
        month_to_date = round(sum(item["amount"] for item in daily), 4)
        elapsed_days = max(today.day, 1)
        days_in_month = (date(today.year + (today.month == 12), (today.month % 12) + 1, 1) - month_start).days
        monthly_estimate = round((month_to_date / elapsed_days) * days_in_month, 4)
        today_cost = daily[-1]["amount"] if daily else 0
        return {
            "currency": currency,
            "today": today_cost,
            "month_to_date": month_to_date,
            "monthly_estimate": monthly_estimate,
            "by_service": by_service[:8],
            "daily_trend": daily,
        }

    def get_summary(
        self,
        region: str,
        credentials: dict[str, str | None],
    ) -> dict[str, Any]:
        """Return resource counts for the selected AWS region."""
        session = self._session(credentials)
        ec2 = self._client(session, "ec2", region)
        s3 = self._client(session, "s3", region)
        rds = self._client(session, "rds", region)
        iam = self._client(session, "iam", region)
        permission_warnings: list[str] = []

        def load_instances() -> list[dict[str, Any]]:
            reservations = ec2.get_paginator("describe_instances").paginate()
            return [
                instance
                for page in reservations
                for reservation in page.get("Reservations", [])
                for instance in reservation.get("Instances", [])
                if instance.get("State", {}).get("Name") != "terminated"
            ]

        instances = self._optional_metric(
            "EC2 instances", load_instances, permission_warnings
        )
        bucket_count = self._optional_metric(
            "S3 buckets",
            lambda: len(s3.list_buckets().get("Buckets", [])),
            permission_warnings,
        )
        rds_count = self._optional_metric(
            "RDS instances",
            lambda: self._count_pages(rds, "describe_db_instances", "DBInstances"),
            permission_warnings,
        )
        iam_count = self._optional_metric(
            "IAM users",
            lambda: self._count_pages(iam, "list_users", "Users"),
            permission_warnings,
        )
        vpcs = self._optional_metric(
            "VPCs",
            lambda: ec2.describe_vpcs().get("Vpcs", []),
            permission_warnings,
        )

        return {
            "region": region,
            "ec2": {
                "running": sum(
                    instance.get("State", {}).get("Name") == "running"
                    for instance in (instances or [])
                )
                if instances is not None
                else None,
                "total": len(instances) if instances is not None else None,
            },
            "s3": {"total": bucket_count},
            "rds": {"total": rds_count},
            "iam": {"total": iam_count},
            "vpc": {
                "custom": sum(
                    vpc.get("State") == "available"
                    and not vpc.get("IsDefault", False)
                    for vpc in (vpcs or [])
                )
                if vpcs is not None
                else None
            },
            "permission_warnings": permission_warnings,
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
                item.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0)
            )
            for item in response.get("ResultsByTime", [])
        }
        currency = next(
            (
                item.get("Total", {}).get("UnblendedCost", {}).get("Unit")
                for item in response.get("ResultsByTime", [])
                if item.get("Total", {}).get("UnblendedCost", {}).get("Unit")
            ),
            "USD",
        )

        daily = []
        for offset in range(30):
            day = current_start + timedelta(days=offset)
            daily.append({"date": day.isoformat(), "amount": amounts.get(day.isoformat(), 0)})

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

        return {
            "region": region,
            "instances": [
                {
                    "id": instance.get("InstanceId", ""),
                    "name": self._tag_name(instance.get("Tags", []))
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

    def _agent_next_actions(
        self, blueprints: list[DeploymentBlueprint]
    ) -> list[dict[str, Any]]:
        actions = []
        for blueprint in blueprints:
            status = self._plan_status(blueprint.status)
            if status in {"completed", "failed", "cancelled"}:
                continue
            actions.append(
                {
                    "plan_id": blueprint.blueprint_id,
                    "title": blueprint.name,
                    "action_type": self._action_type(blueprint),
                    "target_services": sorted({self._service_label(resource.service) for resource in blueprint.resources}),
                    "estimated_cost": float(blueprint.estimated_cost.estimated_monthly_total),
                    "risk_level": blueprint.security_review.risk_level,
                    "status": status,
                    "created_at": blueprint.created_at.isoformat(),
                }
            )
        return actions[:8]

    def _pending_approvals(
        self, blueprints: list[DeploymentBlueprint]
    ) -> list[dict[str, Any]]:
        approvals = []
        for blueprint in blueprints:
            if blueprint.status not in {"draft", "saved"}:
                continue
            services = sorted({self._service_label(resource.service) for resource in blueprint.resources})
            approvals.append(
                {
                    "plan_id": blueprint.blueprint_id,
                    "user_prompt": blueprint.user_prompt,
                    "summary": blueprint.summary,
                    "services_to_create": services,
                    "services_to_modify": [],
                    "services_to_delete": [],
                    "estimated_monthly_cost": float(blueprint.estimated_cost.estimated_monthly_total),
                    "risk_level": blueprint.security_review.risk_level,
                    "approval_actions": ["approve", "reject", "edit_plan"],
                }
            )
        return approvals[:6]

    def _recent_activity(
        self,
        blueprints: list[DeploymentBlueprint],
        deployments: list[DeploymentRecord],
        resources: list[dict[str, Any]],
        broken_resources: list[dict[str, Any]],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        activity: list[dict[str, Any]] = []
        for blueprint in blueprints[:8]:
            activity.append(
                {
                    "id": f"plan-{blueprint.blueprint_id}",
                    "timestamp": blueprint.created_at.isoformat(),
                    "type": "plan",
                    "title": "Plan generated",
                    "description": blueprint.name,
                    "status": "info"
                    if blueprint.status in {"draft", "saved"}
                    else "success"
                    if blueprint.status == "approved"
                    else "warning",
                }
            )
        for deployment in deployments[:8]:
            activity.append(
                {
                    "id": f"deployment-{deployment.deployment_id}",
                    "timestamp": deployment.updated_at.isoformat(),
                    "type": "deployment",
                    "title": f"Deployment {deployment.status}",
                    "description": deployment.deployment_id,
                    "status": "success"
                    if deployment.status == "deployed"
                    else "error"
                    if deployment.status == "failed"
                    else "warning",
                }
            )
        for resource in resources[:5]:
            activity.append(
                {
                    "id": f"resource-{resource['id']}",
                    "timestamp": resource.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "type": "aws",
                    "title": "Resource discovered",
                    "description": f"{resource['name']} ({resource['service']})",
                    "status": "info",
                }
            )
        for item in broken_resources[:6]:
            activity.append(
                {
                    "id": f"broken-{item['id']}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "warning",
                    "title": "Broken resource detected",
                    "description": item["problem"],
                    "status": "error"
                    if item.get("severity") in {"critical", "high"}
                    else "warning",
                }
            )
        for warning in warnings[:4]:
            activity.append(
                {
                    "id": f"warning-{uuid4().hex[:8]}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "type": "warning",
                    "title": "Dashboard warning",
                    "description": warning,
                    "status": "warning",
                }
            )
        activity.sort(key=lambda item: item["timestamp"], reverse=True)
        return activity[:12]

    def _broken_from_failed_deployments(
        self, deployments: list[DeploymentRecord]
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": deployment.deployment_id,
                "name": deployment.deployment_id,
                "service": "Agent",
                "severity": "high",
                "problem": deployment.error or "Recent deployment failed.",
                "recommended_fix": "Open deployment logs, resolve the error, and retry after review.",
                "source": "Agent",
            }
            for deployment in deployments
            if deployment.status == "failed"
        ]

    @staticmethod
    def _running_payload(resource: dict[str, Any]) -> dict[str, Any]:
        health = "Healthy" if resource["status"] in {"running", "active"} else "Unknown"
        return {
            "id": resource["id"],
            "name": resource["name"],
            "service": resource["service"],
            "current_state": resource["status"],
            "health": health,
            "region": resource["region"],
        }

    @staticmethod
    def _empty_costs() -> dict[str, Any]:
        return {
            "currency": "USD",
            "today": 0,
            "month_to_date": 0,
            "monthly_estimate": 0,
            "by_service": [],
            "daily_trend": [],
        }

    @staticmethod
    def _lambda_metric(cloudwatch: Any, function_name: str, metric: str, now: datetime) -> float:
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/Lambda",
            MetricName=metric,
            Dimensions=[{"Name": "FunctionName", "Value": function_name}],
            StartTime=now - timedelta(hours=24),
            EndTime=now,
            Period=3600,
            Statistics=["Sum"],
        )
        return sum(float(item.get("Sum", 0)) for item in response.get("Datapoints", []))

    @staticmethod
    def _tags(tags: list[dict[str, Any]]) -> dict[str, str]:
        normalized = {}
        for tag in tags or []:
            key = tag.get("Key") or tag.get("key")
            value = tag.get("Value") or tag.get("value") or ""
            if key:
                normalized[str(key)] = str(value)
        return normalized

    @classmethod
    def _tag_name(cls, tags: list[dict[str, Any]]) -> str:
        return cls._tags(tags).get("Name", "")

    @staticmethod
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _chunks(items: list[str], size: int) -> list[list[str]]:
        return [items[index:index + size] for index in range(0, len(items), size)]

    @staticmethod
    def _region_from_arn(arn: str) -> str:
        parts = arn.split(":")
        return parts[3] if len(parts) > 3 else ""

    @staticmethod
    def _service_from_arn(arn: str) -> str:
        parts = arn.split(":")
        service = parts[2] if len(parts) > 2 else "AWS"
        return DashboardService._service_label(service)

    @staticmethod
    def _service_label(service: str) -> str:
        mapping = {
            "apigateway": "API Gateway",
            "cloudformation": "CloudFormation",
            "cloudfront": "CloudFront",
            "cloudwatch": "CloudWatch",
            "ec2": "EC2",
            "ecs": "ECS",
            "elasticloadbalancing": "ELB",
            "iam": "IAM",
            "lambda": "Lambda",
            "rds": "RDS",
            "s3": "S3",
        }
        return mapping.get(str(service).lower(), str(service).upper())

    @staticmethod
    def _plan_status(status: str) -> str:
        mapping = {
            "draft": "planned",
            "saved": "pending_approval",
            "approved": "approved",
            "deploying": "executing",
            "deployed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        return mapping.get(status, status)

    @staticmethod
    def _action_type(blueprint: DeploymentBlueprint) -> str:
        prompt = blueprint.user_prompt.lower()
        if any(term in prompt for term in ["delete", "remove", "destroy"]):
            return "delete"
        if any(term in prompt for term in ["rollback", "restore"]):
            return "rollback"
        if any(term in prompt for term in ["resize", "update", "modify", "change"]):
            return "update"
        return "create"


dashboard_service = DashboardService()

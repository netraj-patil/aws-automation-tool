"""Read-only AWS inventory used by the Resource Explorer view."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.services.aws_credentials import explicit_session_kwargs


class ResourceService:
    """Collect searchable resources, EC2 instances, and S3 inventory."""

    def _session(self, credentials: dict[str, str | None]) -> boto3.Session:
        return boto3.Session(**explicit_session_kwargs(credentials))

    @staticmethod
    def _name_from_arn(arn: str) -> str:
        resource = arn.split(":", 5)[-1]
        return resource.rsplit("/", 1)[-1].rsplit(":", 1)[-1] or arn

    @staticmethod
    def _isoformat(value: Any) -> str | None:
        if not value:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _resource_tags(properties: list[dict[str, Any]]) -> list[dict[str, str]]:
        tags: list[dict[str, str]] = []
        for prop in properties:
            if str(prop.get("Name", "")).lower() not in {"tags", "tag"}:
                continue
            data = prop.get("Data")
            if isinstance(data, dict):
                tags.extend(
                    {"key": str(key), "value": str(value)}
                    for key, value in data.items()
                )
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    key = item.get("Key", item.get("key"))
                    value = item.get("Value", item.get("value", ""))
                    if key is not None:
                        tags.append({"key": str(key), "value": str(value)})
        return tags

    def search_resources(
        self,
        query: str,
        credentials: dict[str, str | None],
        region: str,
    ) -> dict[str, Any]:
        """Search the account's Resource Explorer index."""
        session = self._session(credentials)
        client = session.client("resource-explorer-2", region_name=region)
        resources: list[dict[str, Any]] = []
        next_token: str | None = None
        count: dict[str, Any] = {}
        view_arn = ""

        while True:
            params: dict[str, Any] = {
                "QueryString": query,
                "MaxResults": 1000,
            }
            if next_token:
                params["NextToken"] = next_token
            response = client.search(**params)
            count = response.get("Count", count)
            view_arn = response.get("ViewArn", view_arn)
            for item in response.get("Resources", []):
                arn = item.get("Arn", "")
                tags = self._resource_tags(item.get("Properties", []))
                identifier = self._name_from_arn(arn)
                name = next(
                    (
                        tag["value"]
                        for tag in tags
                        if tag["key"].lower() == "name" and tag["value"]
                    ),
                    identifier,
                )
                resources.append(
                    {
                        "identifier": identifier,
                        "name": name,
                        "resource_type": item.get("ResourceType", ""),
                        "type": item.get("ResourceType", ""),
                        "region": item.get("Region") or "global",
                        "account_id": item.get("OwningAccountId", ""),
                        "service": item.get("Service", ""),
                        "last_reported_at": self._isoformat(
                            item.get("LastReportedAt")
                        ),
                        "arn": arn,
                        "tags": tags,
                    }
                )
            next_token = response.get("NextToken")
            if not next_token:
                break

        return {
            "query": query,
            "count": count,
            "view_arn": view_arn,
            "resources": resources,
        }

    @staticmethod
    def _instance_name(instance: dict[str, Any]) -> str:
        return next(
            (
                tag.get("Value", "")
                for tag in instance.get("Tags", [])
                if tag.get("Key") == "Name"
            ),
            "",
        )

    @staticmethod
    def _instance_payload(
        instance: dict[str, Any], region: str
    ) -> dict[str, Any]:
        security_groups = [
            {
                "id": group.get("GroupId", ""),
                "name": group.get("GroupName", ""),
            }
            for group in instance.get("SecurityGroups", [])
        ]
        tags = [
            {"key": tag.get("Key", ""), "value": tag.get("Value", "")}
            for tag in instance.get("Tags", [])
        ]
        launch_time = instance.get("LaunchTime")
        return {
            "name": ResourceService._instance_name(instance)
            or instance.get("InstanceId", "Unnamed"),
            "instance_id": instance.get("InstanceId", ""),
            "type": instance.get("InstanceType", ""),
            "state": instance.get("State", {}).get("Name", "unknown"),
            "region": region,
            "launch_time": launch_time.isoformat() if launch_time else None,
            "public_ip": instance.get("PublicIpAddress"),
            "ami_id": instance.get("ImageId", ""),
            "vpc_id": instance.get("VpcId", ""),
            "security_groups": security_groups,
            "key_pair": instance.get("KeyName"),
            "tags": tags,
        }

    def _instances_for_region(
        self, session: boto3.Session, region: str
    ) -> list[dict[str, Any]]:
        client = session.client("ec2", region_name=region)
        pages = client.get_paginator("describe_instances").paginate()
        return [
            self._instance_payload(instance, region)
            for page in pages
            for reservation in page.get("Reservations", [])
            for instance in reservation.get("Instances", [])
            if instance.get("State", {}).get("Name") != "terminated"
        ]

    def get_ec2_instances(
        self,
        credentials: dict[str, str | None],
        home_region: str,
    ) -> dict[str, Any]:
        """Return non-terminated EC2 instances from all enabled regions."""
        session = self._session(credentials)
        home_client = session.client("ec2", region_name=home_region)
        region_items = home_client.describe_regions(
            AllRegions=True,
            Filters=[
                {
                    "Name": "opt-in-status",
                    "Values": ["opt-in-not-required", "opted-in"],
                }
            ],
        ).get("Regions", [])
        regions = sorted(
            item["RegionName"]
            for item in region_items
            if item.get("RegionName")
        )
        instances: list[dict[str, Any]] = []
        unavailable_regions: list[str] = []

        with ThreadPoolExecutor(max_workers=min(8, len(regions) or 1)) as pool:
            futures = {
                pool.submit(self._instances_for_region, session, region): region
                for region in regions
            }
            for future in as_completed(futures):
                region = futures[future]
                try:
                    instances.extend(future.result())
                except (BotoCoreError, ClientError):
                    unavailable_regions.append(region)

        instances.sort(key=lambda item: (item["region"], item["instance_id"]))

        return {
            "regions": regions,
            "instances": instances,
            "unavailable_regions": sorted(unavailable_regions),
        }

    @staticmethod
    def _bucket_region(s3: Any, bucket: str) -> str:
        location = s3.get_bucket_location(Bucket=bucket).get(
            "LocationConstraint"
        )
        return location or "us-east-1"

    @staticmethod
    def _bucket_is_public(s3: Any, bucket: str) -> bool:
        try:
            if s3.get_bucket_policy_status(Bucket=bucket).get(
                "PolicyStatus", {}
            ).get("IsPublic", False):
                return True
        except ClientError:
            pass

        try:
            public_uris = {
                "http://acs.amazonaws.com/groups/global/AllUsers",
                "http://acs.amazonaws.com/groups/global/AuthenticatedUsers",
            }
            return any(
                grant.get("Grantee", {}).get("URI") in public_uris
                for grant in s3.get_bucket_acl(Bucket=bucket).get("Grants", [])
            )
        except ClientError:
            return False

    @staticmethod
    def _latest_metric_value(
        cloudwatch: Any,
        bucket: str,
        metric_name: str,
        storage_type: str,
    ) -> float | None:
        now = datetime.now(timezone.utc)
        response = cloudwatch.get_metric_statistics(
            Namespace="AWS/S3",
            MetricName=metric_name,
            Dimensions=[
                {"Name": "BucketName", "Value": bucket},
                {"Name": "StorageType", "Value": storage_type},
            ],
            StartTime=now - timedelta(days=3),
            EndTime=now,
            Period=86400,
            Statistics=["Average"],
        )
        points = response.get("Datapoints", [])
        if not points:
            return None
        latest = max(points, key=lambda item: item.get("Timestamp", now))
        return float(latest.get("Average", 0))

    def get_s3_buckets(
        self, credentials: dict[str, str | None]
    ) -> dict[str, Any]:
        """Return S3 buckets with public status and daily storage metrics."""
        session = self._session(credentials)
        s3 = session.client("s3", region_name="us-east-1")
        buckets = []

        for item in s3.list_buckets().get("Buckets", []):
            name = item.get("Name", "")
            region = self._bucket_region(s3, name)
            cloudwatch = session.client("cloudwatch", region_name=region)
            try:
                object_count = self._latest_metric_value(
                    cloudwatch, name, "NumberOfObjects", "AllStorageTypes"
                )
                size = self._latest_metric_value(
                    cloudwatch, name, "BucketSizeBytes", "StandardStorage"
                )
            except (BotoCoreError, ClientError):
                object_count = None
                size = None
            buckets.append(
                {
                    "name": name,
                    "region": region,
                    "creation_date": item.get("CreationDate").isoformat()
                    if item.get("CreationDate")
                    else None,
                    "access": "public"
                    if self._bucket_is_public(s3, name)
                    else "private",
                    "object_count": int(object_count)
                    if object_count is not None
                    else None,
                    "size": int(size) if size is not None else None,
                }
            )

        return {"buckets": buckets}

    def get_s3_objects(
        self,
        bucket: str,
        prefix: str,
        credentials: dict[str, str | None],
    ) -> dict[str, Any]:
        """Return one folder level of objects for a bucket prefix."""
        session = self._session(credentials)
        s3 = session.client("s3", region_name="us-east-1")
        folders: dict[str, dict[str, Any]] = {}
        files: list[dict[str, Any]] = []
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(
            Bucket=bucket, Prefix=prefix, Delimiter="/"
        ):
            for item in page.get("CommonPrefixes", []):
                folder_prefix = item.get("Prefix", "")
                folders[folder_prefix] = {
                    "name": folder_prefix[len(prefix):].rstrip("/"),
                    "prefix": folder_prefix,
                    "type": "folder",
                }
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                if key == prefix:
                    continue
                files.append(
                    {
                        "name": key[len(prefix):],
                        "key": key,
                        "type": "file",
                        "size": item.get("Size", 0),
                        "last_modified": item.get("LastModified").isoformat()
                        if item.get("LastModified")
                        else None,
                    }
                )

        return {
            "bucket": bucket,
            "prefix": prefix,
            "objects": [*folders.values(), *files],
        }


resource_service = ResourceService()

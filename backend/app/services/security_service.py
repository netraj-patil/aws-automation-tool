"""Rule-based security review for deployment blueprints."""

from app.models.blueprint_models import (
    BlueprintResource,
    DeploymentBlueprint,
    RiskLevel,
    SecurityReview,
    SecurityWarning,
    WarningSeverity,
)


RISK_ORDER: dict[RiskLevel, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}
SEVERITY_PENALTIES: dict[WarningSeverity, int] = {
    "info": 0,
    "low": 5,
    "medium": 15,
    "high": 30,
    "critical": 50,
}


class SecurityService:
    """Apply deterministic MVP security rules to a deployment blueprint."""

    def review(self, blueprint: DeploymentBlueprint) -> DeploymentBlueprint:
        """Attach a security score, warnings, and resource risk levels."""
        warnings: list[SecurityWarning] = []

        for resource in blueprint.resources:
            warnings.extend(self._resource_warnings(resource))

        if not self._has_monitoring(blueprint.resources):
            warnings.append(
                SecurityWarning(
                    severity="medium",
                    message="Blueprint is missing CloudWatch or equivalent monitoring.",
                    recommendation="Add CloudWatch metrics, logs, alarms, or a monitoring resource before production deployment.",
                )
            )

        if not self._has_https(blueprint.resources):
            warnings.append(
                SecurityWarning(
                    severity="medium",
                    message="Blueprint is missing HTTPS for external traffic.",
                    recommendation="Add an HTTPS listener, TLS certificate, or HTTPS-enabled entry point.",
                )
            )

        risk_level = self._review_risk_level(blueprint.resources, warnings)
        blueprint.security_review = SecurityReview(
            risk_level=risk_level,
            security_score=self._security_score(warnings),
            passed=risk_level != "critical",
            warnings=warnings,
            summary=self._summary(warnings),
        )
        return blueprint

    def _resource_warnings(
        self, resource: BlueprintResource
    ) -> list[SecurityWarning]:
        warnings: list[SecurityWarning] = []

        if self._is_database(resource) and self._is_public(resource):
            self._raise_resource_risk(resource, "high")
            warnings.append(
                SecurityWarning(
                    severity="high",
                    message="RDS database is publicly reachable.",
                    resource_id=resource.id,
                    recommendation="Place RDS in private subnets and disable public accessibility.",
                )
            )

        if self._is_s3(resource) and self._is_public(resource):
            self._raise_resource_risk(resource, "high")
            warnings.append(
                SecurityWarning(
                    severity="high",
                    message="S3 bucket is publicly reachable.",
                    resource_id=resource.id,
                    recommendation="Enable block public access unless public hosting is explicitly required.",
                )
            )

        if self._has_open_ssh(resource):
            self._raise_resource_risk(resource, "high")
            warnings.append(
                SecurityWarning(
                    severity="high",
                    message="EC2 SSH access is open to 0.0.0.0/0.",
                    resource_id=resource.id,
                    recommendation="Restrict SSH ingress to trusted CIDR ranges or use Session Manager.",
                )
            )

        if self._is_database(resource) and not self._has_backup(resource):
            self._raise_resource_risk(resource, "medium")
            warnings.append(
                SecurityWarning(
                    severity="medium",
                    message="Database backup is not configured.",
                    resource_id=resource.id,
                    recommendation="Enable automated backups and set a backup retention period.",
                )
            )

        return warnings

    def _is_public(self, resource: BlueprintResource) -> bool:
        config = resource.config
        return (
            resource.visibility == "public"
            or config.get("public") is True
            or config.get("publicly_accessible") is True
            or config.get("block_public_access") is False
        )

    def _is_database(self, resource: BlueprintResource) -> bool:
        return resource.service.lower() == "rds" or resource.type.lower() == "database"

    def _is_s3(self, resource: BlueprintResource) -> bool:
        return resource.service.lower() == "s3" or resource.type.lower() == "storage"

    def _has_backup(self, resource: BlueprintResource) -> bool:
        config = resource.config
        return (
            config.get("backup_enabled") is True
            or config.get("automated_backups") is True
            or int(config.get("backup_retention_days") or 0) > 0
        )

    def _has_open_ssh(self, resource: BlueprintResource) -> bool:
        if resource.service.lower() != "ec2":
            return False

        rules = []
        for key in ("inbound_rules", "ingress", "security_group_rules"):
            value = resource.config.get(key)
            if isinstance(value, list):
                rules.extend(value)

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            port = rule.get("port", rule.get("from_port"))
            cidr = rule.get("cidr", rule.get("cidr_block", rule.get("source")))
            if port == 22 and cidr == "0.0.0.0/0":
                return True

        ssh_cidr = resource.config.get("ssh_cidr")
        ssh_cidrs = resource.config.get("allowed_ssh_cidrs", [])
        return ssh_cidr == "0.0.0.0/0" or "0.0.0.0/0" in ssh_cidrs

    def _has_monitoring(self, resources: list[BlueprintResource]) -> bool:
        return any(
            resource.service.lower() == "cloudwatch"
            or resource.type.lower() == "monitoring"
            or resource.config.get("monitoring_enabled") is True
            for resource in resources
        )

    def _has_https(self, resources: list[BlueprintResource]) -> bool:
        return any(
            resource.config.get("https_enabled") is True
            or str(resource.config.get("listener_protocol", "")).upper() == "HTTPS"
            or "https" in resource.id.lower()
            or "https" in resource.name.lower()
            for resource in resources
        )

    def _raise_resource_risk(
        self, resource: BlueprintResource, risk_level: RiskLevel
    ) -> None:
        if RISK_ORDER[risk_level] > RISK_ORDER[resource.risk_level]:
            resource.risk_level = risk_level

    def _review_risk_level(
        self,
        resources: list[BlueprintResource],
        warnings: list[SecurityWarning],
    ) -> RiskLevel:
        warning_levels = [
            warning.severity
            for warning in warnings
            if warning.severity in RISK_ORDER
        ]
        resource_levels = [resource.risk_level for resource in resources]
        levels = [*resource_levels, *warning_levels]
        if not levels:
            return "low"
        return max(levels, key=lambda level: RISK_ORDER[level])

    def _security_score(self, warnings: list[SecurityWarning]) -> int:
        penalty = sum(SEVERITY_PENALTIES[warning.severity] for warning in warnings)
        return max(0, 100 - penalty)

    def _summary(self, warnings: list[SecurityWarning]) -> str:
        if not warnings:
            return "No MVP security warnings found."
        high_count = sum(1 for warning in warnings if warning.severity == "high")
        medium_count = sum(1 for warning in warnings if warning.severity == "medium")
        return (
            f"Rule-based review found {len(warnings)} warning(s): "
            f"{high_count} high, {medium_count} medium."
        )


security_service = SecurityService()

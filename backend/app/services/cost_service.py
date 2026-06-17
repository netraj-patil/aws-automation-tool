"""Static monthly cost estimation for deployment blueprints."""

from app.models.blueprint_models import CostEstimate, DeploymentBlueprint, BlueprintResource


STATIC_MONTHLY_PRICING: dict[str, float] = {
    "EC2_t3_micro": 8,
    "RDS_db_t3_micro": 15,
    "S3_basic": 2,
    "ALB": 18,
    "CloudWatch_basic": 3,
}


class CostService:
    """Estimate blueprint cost from resource metadata and static price entries."""

    def estimate(self, blueprint: DeploymentBlueprint) -> DeploymentBlueprint:
        """Attach per-resource and total monthly cost estimates to a blueprint."""
        breakdown: dict[str, float] = {}
        assumptions = [
            "Static MVP estimate in USD/month; excludes usage spikes, data transfer, regional variance, and free-tier effects."
        ]

        for resource in blueprint.resources:
            pricing_key = self._pricing_key(resource)
            monthly_cost = STATIC_MONTHLY_PRICING.get(pricing_key, 0)
            resource.estimated_monthly_cost = monthly_cost
            breakdown[resource.id] = monthly_cost

            if pricing_key is None:
                assumptions.append(
                    f"{resource.id} has no static pricing entry yet and is estimated at $0."
                )

        blueprint.estimated_cost = CostEstimate(
            estimated_monthly_total=sum(breakdown.values()),
            breakdown=breakdown,
            assumptions=assumptions,
        )
        return blueprint

    def _pricing_key(self, resource: BlueprintResource) -> str | None:
        service = resource.service.lower()
        resource_type = resource.type.lower()
        name = resource.name.lower()

        if service == "rds" or resource_type == "database":
            return "RDS_db_t3_micro"
        if service == "s3" or resource_type == "storage":
            return "S3_basic"
        if service == "cloudwatch" or resource_type == "monitoring":
            return "CloudWatch_basic"
        if (
            service in {"elasticloadbalancing", "elb", "alb"}
            or resource_type == "load_balancer"
            or "load balancer" in name
        ):
            return "ALB"
        if service in {"ec2", "ecs"} or resource_type == "compute":
            return "EC2_t3_micro"
        return None


cost_service = CostService()

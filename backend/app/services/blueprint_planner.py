"""Planner service for generating deployment blueprint drafts."""

import json
import os
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import Field

from app.models.blueprint_models import (
    BlueprintConnection,
    BlueprintResource,
    CostEstimate,
    DeploymentBlueprint,
    RiskLevel,
    SecurityReview,
    SecurityWarning,
    StrictBlueprintModel,
)
from app.utils.logging_decorator import get_logger


PROJECT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(PROJECT_ENV_FILE, override=True)
logger = get_logger(__name__)


class BlueprintDraftPayload(StrictBlueprintModel):
    """Validated planner JSON before application metadata is attached."""

    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    resources: list[BlueprintResource] = Field(default_factory=list)
    connections: list[BlueprintConnection] = Field(default_factory=list)


class BlueprintPlanner:
    """Generate validated DeploymentBlueprint drafts from natural language."""

    def generate(self, prompt: str) -> DeploymentBlueprint:
        """Return a validated draft blueprint for the user's prompt."""
        try:
            draft = (
                self._generate_with_llm(prompt)
                if self._llm_enabled()
                else self._deterministic_draft(prompt)
            )
        except Exception as exc:
            logger.warning(
                "Blueprint planner fell back to deterministic draft",
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            draft = self._deterministic_draft(prompt)

        return self._build_blueprint(prompt, draft)

    def _llm_enabled(self) -> bool:
        mode = os.getenv("BLUEPRINT_PLANNER_MODE", "deterministic").lower()
        return mode in {"llm", "gemini"}

    def _generate_with_llm(self, prompt: str) -> BlueprintDraftPayload:
        llm = self._build_planner_llm()
        response = llm.invoke(
            f"{self._planner_system_prompt()}\n\nUSER PROMPT:\n{prompt}"
        )
        parsed = _parse_json_object_response(_response_text(response))
        return BlueprintDraftPayload(**parsed)

    def _build_planner_llm(self) -> Any:
        from langchain_google_genai import ChatGoogleGenerativeAI

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for LLM blueprint planning")
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=gemini_api_key,
            temperature=0.1,
            timeout=30,
            max_retries=1,
        )

    def _planner_system_prompt(self) -> str:
        return (
            "You generate CloudForge Deployment Blueprint drafts. Do not call "
            "AWS APIs. Do not execute plans. Return ONLY a valid JSON object "
            "with exactly these top-level keys: name, summary, resources, "
            "connections.\n\n"
            "Each resource must contain: id, type, name, service, config, "
            "visibility, estimated_monthly_cost, risk_level. visibility must "
            "be public, private, or internal. risk_level must be low, medium, "
            "high, or critical.\n\n"
            "Each connection must contain: from, to, type, description.\n\n"
            "Include common AWS resources when the prompt mentions them: "
            "FastAPI/app/server as compute, PostgreSQL/database as RDS, "
            "S3/storage as S3, HTTPS/load balancer as an Application Load "
            "Balancer, and monitoring/production-ready as CloudWatch."
        )

    def _deterministic_draft(self, prompt: str) -> BlueprintDraftPayload:
        normalized = prompt.lower()
        resources: list[BlueprintResource] = []

        include_app = _mentions_any(
            normalized, ("fastapi", "app", "application", "server", "api")
        )
        include_db = _mentions_any(
            normalized, ("postgresql", "postgres", "database", "db", "rds")
        )
        include_s3 = _mentions_any(
            normalized, ("s3", "storage", "bucket", "object storage")
        )
        include_alb = _mentions_any(
            normalized, ("https", "load balancer", "alb", "ssl", "tls")
        )
        include_monitoring = _mentions_any(
            normalized,
            (
                "monitoring",
                "observability",
                "cloudwatch",
                "production-ready",
                "production",
                "prod",
            ),
        )

        if include_app:
            resources.append(
                BlueprintResource(
                    id="app-compute",
                    type="compute",
                    name="FastAPI application compute",
                    service="ecs",
                    config={
                        "launch_type": "FARGATE",
                        "container_port": 8000,
                        "desired_count": 2 if include_monitoring else 1,
                        "runtime": "python-fastapi",
                    },
                    visibility="private",
                    estimated_monthly_cost=55,
                    risk_level="medium",
                )
            )

        if include_db:
            resources.append(
                BlueprintResource(
                    id="postgres-database",
                    type="database",
                    name="PostgreSQL database",
                    service="rds",
                    config={
                        "engine": "postgres",
                        "multi_az": include_monitoring,
                        "storage_gb": 20,
                    },
                    visibility="private",
                    estimated_monthly_cost=65,
                    risk_level="medium",
                )
            )

        if include_s3:
            resources.append(
                BlueprintResource(
                    id="object-storage",
                    type="storage",
                    name="S3 object storage",
                    service="s3",
                    config={
                        "block_public_access": True,
                        "versioning": include_monitoring,
                        "encryption": "SSE-S3",
                    },
                    visibility="private",
                    estimated_monthly_cost=5,
                    risk_level="low",
                )
            )

        if include_alb:
            resources.append(
                BlueprintResource(
                    id="https-load-balancer",
                    type="load_balancer",
                    name="HTTPS application load balancer",
                    service="elasticloadbalancing",
                    config={
                        "scheme": "internet-facing",
                        "listener_protocol": "HTTPS",
                        "listener_port": 443,
                    },
                    visibility="public",
                    estimated_monthly_cost=22,
                    risk_level="medium",
                )
            )

        if include_monitoring:
            resources.append(
                BlueprintResource(
                    id="monitoring",
                    type="monitoring",
                    name="CloudWatch monitoring",
                    service="cloudwatch",
                    config={
                        "alarms": ["5xx_errors", "cpu_utilization", "rds_storage"],
                        "dashboard": True,
                    },
                    visibility="internal",
                    estimated_monthly_cost=10,
                    risk_level="low",
                )
            )

        if not resources:
            resources.append(
                BlueprintResource(
                    id="app-compute",
                    type="compute",
                    name="Private application compute",
                    service="ecs",
                    config={"launch_type": "FARGATE", "desired_count": 1},
                    visibility="private",
                    estimated_monthly_cost=35,
                    risk_level="low",
                )
            )

        resource_ids = {resource.id for resource in resources}
        connections = _deterministic_connections(resource_ids)
        return BlueprintDraftPayload(
            name=_draft_name(resource_ids),
            summary=_draft_summary(resource_ids),
            resources=resources,
            connections=connections,
        )

    def _build_blueprint(
        self, prompt: str, draft: BlueprintDraftPayload
    ) -> DeploymentBlueprint:
        resources = draft.resources
        breakdown = {
            resource.id: resource.estimated_monthly_cost for resource in resources
        }
        total = sum(breakdown.values())

        return DeploymentBlueprint(
            blueprint_id=f"bp_{uuid4().hex[:12]}",
            name=draft.name,
            status="draft",
            user_prompt=prompt,
            summary=draft.summary,
            resources=resources,
            connections=draft.connections,
            diagram_mermaid=_build_mermaid(draft.connections),
            estimated_cost=CostEstimate(
                estimated_monthly_total=total,
                breakdown=breakdown,
                assumptions=[
                    "Planner estimates are directional and must be reviewed before deployment."
                ],
            ),
            security_review=_security_review(resources),
        )


def _mentions_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _deterministic_connections(
    resource_ids: set[str],
) -> list[BlueprintConnection]:
    connections: list[BlueprintConnection] = []
    if {"https-load-balancer", "app-compute"} <= resource_ids:
        connections.append(
            BlueprintConnection(
                **{
                    "from": "https-load-balancer",
                    "to": "app-compute",
                    "type": "routes-to",
                    "description": "The HTTPS load balancer routes web traffic to the app compute service.",
                }
            )
        )
    if {"app-compute", "postgres-database"} <= resource_ids:
        connections.append(
            BlueprintConnection(
                **{
                    "from": "app-compute",
                    "to": "postgres-database",
                    "type": "connects-to",
                    "description": "The application reads and writes relational data in PostgreSQL.",
                }
            )
        )
    if {"app-compute", "object-storage"} <= resource_ids:
        connections.append(
            BlueprintConnection(
                **{
                    "from": "app-compute",
                    "to": "object-storage",
                    "type": "uses",
                    "description": "The application stores user or static assets in S3.",
                }
            )
        )
    if "monitoring" in resource_ids:
        for resource_id in sorted(resource_ids - {"monitoring"}):
            connections.append(
                BlueprintConnection(
                    **{
                        "from": resource_id,
                        "to": "monitoring",
                        "type": "emits-metrics-to",
                        "description": f"{resource_id} sends metrics and logs to CloudWatch.",
                    }
                )
            )
    return connections


def _draft_name(resource_ids: set[str]) -> str:
    if {"app-compute", "postgres-database"} <= resource_ids:
        return "Production FastAPI Deployment Blueprint"
    if "object-storage" in resource_ids and len(resource_ids) == 1:
        return "S3 Storage Deployment Blueprint"
    return "Generated Deployment Blueprint"


def _draft_summary(resource_ids: set[str]) -> str:
    labels = {
        "app-compute": "private application compute",
        "postgres-database": "RDS PostgreSQL",
        "object-storage": "S3 storage",
        "https-load-balancer": "public HTTPS load balancing",
        "monitoring": "CloudWatch monitoring",
    }
    included = [labels[item] for item in labels if item in resource_ids]
    return "Draft architecture with " + ", ".join(included) + "."


def _security_review(resources: list[BlueprintResource]) -> SecurityReview:
    warnings: list[SecurityWarning] = []
    if any(resource.id == "https-load-balancer" for resource in resources):
        warnings.append(
            SecurityWarning(
                severity="medium",
                message="Public HTTPS entry point requires certificate and WAF review.",
                resource_id="https-load-balancer",
                recommendation="Use ACM-managed certificates and restrict listener rules.",
            )
        )
    if any(resource.id == "object-storage" for resource in resources):
        warnings.append(
            SecurityWarning(
                severity="low",
                message="S3 bucket access policy should be reviewed before deployment.",
                resource_id="object-storage",
                recommendation="Keep block public access enabled unless explicitly required.",
            )
        )

    risk_level = _highest_risk([resource.risk_level for resource in resources])
    return SecurityReview(
        risk_level=risk_level,
        passed=risk_level != "critical",
        warnings=warnings,
        summary="Draft security review generated from blueprint resource metadata.",
    )


def _highest_risk(levels: list[RiskLevel]) -> RiskLevel:
    order: dict[RiskLevel, int] = {
        "low": 0,
        "medium": 1,
        "high": 2,
        "critical": 3,
    }
    if not levels:
        return "low"
    return max(levels, key=lambda level: order[level])


def _build_mermaid(connections: list[BlueprintConnection]) -> str | None:
    if not connections:
        return None
    lines = ["graph TD"]
    for connection in connections:
        lines.append(f"  {connection.from_resource} --> {connection.to_resource}")
    return "\n".join(lines)


def _response_text(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content)


def _parse_json_object_response(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced:
        text = fenced.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Blueprint planner response must be a JSON object")
    return parsed


blueprint_planner = BlueprintPlanner()

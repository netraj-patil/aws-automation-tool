"""Unit tests for natural-language blueprint planning."""

from types import SimpleNamespace

from app.services.blueprint_planner import BlueprintPlanner


def test_generates_production_fastapi_blueprint(monkeypatch) -> None:
    monkeypatch.delenv("BLUEPRINT_PLANNER_MODE", raising=False)
    planner = BlueprintPlanner()

    blueprint = planner.generate(
        "Deploy a production-ready FastAPI app with PostgreSQL, S3 storage, and HTTPS."
    )

    resources = {resource.id: resource for resource in blueprint.resources}
    assert blueprint.status == "draft"
    assert resources["app-compute"].type == "compute"
    assert resources["app-compute"].service == "ecs"
    assert resources["postgres-database"].service == "rds"
    assert resources["postgres-database"].config["engine"] == "postgres"
    assert resources["object-storage"].service == "s3"
    assert resources["https-load-balancer"].type == "load_balancer"
    assert resources["https-load-balancer"].visibility == "public"
    assert resources["monitoring"].service == "cloudwatch"


def test_invalid_llm_json_falls_back_safely(monkeypatch) -> None:
    planner = BlueprintPlanner()
    broken_llm = SimpleNamespace(
        invoke=lambda _: SimpleNamespace(content="this is not json")
    )
    monkeypatch.setenv("BLUEPRINT_PLANNER_MODE", "llm")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(planner, "_build_planner_llm", lambda: broken_llm)

    blueprint = planner.generate("Deploy a PostgreSQL database with monitoring.")

    resources = {resource.id: resource for resource in blueprint.resources}
    assert blueprint.status == "draft"
    assert "postgres-database" in resources
    assert "monitoring" in resources
    assert blueprint.security_review.passed is True


def test_complex_monitoring_architecture_generates_prompt_specific_diagram(monkeypatch) -> None:
    monkeypatch.delenv("BLUEPRINT_PLANNER_MODE", raising=False)
    planner = BlueprintPlanner()

    blueprint = planner.generate(
        "Create a simple AWS monitoring architecture with User, React dashboard, "
        "FastAPI backend, boto3 layer, EC2, Lambda, RDS, S3, Redis, MongoDB, "
        "Planner Agent, Cost Agent, Health Agent, and Approval Agent."
    )

    resource_ids = {resource.id for resource in blueprint.resources}
    assert {
        "user",
        "react-dashboard",
        "fastapi-backend",
        "boto3-layer",
        "ec2",
        "lambda",
        "postgres-database",
        "object-storage",
        "redis-state",
        "mongodb-history",
        "planner-agent",
        "cost-agent",
        "health-agent",
        "approval-agent",
    } <= resource_ids
    assert 'node_react_dashboard["React dashboard"]' in blueprint.diagram_mermaid
    assert 'node_fastapi_backend["FastAPI backend"]' in blueprint.diagram_mermaid
    assert 'node_mongodb_history[("MongoDB history")]' in blueprint.diagram_mermaid
    assert "node_boto3_layer --> node_ec2" in blueprint.diagram_mermaid
    assert "node_fastapi_backend --> node_planner_agent" in blueprint.diagram_mermaid

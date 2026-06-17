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

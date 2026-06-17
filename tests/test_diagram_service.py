"""Unit tests for blueprint Mermaid diagram generation."""

from app.models.blueprint_models import BlueprintConnection, BlueprintResource
from app.services.diagram_service import generate_blueprint_mermaid


def _resource(
    resource_id: str,
    resource_type: str,
    name: str,
    service: str,
) -> BlueprintResource:
    return BlueprintResource(
        id=resource_id,
        type=resource_type,
        name=name,
        service=service,
        config={},
        visibility="private",
        estimated_monthly_cost=1,
        risk_level="low",
    )


def _connection(
    from_resource: str,
    to_resource: str,
) -> BlueprintConnection:
    return BlueprintConnection(
        from_resource=from_resource,
        to_resource=to_resource,
        type="connects-to",
        description="Source connects to target.",
    )


def test_generates_connected_blueprint_diagram() -> None:
    resources = [
        _resource("app-compute", "compute", "FastAPI application compute", "ecs"),
        _resource("postgres-database", "database", "PostgreSQL database", "rds"),
    ]
    connections = [_connection("app-compute", "postgres-database")]

    diagram = generate_blueprint_mermaid(resources, connections)

    assert diagram == "\n".join(
        [
            "graph TD",
            '  node_app_compute["FastAPI application compute"]',
            '  node_postgres_database[("PostgreSQL database")]',
            "  node_app_compute --> node_postgres_database",
        ]
    )


def test_sanitizes_resource_labels_with_punctuation() -> None:
    resources = [
        _resource(
            "api service/v1!",
            "server",
            'API: "public" / v1',
            "ecs",
        )
    ]

    diagram = generate_blueprint_mermaid(resources, [])

    assert 'node_api_service_v1["API: \'public\' / v1"]' in diagram
    assert "api service/v1!" not in diagram


def test_deduplicates_sanitized_node_ids() -> None:
    resources = [
        _resource("api service", "server", "Application API", "ecs"),
        _resource("api/service", "server", "Application API", "ecs"),
    ]
    connections = [_connection("api service", "api/service")]

    diagram = generate_blueprint_mermaid(resources, connections)

    assert 'node_api_service["Application API"]' in diagram
    assert 'node_api_service_2["Application API"]' in diagram
    assert "node_api_service --> node_api_service_2" in diagram


def test_renders_nodes_when_connections_are_empty() -> None:
    resources = [
        _resource("object-storage", "storage", "S3 object storage", "s3"),
    ]

    diagram = generate_blueprint_mermaid(resources, [])

    assert diagram == "\n".join(
        [
            "graph TD",
            '  node_object_storage["S3 object storage"]',
        ]
    )


def test_skips_connections_with_unknown_resource_references() -> None:
    resources = [
        _resource("app-compute", "compute", "FastAPI application compute", "ecs"),
    ]
    connections = [_connection("app-compute", "missing-database")]

    diagram = generate_blueprint_mermaid(resources, connections)

    assert diagram == "\n".join(
        [
            "graph TD",
            '  node_app_compute["FastAPI application compute"]',
        ]
    )

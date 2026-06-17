"""Mermaid diagram generation for deployment blueprints."""

import re

from app.models.blueprint_models import BlueprintConnection, BlueprintResource


def generate_blueprint_mermaid(
    resources: list[BlueprintResource],
    connections: list[BlueprintConnection],
) -> str:
    """Return a Mermaid graph for blueprint resources and connections."""
    node_ids, node_definitions = _build_nodes(resources)
    lines = ["graph TD"]

    for node_definition in node_definitions:
        lines.append(f"  {node_definition}")

    for connection in connections:
        from_node = node_ids.get(connection.from_resource)
        to_node = node_ids.get(connection.to_resource)
        if not from_node or not to_node:
            continue
        lines.append(f"  {from_node} --> {to_node}")

    return "\n".join(lines)


def _build_nodes(
    resources: list[BlueprintResource],
) -> tuple[dict[str, str], list[str]]:
    used_node_ids: set[str] = set()
    node_ids: dict[str, str] = {}
    node_definitions: list[str] = []

    for resource in resources:
        node_id = _unique_node_id(_sanitize_node_id(resource.id), used_node_ids)
        used_node_ids.add(node_id)
        node_ids.setdefault(resource.id, node_id)
        node_definitions.append(_node_definition(node_id, resource))

    return node_ids, node_definitions


def _sanitize_node_id(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower()
    if not normalized:
        normalized = "resource"
    return f"node_{normalized}"


def _unique_node_id(base_node_id: str, used_node_ids: set[str]) -> str:
    if base_node_id not in used_node_ids:
        return base_node_id

    index = 2
    while f"{base_node_id}_{index}" in used_node_ids:
        index += 1
    return f"{base_node_id}_{index}"


def _node_definition(node_id: str, resource: BlueprintResource) -> str:
    label = _sanitize_label(resource.name)
    if _uses_database_shape(resource):
        return f'{node_id}[("{label}")]'
    return f'{node_id}["{label}"]'


def _sanitize_label(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    return normalized.replace("\\", "\\\\").replace('"', "'")


def _uses_database_shape(resource: BlueprintResource) -> bool:
    shape_terms = (
        resource.type,
        resource.service,
        resource.name,
    )
    return any(
        "database" in term.lower() or "rds" in term.lower()
        for term in shape_terms
    )

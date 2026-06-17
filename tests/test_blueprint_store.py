"""Unit tests for deployment blueprint storage."""

import pytest

from app.services.blueprint_store import (
    BlueprintNotFoundError,
    BlueprintStore,
    InvalidBlueprintTransitionError,
)


def test_create_and_get_blueprint_from_prompt() -> None:
    store = BlueprintStore()

    blueprint = store.create_from_prompt("Deploy an S3 static website")
    stored = store.get(blueprint.blueprint_id)

    assert blueprint.blueprint_id.startswith("bp_")
    assert stored.blueprint_id == blueprint.blueprint_id
    assert stored.status == "draft"
    assert stored.user_prompt == "Deploy an S3 static website"


def test_save_changes_draft_to_saved() -> None:
    store = BlueprintStore()
    blueprint = store.create_from_prompt("Deploy an ECS service")

    saved = store.save(blueprint.blueprint_id)

    assert saved.status == "saved"


def test_approve_changes_draft_or_saved_to_approved() -> None:
    store = BlueprintStore()
    draft = store.create_from_prompt("Deploy a Lambda function")
    saved = store.create_from_prompt("Deploy an RDS database")

    store.save(saved.blueprint_id)

    assert store.approve(draft.blueprint_id).status == "approved"
    assert store.approve(saved.blueprint_id).status == "approved"


def test_unknown_blueprint_raises_not_found() -> None:
    store = BlueprintStore()

    with pytest.raises(BlueprintNotFoundError):
        store.get("bp_missing")


def test_invalid_lifecycle_transition_raises() -> None:
    store = BlueprintStore()
    blueprint = store.create_from_prompt("Deploy a VPC")

    store.approve(blueprint.blueprint_id)

    with pytest.raises(InvalidBlueprintTransitionError):
        store.save(blueprint.blueprint_id)

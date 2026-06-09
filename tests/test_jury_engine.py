"""Tests for deterministic and LLM-assisted jury decisions."""

from app.services.jury.jury_config import JuryConfig
from app.services.jury.jury_engine import JuryEngine


def _config(**overrides) -> JuryConfig:
    values = {
        "gemini_api_key": "test-gemini-key",
        "grok_api_key": "test-grok-key",
    }
    values.update(overrides)
    return JuryConfig(**values)


async def test_fast_path_destructive_keyword() -> None:
    engine = JuryEngine(_config())

    def fail_if_called():
        raise AssertionError("The destructive keyword fast path called the LLM")

    engine._build_llm = fail_if_called
    verdict = await engine.evaluate_plan(
        "Delete the temporary object after validation.",
        [{"name": "update_resource"}],
    )

    assert verdict.risk_level == "high"


async def test_always_block_pattern() -> None:
    engine = JuryEngine(_config())

    def fail_if_called():
        raise AssertionError("The always-block fast path called the LLM")

    engine._build_llm = fail_if_called
    verdict = await engine.evaluate_plan(
        "Remove the VPC.",
        [{"name": "delete_vpc"}],
    )

    assert verdict.requires_explicit_approval is True


async def test_blast_radius_warning(mock_anthropic_response) -> None:
    engine = JuryEngine(_config(max_blast_radius=5))
    engine._build_llm = lambda: mock_anthropic_response
    tool_calls = [{"name": f"tool_{index}"} for index in range(6)]

    verdict = await engine.evaluate_plan("Inspect six services.", tool_calls)

    assert any("6 distinct tools" in warning for warning in verdict.warnings)


async def test_llm_path_uses_mocked_response(
    mock_anthropic_response,
) -> None:
    engine = JuryEngine(_config())
    engine._build_llm = lambda: mock_anthropic_response

    verdict = await engine.evaluate_plan(
        "List the available buckets.",
        [{"name": "list_s3_buckets"}],
    )

    assert verdict.risk_level == "low"
    mock_anthropic_response.ainvoke.assert_awaited_once()

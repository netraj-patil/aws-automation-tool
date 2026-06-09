"""Tests for the jury safety layer."""

import asyncio
from types import SimpleNamespace

from app.services.jury.jury_config import JuryConfig, JuryVerdict
from app.services.jury.jury_engine import JuryEngine
from app.services.jury.metrics import JuryMetrics


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def ainvoke(self, prompt: str) -> SimpleNamespace:
        self.calls += 1
        assert "destructiveness" in prompt
        return SimpleNamespace(content=self.response)


def _config(**overrides: object) -> JuryConfig:
    values = {
        "groq_api_key": "groq-test-key",
    }
    values.update(overrides)
    return JuryConfig(**values)


def test_always_approval_tool_skips_llm() -> None:
    engine = JuryEngine(_config())

    def fail_if_called() -> object:
        raise AssertionError("LLM must not be built on the approval fast path")

    engine._build_llm = fail_if_called  # type: ignore[method-assign]
    verdict = asyncio.run(
        engine.evaluate_plan(
            "Delete the bucket.",
            [{"function": {"name": "delete_s3_bucket"}}],
        )
    )

    assert verdict.passed is True
    assert verdict.blocked is False
    assert verdict.risk_level == "critical"
    assert verdict.requires_explicit_approval is True


def test_fast_checks_and_llm_scores_are_combined() -> None:
    engine = JuryEngine(_config(max_blast_radius=1))
    fake_llm = _FakeLLM(
        '{"destructiveness": 2, "reversibility": 8, '
        '"blast_radius": 2, "summary": "Limited impact."}'
    )
    engine._build_llm = lambda: fake_llm  # type: ignore[method-assign]

    verdict = asyncio.run(
        engine.evaluate_plan(
            "Remove the old role, then revoke its policy.",
            [{"name": "update_role"}, {"name": "list_policies"}],
        )
    )

    assert fake_llm.calls == 1
    assert verdict.risk_level == "high"
    assert len(verdict.warnings) == 3
    assert verdict.requires_explicit_approval is False


def test_critical_llm_score_requires_approval() -> None:
    engine = JuryEngine(_config())
    fake_llm = _FakeLLM(
        "```json\n"
        '{"destructiveness": 7, "reversibility": 1, '
        '"blast_radius": 3, "summary": "Destructive operation."}'
        "\n```"
    )
    engine._build_llm = lambda: fake_llm  # type: ignore[method-assign]

    verdict = asyncio.run(
        engine.evaluate_plan("Modify one resource.", [{"name": "modify_item"}])
    )

    assert verdict.risk_level == "critical"
    assert verdict.requires_explicit_approval is True
    assert verdict.warnings == ["Destructive operation."]


def test_missing_groq_key_returns_low_risk_without_llm() -> None:
    engine = JuryEngine(JuryConfig())

    def fail_if_called() -> object:
        raise AssertionError("LLM must not be built without GROQ_API_KEY")

    engine._build_llm = fail_if_called  # type: ignore[method-assign]
    verdict = asyncio.run(
        engine.evaluate_plan(
            "List the available buckets.",
            [{"name": "list_s3_buckets"}],
        )
    )

    assert verdict.risk_level == "low"
    assert verdict.requires_explicit_approval is False


def test_metrics_records_and_returns_a_copy() -> None:
    metrics = JuryMetrics()
    metrics.record(
        JuryVerdict(
            passed=True,
            risk_level="critical",
            warnings=[],
            blocked=False,
            block_reason=None,
            requires_explicit_approval=True,
        )
    )

    summary = metrics.summary()
    summary["risk_distribution"]["critical"] = 99

    assert metrics.total_plans_evaluated == 1
    assert metrics.plans_requiring_approval == 1
    assert metrics.risk_distribution["critical"] == 1

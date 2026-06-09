"""Tests for the Phase 1 agent graph."""

import asyncio
from types import SimpleNamespace

from app.services import graph
from app.services.jury.jury_config import JuryVerdict


class _FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages = None

    async def ainvoke(self, messages: list) -> SimpleNamespace:
        self.messages = messages
        return SimpleNamespace(content=self.response)


class _FakeJuryEngine:
    def __init__(self, config: object) -> None:
        self.config = config

    async def evaluate_plan(
        self, plan_text: str, tool_calls: list[dict]
    ) -> JuryVerdict:
        assert '"tool_name": "list_s3_buckets"' in plan_text
        assert tool_calls == [{"name": "list_s3_buckets"}]
        return JuryVerdict(
            passed=True,
            risk_level="low",
            warnings=[],
            blocked=False,
            block_reason=None,
            requires_explicit_approval=False,
        )


def _state() -> graph.AgentState:
    return {
        "session_id": "session-1",
        "user_message": "List my buckets",
        "messages": [],
        "plan": None,
        "plan_approved": False,
        "execution_results": [],
        "jury_verdict": None,
        "current_phase": "planning",
        "error": None,
    }


def test_planner_node_parses_structured_plan(monkeypatch) -> None:
    fake_llm = _FakeLLM(
        "```json\n"
        '[{"step_number": 1, "tool_name": "list_s3_buckets", '
        '"tool_description": "List buckets", "parameters_needed": [], '
        '"risk_level": "low", "reason": "Inspect available buckets"}]'
        "\n```"
    )
    monkeypatch.setattr(graph, "_build_planner_llm", lambda: fake_llm)

    update = asyncio.run(graph.planner_node(_state()))

    assert update["current_phase"] == "awaiting_approval"
    assert update["plan"][0]["tool_name"] == "list_s3_buckets"
    assert "Do not execute anything" in fake_llm.messages[0].content
    assert "args_schema" not in fake_llm.messages[0].content


def test_planner_node_reports_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(
        graph, "_build_planner_llm", lambda: _FakeLLM("not json")
    )

    update = asyncio.run(graph.planner_node(_state()))

    assert update["current_phase"] == "error"
    assert update["plan"] is None
    assert "Failed to generate plan" in update["error"]


def test_jury_node_serializes_verdict(monkeypatch) -> None:
    monkeypatch.setattr(graph, "JuryEngine", _FakeJuryEngine)
    monkeypatch.setattr(graph, "JuryConfig", lambda: object())
    state = _state()
    state["plan"] = [
        {
            "step_number": 1,
            "tool_name": "list_s3_buckets",
            "tool_description": "List buckets",
            "parameters_needed": [],
            "risk_level": "low",
            "reason": "Inspect available buckets",
        }
    ]
    state["current_phase"] = "awaiting_approval"

    update = asyncio.run(graph.jury_node(state))

    assert update["jury_verdict"]["risk_level"] == "low"
    assert "current_phase" not in update


def test_format_plan_for_user() -> None:
    state = _state()
    state["plan"] = [
        {
            "step_number": 1,
            "tool_name": "list_s3_buckets",
            "risk_level": "low",
            "reason": "Inspect available buckets",
        }
    ]
    state["jury_verdict"] = {
        "risk_level": "low",
        "warnings": [],
        "requires_explicit_approval": False,
    }

    formatted = graph.format_plan_for_user(state)

    assert "Step 1: list_s3_buckets" in formatted
    assert "Jury Assessment: LOW risk | No warnings" in formatted
    assert "Type 'approve'" in formatted


def test_create_agent_graph_wires_phase_one() -> None:
    compiled = graph.create_agent_graph()
    drawable = compiled.get_graph()

    assert "planner_node" in drawable.nodes
    assert "jury_node" in drawable.nodes


def test_compiled_graph_runs_through_jury(monkeypatch) -> None:
    fake_llm = _FakeLLM(
        '[{"step_number": 1, "tool_name": "list_s3_buckets", '
        '"tool_description": "List buckets", "parameters_needed": [], '
        '"risk_level": "low", "reason": "Inspect available buckets"}]'
    )
    monkeypatch.setattr(graph, "_build_planner_llm", lambda: fake_llm)
    monkeypatch.setattr(graph, "JuryEngine", _FakeJuryEngine)
    monkeypatch.setattr(graph, "JuryConfig", lambda: object())

    result = asyncio.run(graph.create_agent_graph().ainvoke(_state()))

    assert result["current_phase"] == "awaiting_approval"
    assert result["jury_verdict"]["risk_level"] == "low"

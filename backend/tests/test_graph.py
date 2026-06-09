"""Tests for the planning and execution agent graph."""

import asyncio
from types import SimpleNamespace

from app.services import graph
from app.services.jury.jury_config import JuryVerdict
from app.services.session_store import SessionStore


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


class _FakeTool:
    name = "list_s3_buckets"
    description = "List S3 buckets"

    def __init__(
        self, result: object = None, error: Exception | None = None
    ) -> None:
        self.result = result
        self.error = error
        self.payloads: list[dict] = []

    def invoke(self, payload: dict) -> object:
        self.payloads.append(payload)
        if self.error:
            raise self.error
        return self.result


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


def test_create_agent_graph_wires_full_workflow() -> None:
    compiled = graph.create_agent_graph()
    drawable = compiled.get_graph()

    assert "planner_node" in drawable.nodes
    assert "jury_node" in drawable.nodes
    assert "executor_node" in drawable.nodes
    assert "results_formatter_node" in drawable.nodes


def test_compiled_graph_runs_through_jury(monkeypatch) -> None:
    fake_llm = _FakeLLM(
        '[{"step_number": 1, "tool_name": "list_s3_buckets", '
        '"tool_description": "List buckets", "parameters_needed": [], '
        '"risk_level": "low", "reason": "Inspect available buckets"}]'
    )
    monkeypatch.setattr(graph, "_build_planner_llm", lambda: fake_llm)
    monkeypatch.setattr(graph, "JuryEngine", _FakeJuryEngine)
    monkeypatch.setattr(graph, "JuryConfig", lambda: object())

    result = asyncio.run(
        graph.create_agent_graph().ainvoke(
            _state(),
            config={"configurable": {"thread_id": "test-through-jury"}},
        )
    )

    assert result["current_phase"] == "awaiting_approval"
    assert result["jury_verdict"]["risk_level"] == "low"


def test_approval_router() -> None:
    state = _state()
    state["plan_approved"] = True
    assert graph.approval_router(state) == "executor_node"

    state["plan_approved"] = False
    state["user_message"] = "Use a different region"
    assert graph.approval_router(state) == "planner_node"

    state["current_phase"] = "error"
    assert graph.approval_router(state) == graph.END


def test_executor_injects_credentials_and_continues(monkeypatch) -> None:
    successful = _FakeTool(result=["bucket-a"])
    failing = _FakeTool(error=RuntimeError("AWS unavailable"))
    failing.name = "get_bucket_region"
    monkeypatch.setattr(
        graph, "get_all_aws_tools", lambda: [successful, failing]
    )
    monkeypatch.setattr(
        graph.session_store,
        "get_credentials",
        lambda session_id: {
            "aws_access_key_id": "stored-key",
            "aws_secret_access_key": "stored-secret",
        },
    )
    state = _state()
    state["plan"] = [
        {
            "step_number": 1,
            "tool_name": "list_s3_buckets",
            "parameters": {"aws_access_key_id": "untrusted-key"},
        },
        {
            "step_number": 2,
            "tool_name": "get_bucket_region",
            "parameters": {"bucket_name": "bucket-a"},
        },
    ]
    state["plan_approved"] = True
    state["current_phase"] = "executing"

    update = asyncio.run(graph.executor_node(state))

    assert update["current_phase"] == "done"
    assert [item["status"] for item in update["execution_results"]] == [
        "success",
        "error",
    ]
    assert successful.payloads[0]["aws_access_key_id"] == "stored-key"
    assert failing.payloads[0]["bucket_name"] == "bucket-a"


def test_results_formatter_appends_summary() -> None:
    state = _state()
    state["execution_results"] = [
        {
            "step": 1,
            "tool": "list_s3_buckets",
            "status": "success",
            "result": ["bucket-a"],
        }
    ]

    update = asyncio.run(graph.results_formatter_node(state))

    assert "✅ Completed 1/1 steps" in update["messages"][0].content


def test_run_agent_resumes_checkpoint_for_approval(monkeypatch) -> None:
    fake_llm = _FakeLLM(
        '[{"step_number": 1, "tool_name": "list_s3_buckets", '
        '"tool_description": "List buckets", "parameters_needed": [], '
        '"parameters": {}, "risk_level": "low", '
        '"reason": "Inspect available buckets"}]'
    )
    fake_tool = _FakeTool(result=["bucket-a"])
    store = SessionStore()
    store.create_session(
        "integration-session",
        {
            "aws_access_key_id": "stored-key",
            "aws_secret_access_key": "stored-secret",
        },
    )
    monkeypatch.setattr(graph, "_build_planner_llm", lambda: fake_llm)
    monkeypatch.setattr(graph, "JuryEngine", _FakeJuryEngine)
    monkeypatch.setattr(graph, "JuryConfig", lambda: object())
    monkeypatch.setattr(graph, "get_all_aws_tools", lambda: [fake_tool])
    monkeypatch.setattr(graph, "session_store", store)
    monkeypatch.setattr(graph, "agent_graph", graph.create_agent_graph())

    planning = asyncio.run(
        graph.run_agent("integration-session", "List my buckets")
    )
    completed = asyncio.run(
        graph.run_agent(
            "integration-session", "approve", plan_approved=True
        )
    )

    assert planning["phase"] == "awaiting_approval"
    assert completed["phase"] == "done"
    assert completed["results"][0]["result"] == ["bucket-a"]
    assert fake_tool.payloads[0]["aws_access_key_id"] == "stored-key"

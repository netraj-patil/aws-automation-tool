"""Phase 1 LangGraph workflow for planning and safety review."""

import json
import os
import re
from typing import Annotated, Any, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.services.aws_tools import get_all_aws_tools
from app.services.jury.jury_config import JuryConfig
from app.services.jury.jury_engine import JuryEngine
from app.utils.logging_decorator import get_logger


load_dotenv()
logger = get_logger(__name__)


class AgentState(TypedDict):
    """Shared state for both phases of the AWS automation agent."""

    session_id: str
    user_message: str
    messages: Annotated[list[BaseMessage], add_messages]
    plan: list[dict] | None
    plan_approved: bool
    execution_results: list[dict]
    jury_verdict: dict | None
    current_phase: Literal[
        "planning", "awaiting_approval", "executing", "done", "error"
    ]
    error: str | None


class _PlanStep(BaseModel):
    """Validated shape of a single planner response step."""

    model_config = ConfigDict(extra="forbid")

    step_number: int = Field(ge=1)
    tool_name: str = Field(min_length=1)
    tool_description: str
    parameters_needed: list[str]
    risk_level: Literal["low", "medium", "high"]
    reason: str = Field(min_length=1)


_PLAN_ADAPTER = TypeAdapter(list[_PlanStep])


async def planner_node(state: AgentState) -> AgentState:
    """Generate a structured, non-executing plan for the user's request."""
    try:
        tools = get_all_aws_tools()
        tool_catalog = _build_tool_catalog(tools)
        llm = _build_planner_llm()
        response = await llm.ainvoke(
            [
                SystemMessage(content=_planner_system_prompt(tool_catalog)),
                HumanMessage(content=state["user_message"]),
            ]
        )
        parsed = _parse_json_response(_response_text(response))
        plan_steps = _PLAN_ADAPTER.validate_python(parsed)
        _validate_plan_steps(plan_steps, {tool.name for tool in tools})
        plan = [step.model_dump() for step in plan_steps]

        logger.info(
            "Plan generated",
            extra={
                "session_id": state["session_id"],
                "step_count": len(plan),
            },
        )
        return cast(
            AgentState,
            {
                "plan": plan,
                "plan_approved": False,
                "jury_verdict": None,
                "current_phase": "awaiting_approval",
                "error": None,
            },
        )
    except Exception as exc:
        logger.error(
            "Plan generation failed",
            extra={
                "session_id": state.get("session_id"),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return cast(
            AgentState,
            {
                "plan": None,
                "plan_approved": False,
                "jury_verdict": None,
                "current_phase": "error",
                "error": f"Failed to generate plan: {exc}",
            },
        )


async def jury_node(state: AgentState) -> AgentState:
    """Review the structured plan with the jury safety engine."""
    plan = state.get("plan")
    if state.get("current_phase") == "error" or plan is None:
        return cast(AgentState, {})

    try:
        plan_text = json.dumps(plan, default=str)
        tool_calls = [
            {"name": step["tool_name"]}
            for step in plan
            if isinstance(step.get("tool_name"), str)
        ]
        verdict = await JuryEngine(JuryConfig()).evaluate_plan(
            plan_text, tool_calls
        )
        verdict_data = verdict.model_dump()
        update: dict[str, Any] = {"jury_verdict": verdict_data}

        if verdict.blocked:
            update.update(
                {
                    "current_phase": "error",
                    "error": verdict.block_reason
                    or "The jury blocked this plan.",
                }
            )

        logger.info(
            "Plan reviewed by jury",
            extra={
                "session_id": state["session_id"],
                "risk_level": verdict.risk_level,
                "blocked": verdict.blocked,
            },
        )
        return cast(AgentState, update)
    except Exception as exc:
        logger.error(
            "Jury evaluation failed",
            extra={
                "session_id": state.get("session_id"),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return cast(
            AgentState,
            {
                "current_phase": "error",
                "error": f"Failed to review plan: {exc}",
            },
        )


def format_plan_for_user(state: AgentState) -> str:
    """Format the plan and jury verdict for an approval response."""
    if state.get("current_phase") == "error":
        return f"Unable to prepare the plan: {state.get('error') or 'Unknown error'}"

    plan = state.get("plan") or []
    lines = ["📋 Here's what I plan to do:"]
    if not plan:
        lines.append("No actions are required.")

    for step in plan:
        lines.append(
            f"Step {step.get('step_number', '?')}: "
            f"{step.get('tool_name', 'unknown_tool')} — "
            f"{step.get('reason', 'No reason provided.')}  "
            f"⚠️ Risk: {str(step.get('risk_level', 'unknown')).lower()}"
        )

    verdict = state.get("jury_verdict")
    if verdict:
        risk_level = str(verdict.get("risk_level", "unknown")).upper()
        warnings = verdict.get("warnings") or []
        warning_text = "; ".join(str(item) for item in warnings)
        lines.append(
            f"Jury Assessment: {risk_level} risk | "
            f"{warning_text or 'No warnings'}"
        )
        if verdict.get("requires_explicit_approval"):
            lines.append("This plan requires explicit approval before execution.")
    else:
        lines.append("Jury Assessment: Not available")

    lines.append("Type 'approve' to proceed or describe what to change.")
    return "\n".join(lines)


def create_agent_graph() -> CompiledStateGraph:
    """Compile the Phase 1 planning and jury-review graph."""
    workflow = StateGraph(AgentState)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("jury_node", jury_node)
    workflow.add_edge(START, "planner_node")
    workflow.add_edge("planner_node", "jury_node")
    workflow.add_edge("jury_node", END)
    return workflow.compile(interrupt_after=["jury_node"])


def _build_planner_llm() -> Any:
    provider = os.getenv("PLANNER_MODEL_PROVIDER", "gemini").lower()
    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'langchain-google-genai' package is required for Gemini"
            ) from exc

        api_key = _required_env("GEMINI_API_KEY")
        return ChatGoogleGenerativeAI(
            model=os.getenv("PLANNER_MODEL_GEMINI", "gemini-2.0-flash"),
            google_api_key=api_key,
            temperature=0,
        )

    if provider == "grok":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'langchain-openai' package is required for Grok"
            ) from exc

        api_key = _required_env("GROK_API_KEY")
        return ChatOpenAI(
            base_url="https://api.x.ai/v1",
            api_key=api_key,
            model=os.getenv("PLANNER_MODEL_GROK", "grok-3"),
            temperature=0,
        )

    raise ValueError(
        "PLANNER_MODEL_PROVIDER must be either 'gemini' or 'grok'"
    )


def _build_tool_catalog(tools: list[Any]) -> str:
    entries = []
    for tool in tools:
        description = " ".join(str(tool.description or "").split())
        entries.append(f"- {tool.name}: {description}")
    return "\n".join(entries)


def _planner_system_prompt(tool_catalog: str) -> str:
    return (
        "You plan AWS automation tasks using only the tools listed below. "
        "Do not execute anything. Only produce the plan.\n\n"
        "Return ONLY a valid JSON list. Each step must contain exactly: "
        '"step_number" (integer starting at 1), "tool_name" (listed tool), '
        '"tool_description" (short string), "parameters_needed" (list of '
        'parameter names), "risk_level" ("low", "medium", or "high"), and '
        '"reason" (short string). Order steps by execution dependency. Never '
        "include AWS credentials in parameters_needed because the application "
        "injects them at execution time. If the request needs no AWS action, "
        "return an empty list.\n\n"
        f"AVAILABLE TOOLS:\n{tool_catalog}"
    )


def _validate_plan_steps(
    plan_steps: list[_PlanStep], available_tool_names: set[str]
) -> None:
    expected_numbers = list(range(1, len(plan_steps) + 1))
    actual_numbers = [step.step_number for step in plan_steps]
    if actual_numbers != expected_numbers:
        raise ValueError("Plan step numbers must be sequential and start at 1")

    unknown_tools = sorted(
        {
            step.tool_name
            for step in plan_steps
            if step.tool_name not in available_tool_names
        }
    )
    if unknown_tools:
        raise ValueError(
            f"Planner selected unknown tool(s): {', '.join(unknown_tools)}"
        )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} environment variable is required")
    return value


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


def _parse_json_response(content: str) -> list[dict]:
    text = content.strip()
    fenced = re.fullmatch(
        r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE
    )
    if fenced:
        text = fenced.group(1)
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Planner response must be a JSON list")
    return parsed

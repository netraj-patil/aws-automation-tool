"""LangGraph workflow for planning, approval, and AWS tool execution."""

# LLM CONFIGURATION
# Planner: gemini-2.5-flash via langchain-google-genai (GEMINI_API_KEY)
# Jury: Groq via langchain-groq (GROQ_API_KEY or GROK_API_KEY)
# Last smoke tested: 2026-06-09

import json
import os
import re
from typing import Annotated, Any, Literal, TypedDict, cast

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.services.aws_tools import get_all_aws_tools
from app.services.jury.jury_engine import get_jury_engine
from app.services.session_store import session_store
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
    parameters: dict[str, Any] = Field(default_factory=dict)
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
                "user_message": "",
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
                "user_message": "",
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
        verdict = await get_jury_engine().evaluate_plan(plan_text, tool_calls)
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


def approval_router(
    state: AgentState,
) -> Literal["executor_node", "planner_node", END]:
    """Route an approved plan to execution or a refinement back to planning."""
    if state.get("current_phase") == "error" or state.get("error"):
        return END
    if state.get("plan_approved") is True:
        return "executor_node"
    if _contains_refinement(state.get("user_message", "")):
        return "planner_node"
    return END


async def executor_node(state: AgentState) -> AgentState:
    """Execute every approved plan step, recording failures without aborting."""
    tools_by_name = {tool.name: tool for tool in get_all_aws_tools()}
    results = list(state.get("execution_results") or [])

    try:
        credentials = session_store.get_credentials(state["session_id"])
    except Exception as exc:
        logger.error(
            "Failed to load AWS credentials",
            extra={
                "session_id": state.get("session_id"),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        return cast(
            AgentState,
            {
                "execution_results": results,
                "current_phase": "error",
                "error": f"Failed to load AWS credentials: {exc}",
            },
        )

    for index, step in enumerate(state.get("plan") or [], start=1):
        step_number = step.get("step_number", index)
        tool_name = str(step.get("tool_name", ""))
        try:
            tool = tools_by_name.get(tool_name)
            if tool is None:
                raise ValueError(f"Unknown AWS tool: {tool_name}")

            parameters = step.get("parameters") or {}
            if not isinstance(parameters, dict):
                raise ValueError("Plan step parameters must be an object")

            result = tool.invoke({**parameters, **credentials})
            results.append(
                {
                    "step": step_number,
                    "tool": tool_name,
                    "status": "success",
                    "result": _serialize_result(result),
                }
            )
        except Exception as exc:
            logger.error(
                "AWS plan step failed",
                extra={
                    "session_id": state.get("session_id"),
                    "step": step_number,
                    "tool": tool_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            results.append(
                {
                    "step": step_number,
                    "tool": tool_name,
                    "status": "error",
                    "result": str(exc),
                }
            )

    return cast(
        AgentState,
        {
            "execution_results": results,
            "current_phase": "done",
            "error": None,
        },
    )


async def results_formatter_node(state: AgentState) -> AgentState:
    """Append a concise execution summary for the user."""
    results = state.get("execution_results") or []
    succeeded = sum(item.get("status") == "success" for item in results)
    details = [
        f"Step {item.get('step', '?')} ({item.get('tool', 'unknown')}): "
        f"{item.get('status', 'unknown')} - {item.get('result')}"
        for item in results
    ]
    summary = (
        f"✅ Completed {succeeded}/{len(results)} steps. Here's what happened:"
    )
    if details:
        summary = f"{summary}\n" + "\n".join(details)
    return cast(AgentState, {"messages": [AIMessage(content=summary)]})


def create_agent_graph() -> CompiledStateGraph:
    """Compile the complete checkpointed planning and execution graph."""
    workflow = StateGraph(AgentState)
    workflow.add_node("planner_node", planner_node)
    workflow.add_node("jury_node", jury_node)
    workflow.add_node("executor_node", executor_node)
    workflow.add_node("results_formatter_node", results_formatter_node)
    workflow.add_edge(START, "planner_node")
    workflow.add_edge("planner_node", "jury_node")
    workflow.add_conditional_edges(
        "jury_node",
        approval_router,
        {
            "executor_node": "executor_node",
            "planner_node": "planner_node",
            END: END,
        },
    )
    workflow.add_edge("executor_node", "results_formatter_node")
    workflow.add_edge("results_formatter_node", END)
    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["executor_node"],
    )


agent_graph = create_agent_graph()


async def run_agent(
    session_id: str, user_message: str, plan_approved: bool = False
) -> dict:
    """Single entry point for both planning and execution phases."""
    history = session_store.get_messages(session_id)
    config = {"configurable": {"thread_id": session_id}}
    snapshot = await agent_graph.aget_state(config)

    is_active_checkpoint = (
        bool(snapshot.values)
        and snapshot.values.get("current_phase") != "done"
        and not (
            snapshot.values.get("current_phase") == "error"
            and not plan_approved
        )
    )
    if is_active_checkpoint:
        await agent_graph.aupdate_state(
            config,
            {
                "user_message": user_message,
                "plan_approved": plan_approved,
                "current_phase": (
                    "executing" if plan_approved else "awaiting_approval"
                ),
                "error": None,
            },
            as_node="jury_node",
        )
        state = await agent_graph.ainvoke(None, config=config)
        if plan_approved and state.get("current_phase") != "done":
            state = await agent_graph.ainvoke(None, config=config)
    else:
        messages = [_stored_message(item) for item in history]
        messages.append(HumanMessage(content=user_message))
        initial_state: AgentState = {
            "session_id": session_id,
            "user_message": user_message,
            "messages": messages,
            "plan": None,
            "plan_approved": plan_approved,
            "execution_results": [],
            "jury_verdict": None,
            "current_phase": "planning",
            "error": None,
        }
        state = await agent_graph.ainvoke(initial_state, config=config)

    phase = state.get("current_phase", "error")
    if phase == "done":
        message = _latest_message_text(state)
        results = state.get("execution_results") or []
        response = {
            "phase": phase,
            "results": results,
            "message": message,
        }
    else:
        message = format_plan_for_user(state)
        response = {
            "phase": phase,
            "plan": state.get("plan"),
            "message": message,
        }

    session_store.append_message(session_id, "user", user_message)
    session_store.append_message(session_id, "assistant", message)
    return response


def _build_planner_llm() -> Any:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    google_api_key = os.environ.pop("GOOGLE_API_KEY", None)
    try:
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            api_key=gemini_api_key,
            temperature=0.1,
            timeout=30,
            max_retries=1,
        )
    finally:
        if google_api_key is not None:
            os.environ["GOOGLE_API_KEY"] = google_api_key


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
        'parameter names), "parameters" (object containing the corresponding '
        'values), "risk_level" ("low", "medium", or "high"), and '
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


def _contains_refinement(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False
    approval_words = {"approve", "approved", "yes", "proceed", "execute"}
    return normalized not in approval_words


def _serialize_result(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump()
    try:
        json.dumps(result)
        return result
    except (TypeError, ValueError):
        return str(result)


def _stored_message(message: dict[str, str]) -> BaseMessage:
    content = message.get("content", "")
    if message.get("role") == "assistant":
        return AIMessage(content=content)
    return HumanMessage(content=content)


def _latest_message_text(state: AgentState) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    return _response_text(messages[-1])

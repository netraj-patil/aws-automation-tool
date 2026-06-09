"""LLM-assisted safety evaluation for proposed AWS plans."""

import json
import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from app.services.jury.jury_config import JuryConfig, JuryVerdict
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)


class _LLMAssessment(BaseModel):
    """Validated structured response from the jury model."""

    destructiveness: float = Field(ge=0, le=10)
    reversibility: float = Field(ge=0, le=10)
    blast_radius: float = Field(ge=0, le=10)
    summary: str


class JuryEngine:
    """Review an agent plan before any AWS tool is executed."""

    def __init__(self, config: JuryConfig):
        self.config = config

    async def evaluate_plan(
        self, plan: str, tool_calls: list[dict]
    ) -> JuryVerdict:
        """Combine deterministic safety checks with an independent LLM review."""
        tool_names = {
            name
            for tool_call in tool_calls
            if (name := self._tool_name(tool_call)) is not None
        }
        approval_tools = sorted(
            tool_names.intersection(self.config.always_block_patterns)
        )

        if approval_tools:
            warning = (
                "Explicit approval is required for tool(s): "
                f"{', '.join(approval_tools)}."
            )
            verdict = JuryVerdict(
                passed=True,
                risk_level="critical",
                warnings=[warning],
                blocked=False,
                block_reason=None,
                requires_explicit_approval=True,
            )
            logger.warning(
                "Plan requires explicit approval",
                extra={"tool_names": approval_tools, "risk_level": "critical"},
            )
            return verdict

        warnings: list[str] = []
        risk_level = "low"

        destructive_matches = self._count_destructive_matches(plan)
        if re.search(r"\bdelete\b", plan, flags=re.IGNORECASE):
            return JuryVerdict(
                passed=True,
                risk_level="high",
                warnings=["Plan contains a destructive delete action."],
                blocked=False,
                block_reason=None,
                requires_explicit_approval=False,
            )

        if destructive_matches >= 2:
            risk_level = "high"
            warnings.append(
                "Plan contains multiple destructive action references "
                f"({destructive_matches} matches)."
            )

        if len(tool_names) > self.config.max_blast_radius:
            warnings.append(
                "Plan touches "
                f"{len(tool_names)} distinct tools, exceeding the configured "
                f"maximum of {self.config.max_blast_radius}."
            )

        assessment = await self._evaluate_with_llm(plan, tool_calls)
        if (
            assessment.destructiveness >= 7
            or assessment.blast_radius >= 7
        ):
            risk_level = "critical"
        elif (
            assessment.destructiveness >= 5
            or assessment.blast_radius >= 5
        ) and risk_level != "critical":
            risk_level = "high"

        if risk_level in {"high", "critical"} and assessment.summary:
            warnings.append(assessment.summary)

        requires_approval = risk_level == "critical"
        verdict = JuryVerdict(
            passed=True,
            risk_level=risk_level,
            warnings=warnings,
            blocked=False,
            block_reason=None,
            requires_explicit_approval=requires_approval,
        )
        logger.info(
            "Plan evaluated",
            extra={
                "risk_level": verdict.risk_level,
                "requires_explicit_approval": requires_approval,
                "distinct_tool_count": len(tool_names),
                "destructive_keyword_matches": destructive_matches,
            },
        )
        return verdict

    async def _evaluate_with_llm(
        self, plan: str, tool_calls: list[dict]
    ) -> _LLMAssessment:
        llm = self._build_llm()
        prompt = self._build_prompt(plan, tool_calls)
        response = await llm.ainvoke(prompt)
        content = self._response_text(response)
        payload = self._parse_json_response(content)
        return _LLMAssessment.model_validate(payload)

    def _build_llm(self) -> Any:
        if self.config.jury_model_provider == "gemini":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as exc:
                raise RuntimeError(
                    "The 'langchain-google-genai' package is required for "
                    "Gemini jury evaluations"
                ) from exc
            return ChatGoogleGenerativeAI(
                model=self.config.jury_model_gemini,
                google_api_key=self.config.gemini_api_key,
                temperature=0,
            )

        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The 'langchain-openai' package is required for Grok jury "
                "evaluations"
            ) from exc
        return ChatOpenAI(
            base_url="https://api.x.ai/v1",
            api_key=self.config.grok_api_key,
            model=self.config.jury_model_grok,
            temperature=0,
        )

    @staticmethod
    def _build_prompt(plan: str, tool_calls: list[dict]) -> str:
        serialized_calls = json.dumps(tool_calls, default=str, indent=2)
        return (
            "You are an independent safety reviewer for an AWS automation "
            "agent. Evaluate the proposed plan and tool calls on these axes:\n"
            "- destructiveness: 0 (non-destructive) to 10 (catastrophic)\n"
            "- reversibility: 0 (irreversible) to 10 (fully reversible)\n"
            "- blast_radius: 0 (one harmless resource) to 10 (widespread impact)\n\n"
            "Respond ONLY with valid JSON containing exactly these keys: "
            '"destructiveness", "reversibility", "blast_radius", and "summary". '
            "The three scores must be numbers from 0 to 10 and summary must be "
            "a concise string.\n\n"
            f"PLAN:\n{plan}\n\nTOOL CALLS:\n{serialized_calls}"
        )

    def _count_destructive_matches(self, plan: str) -> int:
        return sum(
            len(
                re.findall(
                    rf"\b{re.escape(keyword)}\b",
                    plan,
                    flags=re.IGNORECASE,
                )
            )
            for keyword in self.config.destructive_keywords
        )

    @staticmethod
    def _tool_name(tool_call: dict) -> str | None:
        for key in ("name", "tool", "tool_name"):
            value = tool_call.get(key)
            if isinstance(value, str) and value:
                return value

        function = tool_call.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str) and name:
                return name
        return None

    @staticmethod
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

    @staticmethod
    def _parse_json_response(content: str) -> dict[str, Any]:
        text = content.strip()
        fenced = re.fullmatch(
            r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE
        )
        if fenced:
            text = fenced.group(1)
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("Jury model response must be a JSON object")
        return parsed


@lru_cache(maxsize=1)
def get_jury_engine() -> JuryEngine:
    """Return the process-wide jury engine singleton."""
    return JuryEngine(JuryConfig())

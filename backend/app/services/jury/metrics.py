"""In-memory metrics for jury safety decisions."""

from app.services.jury.jury_config import JuryVerdict
from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)


class JuryMetrics:
    """Track aggregate jury outcomes for the current process."""

    def __init__(self) -> None:
        self.total_plans_evaluated = 0
        self.plans_blocked = 0
        self.plans_requiring_approval = 0
        self.risk_distribution = {
            "low": 0,
            "medium": 0,
            "high": 0,
            "critical": 0,
        }

    def record(self, verdict: JuryVerdict) -> None:
        """Record one completed jury evaluation."""
        self.total_plans_evaluated += 1
        if verdict.blocked:
            self.plans_blocked += 1
        if verdict.requires_explicit_approval:
            self.plans_requiring_approval += 1
        self.risk_distribution[verdict.risk_level] += 1
        logger.info(
            "Jury metrics updated",
            extra={
                "total_plans_evaluated": self.total_plans_evaluated,
                "risk_level": verdict.risk_level,
            },
        )

    def summary(self) -> dict:
        """Return a plain, mutation-safe snapshot of all metrics."""
        return {
            "total_plans_evaluated": self.total_plans_evaluated,
            "plans_blocked": self.plans_blocked,
            "plans_requiring_approval": self.plans_requiring_approval,
            "risk_distribution": dict(self.risk_distribution),
        }

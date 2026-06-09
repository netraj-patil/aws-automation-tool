"""Configuration and result models for the jury safety system."""

from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)


class JuryConfig(BaseSettings):
    """Runtime configuration for plan safety evaluation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    gemini_api_key: str = Field(validation_alias="GEMINI_API_KEY")
    grok_api_key: str = Field(validation_alias="GROK_API_KEY")
    jury_model_provider: Literal["gemini", "grok"] = "gemini"
    jury_model_gemini: str = "gemini-2.0-flash"
    jury_model_grok: str = "grok-3-mini"
    destructive_keywords: list[str] = Field(
        default_factory=lambda: [
            "delete",
            "terminate",
            "remove",
            "destroy",
            "drop",
            "purge",
            "detach",
            "revoke",
        ]
    )
    max_blast_radius: int = Field(default=5, ge=0)
    always_block_patterns: list[str] = Field(
        default_factory=lambda: [
            "delete_vpc",
            "delete_ec2_instance",
            "delete_rds_instance",
            "delete_s3_bucket",
            "delete_iam_user",
        ]
    )


class JuryVerdict(BaseModel):
    """Final safety decision for an agent plan."""

    passed: bool
    risk_level: Literal["low", "medium", "high", "critical"]
    warnings: list[str] = Field(default_factory=list)
    blocked: bool
    block_reason: str | None = None
    requires_explicit_approval: bool

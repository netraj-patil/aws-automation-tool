"""Configuration and result models for the jury safety system."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, Field
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

    groq_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY", "GROK_API_KEY"),
    )
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

"""Shared fixtures and import setup for the root test suite."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.session_store import SessionStore


@pytest.fixture
def fake_credentials() -> dict[str, str]:
    return {
        "aws_access_key_id": "AKIATEST",
        "aws_secret_access_key": "fakesecret",
        "region": "us-east-1",
    }


@pytest.fixture
def real_credentials() -> dict[str, str]:
    load_dotenv()
    key = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not key or not secret:
        pytest.skip("Real AWS credentials not set in .env")
    return {
        "aws_access_key_id": key,
        "aws_secret_access_key": secret,
        "region": "ap-south-1",
    }


@pytest.fixture
def memory_session_store() -> SessionStore:
    return SessionStore("memory")


@pytest.fixture
def mock_anthropic_response() -> MagicMock:
    llm = MagicMock(name="ChatAnthropic")
    llm.ainvoke = AsyncMock(
        return_value=SimpleNamespace(
            content=(
                '{"destructiveness": 1, "reversibility": 9, '
                '"blast_radius": 1, "summary": "Low risk."}'
            )
        )
    )
    return llm

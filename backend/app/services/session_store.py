"""Conversation session storage backed by memory or Redis."""

import json
import os
import time
from typing import Any, Literal

from app.utils.logging_decorator import get_logger


logger = get_logger(__name__)


class SessionNotFoundError(KeyError):
    """Raised when an operation references an unknown session ID."""


class SessionStore:
    """Store conversation messages and AWS credentials by session ID."""

    _REDIS_PREFIX = "aws-automation:session:"

    def __init__(self, backend: Literal["memory", "redis"] = "memory") -> None:
        """Initialize a memory or Redis-backed session store."""
        if backend not in {"memory", "redis"}:
            raise ValueError("backend must be either 'memory' or 'redis'")

        self.backend = backend
        self._sessions: dict[str, dict[str, Any]] = {}
        self._redis: Any = None

        if backend == "redis":
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                raise ValueError(
                    "REDIS_URL environment variable is required for Redis backend"
                )
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError(
                    "The 'redis' package is required for Redis backend"
                ) from exc
            self._redis = redis.from_url(redis_url, decode_responses=True)

    def create_session(
        self, session_id: str, aws_credentials: dict[str, Any]
    ) -> None:
        """Create or replace a session with empty message history."""
        timestamp = self._timestamp()
        session = {
            "messages": [],
            "aws_credentials": dict(aws_credentials),
            "created_at": timestamp,
            "last_active": timestamp,
        }
        self._save(session_id, session)
        logger.info("Session created", extra={"session_id": session_id})

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        """Return a copy of the session's serialized message history."""
        session = self._get(session_id)
        self._touch(session_id, session)
        return [dict(message) for message in session["messages"]]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """Append a serialized message to an existing session."""
        session = self._get(session_id)
        session["messages"].append({"role": role, "content": content})
        session["last_active"] = self._timestamp()
        self._save(session_id, session)

    def get_credentials(self, session_id: str) -> dict[str, Any]:
        """Return a copy of the AWS credentials stored for a session."""
        session = self._get(session_id)
        self._touch(session_id, session)
        return dict(session["aws_credentials"])

    def session_exists(self, session_id: str) -> bool:
        """Return whether the requested session exists."""
        if self.backend == "memory":
            return session_id in self._sessions
        return bool(self._redis.exists(self._redis_key(session_id)))

    def delete_session(self, session_id: str) -> None:
        """Delete an existing session."""
        if not self.session_exists(session_id):
            raise SessionNotFoundError(session_id)
        if self.backend == "memory":
            del self._sessions[session_id]
        else:
            self._redis.delete(self._redis_key(session_id))
        logger.info("Session deleted", extra={"session_id": session_id})

    def clear_all(self) -> None:
        """Delete all sessions in this store; intended for tests only."""
        if self.backend == "memory":
            self._sessions.clear()
            return

        keys = list(self._redis.scan_iter(match=f"{self._REDIS_PREFIX}*"))
        if keys:
            self._redis.delete(*keys)

    @staticmethod
    def _timestamp() -> str:
        seconds = time.time()
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(seconds))
        return f"{timestamp}.{int((seconds % 1) * 1000):03d}Z"

    def _redis_key(self, session_id: str) -> str:
        return f"{self._REDIS_PREFIX}{session_id}"

    def _get(self, session_id: str) -> dict[str, Any]:
        if self.backend == "memory":
            session = self._sessions.get(session_id)
        else:
            serialized = self._redis.get(self._redis_key(session_id))
            session = json.loads(serialized) if serialized is not None else None

        if session is None:
            raise SessionNotFoundError(session_id)
        return session

    def _save(self, session_id: str, session: dict[str, Any]) -> None:
        if self.backend == "memory":
            self._sessions[session_id] = session
        else:
            self._redis.set(self._redis_key(session_id), json.dumps(session))

    def _touch(self, session_id: str, session: dict[str, Any]) -> None:
        session["last_active"] = self._timestamp()
        self._save(session_id, session)

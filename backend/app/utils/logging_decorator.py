"""Structured logging helpers for the application."""

import functools
import json
import logging
import os
import sys
import time


_REDACTED = "REDACTED"
_SENSITIVE_KEYS = {"aws_access_key_id", "aws_secret_access_key"}
_STANDARD_LOG_RECORD_KEYS = set(logging.makeLogRecord({}).__dict__)
_STANDARD_LOG_RECORD_KEYS.update({"message", "asctime"})


def _redact(value: object, key: str | None = None) -> object:
    """Return a logging-safe copy of a value with AWS credentials removed."""
    if key and key.lower() in _SENSITIVE_KEYS:
        return _REDACTED
    if isinstance(value, dict):
        return {
            item_key: _redact(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _function_arguments(
    func: object, args: tuple[object, ...], kwargs: dict[str, object]
) -> dict[str, object]:
    """Map call arguments to parameter names without adding dependencies."""
    code = func.__code__  # type: ignore[attr-defined]
    positional_names = code.co_varnames[: code.co_argcount]
    arguments = {
        name: _redact(value, name)
        for name, value in zip(positional_names, args)
    }
    if len(args) > len(positional_names):
        arguments["args"] = _redact(args[len(positional_names) :])
    arguments.update(
        {name: _redact(value, name) for name, value in kwargs.items()}
    )
    return arguments


class _JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = time.strftime(
            "%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)
        )
        payload: dict[str, object] = {
            key: _redact(value, key)
            for key, value in record.__dict__.items()
            if key not in _STANDARD_LOG_RECORD_KEYS
        }
        payload.update(
            {
                "timestamp": f"{timestamp}.{int(record.msecs):03d}Z",
                "level": record.levelname,
                "logger_name": record.name,
                "message": record.getMessage(),
            }
        )
        return json.dumps(payload, default=str, separators=(",", ":"))


def get_logger(name: str) -> logging.Logger:
    """Return a named logger configured for JSON-line output to stdout."""
    logger = logging.getLogger(name)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    handler = next(
        (
            existing_handler
            for existing_handler in logger.handlers
            if getattr(existing_handler, "_aws_automation_json_handler", False)
        ),
        None,
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler._aws_automation_json_handler = True  # type: ignore[attr-defined]
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    handler.setLevel(level)
    return logger


_tool_logger = get_logger("app.tools")


def log_tool_call(func: object) -> object:
    """Log arguments, duration, and outcome for a synchronous or async tool."""

    if func.__code__.co_flags & 0x80:  # type: ignore[attr-defined]

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            started_at = time.perf_counter()
            arguments = _function_arguments(func, args, kwargs)
            try:
                result = await func(*args, **kwargs)  # type: ignore[misc]
            except Exception as exc:
                _tool_logger.error(
                    "Tool call failed",
                    extra={
                        "function_name": func.__name__,  # type: ignore[attr-defined]
                        "arguments": arguments,
                        "execution_time_ms": round(
                            (time.perf_counter() - started_at) * 1000, 3
                        ),
                        "outcome": "error",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                raise
            _tool_logger.info(
                "Tool call succeeded",
                extra={
                    "function_name": func.__name__,  # type: ignore[attr-defined]
                    "arguments": arguments,
                    "execution_time_ms": round(
                        (time.perf_counter() - started_at) * 1000, 3
                    ),
                    "outcome": "success",
                },
            )
            return result

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> object:
        started_at = time.perf_counter()
        arguments = _function_arguments(func, args, kwargs)
        try:
            result = func(*args, **kwargs)  # type: ignore[operator]
        except Exception as exc:
            _tool_logger.error(
                "Tool call failed",
                extra={
                    "function_name": func.__name__,  # type: ignore[attr-defined]
                    "arguments": arguments,
                    "execution_time_ms": round(
                        (time.perf_counter() - started_at) * 1000, 3
                    ),
                    "outcome": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
            raise
        _tool_logger.info(
            "Tool call succeeded",
            extra={
                "function_name": func.__name__,  # type: ignore[attr-defined]
                "arguments": arguments,
                "execution_time_ms": round(
                    (time.perf_counter() - started_at) * 1000, 3
                ),
                "outcome": "success",
            },
        )
        return result

    return wrapper

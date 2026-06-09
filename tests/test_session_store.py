import pytest

from app.services.session_store import SessionNotFoundError


def test_memory_session_lifecycle(
    memory_session_store, fake_credentials
) -> None:
    memory_session_store.create_session("session-1", fake_credentials)

    assert memory_session_store.get_messages("session-1") == []
    assert (
        memory_session_store.get_credentials("session-1")
        == fake_credentials
    )

    memory_session_store.append_message("session-1", "user", "List buckets")
    memory_session_store.append_message(
        "session-1", "assistant", "Here is the plan"
    )

    assert memory_session_store.get_messages("session-1") == [
        {"role": "user", "content": "List buckets"},
        {"role": "assistant", "content": "Here is the plan"},
    ]


@pytest.mark.parametrize(
    "operation",
    ["get_messages", "append_message", "get_credentials", "delete_session"],
)
def test_unknown_session_raises(memory_session_store, operation) -> None:
    method = getattr(memory_session_store, operation)
    args = ("missing", "user", "hello") if operation == "append_message" else (
        "missing",
    )

    with pytest.raises(SessionNotFoundError):
        method(*args)


def test_delete_session_cleans_up(
    memory_session_store, fake_credentials
) -> None:
    memory_session_store.create_session("session-1", fake_credentials)
    memory_session_store.delete_session("session-1")

    assert memory_session_store.session_exists("session-1") is False
    with pytest.raises(SessionNotFoundError):
        memory_session_store.get_messages("session-1")

import pytest

from app.agent.nodes import latest_user_text
from app.ai.types import ChatMessage


def test_latest_user_text_ignores_assistant_history() -> None:
    messages = [
        ChatMessage(role="user", content="first"),
        ChatMessage(role="assistant", content="reply"),
        ChatMessage(role="user", content="latest"),
    ]

    assert latest_user_text(messages) == "latest"


def test_latest_user_text_requires_a_user_message() -> None:
    with pytest.raises(ValueError, match="user message"):
        latest_user_text([ChatMessage(role="assistant", content="reply")])

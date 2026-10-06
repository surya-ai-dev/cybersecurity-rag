"""In-memory conversation history buffer conforming to BaseConversationMemory."""

from typing import List, Optional, Union

from app.core.config import settings
from app.core.interfaces import BaseConversationMemory
from app.core.models import Message


class ConversationMemory(BaseConversationMemory):
    """In-memory buffer for managing recent multi-turn conversation history."""

    MAX_RECENT_MESSAGES: int = 6

    def __init__(
        self,
        max_recent_messages: Optional[int] = None,
    ) -> None:
        """Initialize the conversation memory buffer.

        Args:
            max_recent_messages: Maximum number of recent interaction turns to retain.
                Defaults to settings.conversation_history_limit (6).
        """
        self.max_recent_messages: int = (
            max_recent_messages
            if max_recent_messages is not None
            else getattr(settings, "conversation_history_limit", self.MAX_RECENT_MESSAGES)
        )
        self.messages: List[Message] = []

    def add_message(
        self,
        user_message: Union[str, Message],
        assistant_message: str = "",
    ) -> None:
        """Record a single interaction turn.

        Args:
            user_message: User question or prompt string (or a Message instance).
            assistant_message: Assistant response text.
        """
        if isinstance(user_message, Message):
            msg = user_message
        else:
            msg = Message(
                user=str(user_message),
                assistant=str(assistant_message),
            )

        self.messages.append(msg)
        self.messages = self.messages[-self.max_recent_messages:]

    def get_messages(self) -> List[Message]:
        """Retrieve the recorded conversation history.

        Returns:
            List of Message instances representing the most recent conversation turns.
        """
        return list(self.messages)

    def clear(self) -> None:
        """Clear all stored messages."""
        self.messages.clear()


if __name__ == "__main__":

    memory = ConversationMemory()

    memory.add_message(
        "What is least privilege?",
        "Least privilege gives a component only the permissions it needs.",
    )

    memory.add_message(
        "Why is it important?",
        "It reduces the impact of failures and misuse.",
    )

    print(memory.get_messages())
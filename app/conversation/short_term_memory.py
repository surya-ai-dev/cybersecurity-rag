"""Token-budgeted short-term working memory for Cybersecurity RAG conversations."""

from typing import List, Optional, Sequence

from app.core.models import Message


class TokenCounter:
    """Counts tokens using tiktoken with a deterministic offline fallback."""

    _ROLE_OVERHEAD_TOKENS = 8

    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        self.encoding_name = encoding_name
        self._encoding = None
        self._tiktoken_failed = False

    def _get_encoding(self):
        """Lazily load tiktoken encoding; cache failure to avoid repeated network retries."""
        if self._encoding is None and not self._tiktoken_failed:
            try:
                import tiktoken

                self._encoding = tiktoken.get_encoding(self.encoding_name)
            except Exception:
                self._tiktoken_failed = True
        return self._encoding

    def count_text(self, text: str) -> int:
        """Count tokens in plain text, falling back to char heuristic offline."""
        if not text:
            return 0
        encoding = self._get_encoding()
        if encoding is not None:
            try:
                return len(encoding.encode(text))
            except Exception:
                pass
        return max(1, len(text) // 4)

    def count_message(self, msg: Message) -> int:
        """Estimate total tokens consumed by a Message turn including role overhead."""
        user_tokens = self.count_text(msg.user)
        assistant_tokens = self.count_text(msg.assistant)
        return user_tokens + assistant_tokens + self._ROLE_OVERHEAD_TOKENS


class ShortTermMemory:
    """In-memory sliding window buffer bounded by turn count and token budget."""

    def __init__(
        self,
        max_recent_messages: int = 6,
        max_tokens: int = 1500,
        token_counter: Optional[TokenCounter] = None,
    ) -> None:
        self.max_recent_messages: int = max(0, max_recent_messages)
        self.max_tokens: int = max(0, max_tokens)
        self.token_counter: TokenCounter = token_counter if token_counter is not None else TokenCounter()
        self._messages: List[Message] = []

    def add(self, message: Message) -> List[Message]:
        """Append a turn and return any older turns evicted past max_recent_messages."""
        if self.max_recent_messages == 0:
            return [message]

        self._messages.append(message)
        evicted: List[Message] = []
        while len(self._messages) > self.max_recent_messages:
            evicted.append(self._messages.pop(0))
        return evicted

    def get_messages(self, max_tokens: Optional[int] = None) -> List[Message]:
        """Return recent turns in chronological order fitting within the token budget.

        Always preserves at least the most recent turn when budget > 0 and history
        is non-empty.
        """
        budget = self.max_tokens if max_tokens is None else max_tokens
        if budget <= 0 or not self._messages:
            return []

        selected_reversed: List[Message] = []
        running_tokens = 0

        for msg in reversed(self._messages):
            msg_tokens = self.token_counter.count_message(msg)
            if not selected_reversed:
                # Always keep the latest turn when budget > 0 so immediate follow-ups stay anchored.
                selected_reversed.append(msg)
                running_tokens += msg_tokens
                continue

            if running_tokens + msg_tokens > budget:
                break

            selected_reversed.append(msg)
            running_tokens += msg_tokens

        selected_reversed.reverse()
        return selected_reversed

    def hydrate(self, messages: Sequence[Message]) -> None:
        """Populate working memory from persisted turns, keeping the newest window."""
        if self.max_recent_messages == 0:
            self._messages = []
            return
        self._messages = list(messages)[-self.max_recent_messages :]

    def clear(self) -> None:
        """Clear all buffered turns."""
        self._messages.clear()

    def total_tokens(self, messages: Optional[Sequence[Message]] = None) -> int:
        """Compute total tokens across buffered or supplied messages."""
        target = self._messages if messages is None else messages
        return sum(self.token_counter.count_message(m) for m in target)

    def __len__(self) -> int:
        return len(self._messages)

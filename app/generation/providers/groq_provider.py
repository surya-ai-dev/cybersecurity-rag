"""Groq LLM provider implementation conforming to BaseLLMProvider."""

import os
from typing import Iterator, Optional

from dotenv import load_dotenv
from groq import Groq

from app.core.config import settings
from app.core.interfaces import BaseLLMProvider

# Ensure environment variables are loaded
load_dotenv(override=True)


class GroqProvider(BaseLLMProvider):
    """LLM provider implementation for Groq Cloud API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        """Initialize the Groq client with configuration.

        Args:
            api_key: Optional API key override. If not provided, falls back to
                centralized settings or the GROQ_API_KEY environment variable.
            model: Optional model name override. Defaults to settings.llm_model.
        """
        resolved_key = (
            api_key
            or settings.groq_api_key
            or os.getenv("GROQ_API_KEY", "")
        )

        if not resolved_key:
            raise ValueError("GROQ_API_KEY not found in .env")

        self.api_key: str = resolved_key
        self.model: str = model or settings.llm_model or "openai/gpt-oss-20b"
        self.client: Groq = Groq(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> str:
        """Generate a complete text response non-streamingly.

        Args:
            prompt: Text prompt to submit to the model.
            temperature: Sampling temperature (default: 0.0).
            max_tokens: Maximum tokens in completion (default: 8192).

        Returns:
            The complete text content of the completion.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
            stream=False,
        )

        content = response.choices[0].message.content
        return content.strip() if content else ""

    def stream(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 8192,
    ) -> Iterator[str]:
        """Stream response text chunks for a given prompt.

        Args:
            prompt: Text prompt to submit to the model.
            temperature: Sampling temperature (default: 0.0).
            max_tokens: Maximum tokens in completion (default: 8192).

        Yields:
            Incremental text chunks as they arrive from the API.
        """
        response_stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
            stream=True,
        )

        for chunk in response_stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content

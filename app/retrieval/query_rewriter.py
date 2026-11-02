"""LLM-based Query Rewriting module for document retrieval in Cybersecurity RAG.

Optimizes user questions for dense vector and lexical BM25 retrieval against
authoritative cybersecurity publications (NIST SP series, etc.) while preserving
technical standards, entities, and original intent.
"""

from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Any, Optional

from groq import Groq

from app.core.config import settings

logger = logging.getLogger(__name__)

# Specialized system prompt for document retrieval rewriting
QUERY_REWRITE_SYSTEM_PROMPT = """You are a cybersecurity document search query optimizer.
Your task is to rewrite the user's question into an optimal search query for retrieving technical sections from authoritative cybersecurity publications (such as NIST Special Publications, ISO/IEC, and OWASP).

CRITICAL RULES:
1. Output ONLY the search query on a single line. Do not include quotes, explanations, preambles, or markdown formatting.
2. DO NOT answer the question.
3. PRESERVE all document standards, publication numbers, control IDs, and formal designations exactly (e.g., "NIST SP 800-145", "NIST SP 800-218", "SP 800-53", "SSDF") present in the user question.
4. DO NOT hallucinate, inject, or guess document numbers or publication IDs (e.g. do NOT add "NIST SP 800-145" or other publication numbers) unless the user question explicitly mentions them.
5. PRESERVE and EXPAND domain-specific terminology, technical entities, acronyms, and synonyms relevant to the specific subject:
   - For cloud security monitoring: event logs, monitoring provider controls, incident response, forensics limitations.
   - For SSDF practice groups: Prepare the Organization PO, Protect Software PS, Produce Well-Secured Software PW, Respond to Vulnerabilities RV.
   - For cloud computing essential characteristics: on-demand self-service, broad network access, resource pooling, rapid elasticity, measured service.
6. Return a clean, concise, keyword-rich search query.
"""


@dataclass
class RewriteResult:
    """Encapsulates the result of a query rewriting operation."""

    original_query: str
    rewritten_query: str
    success: bool
    fallback_used: bool
    latency_ms: float
    error_message: Optional[str] = None
    model_used: Optional[str] = None


class QueryRewriter:
    """Rewrites cybersecurity queries for document retrieval using an LLM."""

    def __init__(
        self,
        client: Optional[Groq] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        enabled: Optional[bool] = None,
        max_tokens: Optional[int] = None,
    ) -> None:
        """Initialize QueryRewriter with configuration.

        Args:
            client: Optional pre-configured Groq client instance.
            model_name: Model identifier (defaults to settings.query_rewriter_model).
            api_key: Optional Groq API key override.
            timeout: API call timeout in seconds.
            max_retries: Number of retry attempts on transient failure.
            enabled: Explicit feature flag override. Defaults to settings.enable_query_rewriting.
            max_tokens: Max completion tokens for the rewriting call.
        """
        self.model_name: str = (
            model_name
            or getattr(settings, "query_rewriter_model", "qwen/qwen3.8-27b")
        )
        self.api_key: Optional[str] = api_key or getattr(settings, "groq_api_key", None) or os.getenv("GROQ_API_KEY", "")
        self.timeout: float = (
            timeout
            if timeout is not None
            else getattr(settings, "query_rewriter_timeout", 10.0)
        )
        self.max_retries: int = (
            max_retries
            if max_retries is not None
            else getattr(settings, "query_rewriter_max_retries", 2)
        )
        self.enabled: bool = (
            enabled
            if enabled is not None
            else getattr(settings, "enable_query_rewriting", False)
        )
        self.max_tokens: int = (
            max_tokens
            if max_tokens is not None
            else getattr(settings, "query_rewrite_max_tokens", 1024)
        )

        self._client: Optional[Groq] = client

    def _get_client(self) -> Groq:
        """Lazily initialize or return the underlying Groq client."""
        if self._client is None:
            resolved_key = self.api_key or os.getenv("GROQ_API_KEY", "")
            if not resolved_key:
                raise ValueError("GROQ_API_KEY not configured for QueryRewriter.")
            self._client = Groq(api_key=resolved_key, timeout=self.timeout)
        return self._client

    def _clean_response(self, text: str) -> str:
        """Clean markdown formatting, quotation marks, and preambles from response."""
        if not text:
            return ""

        cleaned = text.strip()

        # Remove markdown code block if wrapped
        if cleaned.startswith("```") and cleaned.endswith("```"):
            lines = cleaned.split("\n")
            if len(lines) >= 3:
                cleaned = "\n".join(lines[1:-1]).strip()

        # Remove enclosing quotation marks
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()

        # Remove standard preambles (e.g. "Search query: ...", "Rewritten query: ...")
        prefix_pattern = r"^(?:search\s+query|rewritten\s+query|query|optimized\s+query)\s*:\s*"
        cleaned = re.sub(prefix_pattern, "", cleaned, flags=re.IGNORECASE).strip()

        # Replace internal newlines with single space
        cleaned = " ".join(cleaned.split())

        return cleaned

    def rewrite(self, question: str) -> RewriteResult:
        """Rewrite a cybersecurity question for document retrieval.

        If disabled, empty, or if an error occurs, falls back safely to original query.

        Args:
            question: The user query to optimize.

        Returns:
            RewriteResult domain object containing status, latency, and query.
        """
        if not question or not question.strip():
            return RewriteResult(
                original_query=question,
                rewritten_query=question,
                success=True,
                fallback_used=False,
                latency_ms=0.0,
                model_used=self.model_name,
            )

        stripped_question = question.strip()

        # If rewriting is globally disabled, return original question directly
        if not self.enabled:
            return RewriteResult(
                original_query=stripped_question,
                rewritten_query=stripped_question,
                success=True,
                fallback_used=False,
                latency_ms=0.0,
                model_used=self.model_name,
            )

        t0 = time.perf_counter()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                client = self._get_client()

                response = client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT},
                        {"role": "user", "content": f"User question: {stripped_question}\nSearch query:"},
                    ],
                    temperature=0.0,
                    max_completion_tokens=self.max_tokens,
                )

                latency_ms = (time.perf_counter() - t0) * 1000
                content = response.choices[0].message.content or ""
                cleaned = self._clean_response(content)

                # Validation: must be non-empty and have substance
                if cleaned and len(cleaned) >= 3:
                    return RewriteResult(
                        original_query=stripped_question,
                        rewritten_query=cleaned,
                        success=True,
                        fallback_used=False,
                        latency_ms=latency_ms,
                        model_used=self.model_name,
                    )

                # Malformed / empty response from model
                logger.warning(
                    "Query rewriter received empty or invalid response from model %s on attempt %d.",
                    self.model_name,
                    attempt + 1,
                )
                last_error = ValueError("Empty or malformed content returned by model.")

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Query rewriter attempt %d failed: %s",
                    attempt + 1,
                    str(exc),
                )
                if attempt < self.max_retries:
                    time.sleep(0.3 * (attempt + 1))

        # Graceful fallback to original query
        latency_ms = (time.perf_counter() - t0) * 1000
        error_msg = str(last_error) if last_error else "Unknown rewriting error"

        return RewriteResult(
            original_query=stripped_question,
            rewritten_query=stripped_question,
            success=False,
            fallback_used=True,
            latency_ms=latency_ms,
            error_message=error_msg,
            model_used=self.model_name,
        )


def rewrite_query(
    question: str,
    rewriter: Optional[QueryRewriter] = None,
) -> str:
    """Convenience helper returning the rewritten query string directly."""
    active_rewriter = rewriter or QueryRewriter()
    return active_rewriter.rewrite(question).rewritten_query

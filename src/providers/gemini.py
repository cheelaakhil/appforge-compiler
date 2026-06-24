"""
Google Gemini LLM Provider

Concrete implementation using the google-genai SDK with native
structured output support (constrained decoding via response_schema).
"""

from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel

from src.providers.base import BaseLLMProvider, GenerationResult

T = TypeVar("T", bound=BaseModel)

# Gemini pricing (per 1M tokens, approximate as of 2025)
GEMINI_PRICING = {
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
}


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini provider using google-genai SDK.

    Uses native structured output via response_schema for deterministic
    JSON generation with constrained decoding.
    """

    def __init__(self, api_keys: str | list[str], max_retries: int = 2):
        super().__init__(api_keys=api_keys, max_retries=max_retries)
        self._client = None

    @property
    def client(self):
        """Lazy-initialize the Gemini client."""
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _reset_client(self):
        """Clear the cached client so it gets re-initialized with the new API key."""
        self._client = None

    def _raw_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> GenerationResult:
        """
        Execute a structured generation call using Gemini's native JSON mode.

        Uses response_mime_type="application/json" with response_schema
        set to the Pydantic model's JSON schema for constrained decoding.
        """
        from google.genai import types

        # Build the generation config with structured output
        generation_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
            temperature=temperature,
        )

        if system_instruction:
            generation_config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=generation_config,
        )

        # Parse the response
        raw_text = response.text
        parsed_data = json.loads(raw_text)

        # Extract token usage from response metadata
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return GenerationResult(
            data=parsed_data,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_used=model,
        )

    def _raw_generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> dict:
        """Execute a plain-text generation call (for repair prompts)."""
        from google.genai import types

        generation_config = types.GenerateContentConfig(
            temperature=temperature,
        )

        if system_instruction:
            generation_config.system_instruction = system_instruction

        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=generation_config,
        )

        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return {
            "text": response.text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost using Gemini-specific pricing."""
        pricing = GEMINI_PRICING.get(model, {"input": 0.10, "output": 0.40})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)

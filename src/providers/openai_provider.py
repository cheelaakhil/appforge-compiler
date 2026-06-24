"""
OpenAI LLM Provider

Concrete implementation using the openai SDK.
Supports native structured outputs via beta.chat.completions.parse.
"""

from __future__ import annotations

from typing import Type, TypeVar

from pydantic import BaseModel

from src.providers.base import BaseLLMProvider, GenerationResult

T = TypeVar("T", bound=BaseModel)

OPENAI_PRICING = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI provider using openai SDK.
    Uses native structured outputs.
    """

    def __init__(self, api_keys: str | list[str], max_retries: int = 2, base_url: str | None = None):
        super().__init__(api_keys=api_keys, max_retries=max_retries)
        self.base_url = base_url
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
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
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        response = self.client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            temperature=temperature,
            response_format=response_model,
        )

        parsed_obj = response.choices[0].message.parsed
        # Return the dictionary because BaseLLMProvider validates it
        raw_dict = parsed_obj.model_dump()

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        pricing = OPENAI_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (input_tokens / 1_000_000 * pricing["input"]) + \
               (output_tokens / 1_000_000 * pricing["output"])

        return GenerationResult(
            data=raw_dict,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

    def _raw_generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> GenerationResult:
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        content = response.choices[0].message.content

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        pricing = OPENAI_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (input_tokens / 1_000_000 * pricing["input"]) + \
               (output_tokens / 1_000_000 * pricing["output"])

        return GenerationResult(
            data=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )

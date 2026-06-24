"""
Groq LLM Provider

Concrete implementation using the groq SDK.
Uses Llama 3 models with JSON mode.
"""

from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel

from src.providers.base import BaseLLMProvider, GenerationResult

T = TypeVar("T", bound=BaseModel)

GROQ_PRICING = {
    "llama3-70b-8192": {"input": 0.59, "output": 0.79},
    "llama3-8b-8192": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
}


class GroqProvider(BaseLLMProvider):
    """
    Groq provider using groq SDK.
    """

    def __init__(self, api_keys: str | list[str], max_retries: int = 2):
        super().__init__(api_keys=api_keys, max_retries=max_retries)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
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
        schema = response_model.model_json_schema()
        
        # Inject the expected JSON schema into the system prompt for Llama 3
        system_msg = f"{system_instruction}\n\nYou must respond in JSON format matching this schema:\n{json.dumps(schema, indent=2)}\nDO NOT wrap the JSON in markdown code blocks. Output RAW JSON ONLY."

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        # Dynamically calculate max_tokens to avoid Groq's 12000 TPM free tier limit
        # The limit is applied to (prompt_tokens + max_tokens).
        approx_prompt_tokens = len(system_msg + prompt) // 3
        calculated_max_tokens = min(8192, max(1500, 11500 - approx_prompt_tokens))

        # Call Groq API
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=calculated_max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        
        # In case the model output markdown blocks despite instructions
        if "```json" in content:
            content = content.split("```json")[1]
            if "```" in content:
                content = content.split("```")[0]
        elif "```" in content:
            content = content.split("```")[0]
            
        content = content.strip()
        
        try:
            raw_dict = json.loads(content)
        except Exception as e:
            print(f"Failed to parse JSON: {content}")
            raise e

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # Calculate cost
        pricing = GROQ_PRICING.get(model, {"input": 0.0, "output": 0.0})
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

        pricing = GROQ_PRICING.get(model, {"input": 0.0, "output": 0.0})
        cost = (input_tokens / 1_000_000 * pricing["input"]) + \
               (output_tokens / 1_000_000 * pricing["output"])

        return {
            "text": content,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

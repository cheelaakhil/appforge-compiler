"""
Abstract LLM Provider Interface

Defines the contract that all LLM providers must implement.
Handles structured output generation, retries, and telemetry.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TypeVar, Type

from pydantic import BaseModel

from src.models.manifest import StageTelemetry

T = TypeVar("T", bound=BaseModel)


class LLMProviderError(Exception):
    """Raised when the LLM provider fails to generate output."""

    def __init__(self, message: str, retries_exhausted: bool = False):
        super().__init__(message)
        self.retries_exhausted = retries_exhausted


class GenerationResult(BaseModel):
    """Result of a structured generation call."""
    data: dict  # The raw parsed JSON before Pydantic validation
    input_tokens: int = 0
    output_tokens: int = 0
    model_used: str = ""
    duration_seconds: float = 0.0
    estimated_cost_usd: float = 0.0


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    Subclasses must implement `_raw_generate` which handles the actual
    API call. This base class handles retries, timing, and Pydantic validation.
    """

    def __init__(self, api_keys: str | list[str], max_retries: int = 2):
        if isinstance(api_keys, str):
            self.api_keys = [api_keys]
        else:
            self.api_keys = api_keys
        self.max_retries = max_retries
        self._current_key_index = 0

    @property
    def api_key(self) -> str:
        """Get the currently active API key."""
        return self.api_keys[self._current_key_index]

    def rotate_key(self) -> bool:
        """Rotate to the next API key. Returns True if a new key is available, False if exhausted."""
        if len(self.api_keys) <= 1:
            return False
            
        self._current_key_index = (self._current_key_index + 1) % len(self.api_keys)
        self._reset_client()
        print(f"🔄 Rotating to API Key #{self._current_key_index + 1}/{len(self.api_keys)}")
        return True

    def _reset_client(self):
        """Override in subclasses to clear cached client instances when the key rotates."""
        pass

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        model: str,
        system_instruction: str = "",
        temperature: float = 0.1,
    ) -> tuple[T, StageTelemetry]:
        """
        Generate a structured output conforming to a Pydantic model.

        Args:
            prompt: The user prompt / input context.
            response_model: The Pydantic model class to validate against.
            model: The model identifier to use.
            system_instruction: Optional system-level instruction.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            A tuple of (validated Pydantic instance, telemetry data).

        Raises:
            LLMProviderError: If generation fails after all retries.
        """
        last_error = None
        total_input_tokens = 0
        total_output_tokens = 0
        start_time = time.time()
        
        retries_left = self.max_retries
        keys_tried = 1

        while retries_left > 0:
            try:
                result = self._raw_generate(
                    prompt=prompt,
                    response_model=response_model,
                    model=model,
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                total_input_tokens += result.input_tokens
                total_output_tokens += result.output_tokens

                # Validate with Pydantic
                validated = response_model.model_validate(result.data)

                elapsed = time.time() - start_time
                telemetry = StageTelemetry(
                    stage_name="",  # Filled by caller
                    duration_seconds=elapsed,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    model_used=model,
                    retries=(self.max_retries - retries_left),
                    estimated_cost_usd=self._estimate_cost(
                        model, total_input_tokens, total_output_tokens
                    ),
                )
                return validated, telemetry

            except Exception as e:
                last_error = e
                total_input_tokens += getattr(e, "input_tokens", 0)
                total_output_tokens += getattr(e, "output_tokens", 0)
                
                # Check for rate limit / 429 / 403 errors and attempt key rotation
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                    if keys_tried < len(self.api_keys):
                        if self.rotate_key():
                            keys_tried += 1
                            # If we successfully rotated, don't consume a retry budget!
                            continue
                    print("⚠️ Rate limit hit, backing off for 2 seconds...")
                    time.sleep(2)
                        
                retries_left -= 1
                if retries_left == 0:
                    break

        raise LLMProviderError(
            f"Generation failed after {self.max_retries} attempts: {last_error}",
            retries_exhausted=True,
        )

    def generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: str = "",
        temperature: float = 0.1,
    ) -> tuple[str, StageTelemetry]:
        """
        Generate a plain-text response (for repair prompts).

        Returns:
            A tuple of (text response, telemetry data).
        """
        start_time = time.time()
        last_error = None
        retries_left = self.max_retries
        keys_tried = 1
        
        while retries_left > 0:
            try:
                result = self._raw_generate_text(
                    prompt=prompt,
                    model=model,
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                elapsed = time.time() - start_time
                telemetry = StageTelemetry(
                    stage_name="",
                    duration_seconds=elapsed,
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    model_used=model,
                )
                return result["text"], telemetry
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if "429" in err_str or "rate limit" in err_str or "quota" in err_str:
                    if keys_tried < len(self.api_keys):
                        if self.rotate_key():
                            keys_tried += 1
                            continue
                    print("⚠️ Rate limit hit, backing off for 2 seconds...")
                    time.sleep(2)
                
                retries_left -= 1
                if retries_left == 0:
                    break
                    
        raise LLMProviderError(
            f"Generation failed after {self.max_retries} attempts: {last_error}",
            retries_exhausted=True,
        )

    @abstractmethod
    def _raw_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> GenerationResult:
        """Execute the actual structured generation API call."""
        ...

    @abstractmethod
    def _raw_generate_text(
        self,
        prompt: str,
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> dict:
        """Execute a plain-text generation API call. Returns dict with 'text', 'input_tokens', 'output_tokens'."""
        ...

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate API cost in USD. Override for provider-specific pricing."""
        # Default rough estimate (varies by provider)
        input_cost_per_1k = 0.0001
        output_cost_per_1k = 0.0003
        return (input_tokens / 1000 * input_cost_per_1k) + (output_tokens / 1000 * output_cost_per_1k)

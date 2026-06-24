"""
NVIDIA LLM Provider

Concrete implementation using the nvidia NIM API via requests.
"""

from __future__ import annotations

import json
from typing import Type, TypeVar
import requests

from pydantic import BaseModel

from src.providers.base import BaseLLMProvider, GenerationResult

T = TypeVar("T", bound=BaseModel)


class NvidiaProvider(BaseLLMProvider):
    """
    NVIDIA NIM provider.
    """

    def __init__(self, api_keys: str | list[str], max_retries: int = 2):
        super().__init__(api_keys=api_keys, max_retries=max_retries)
        self.base_url = "https://integrate.api.nvidia.com/v1/chat/completions"

    def _raw_generate(
        self,
        prompt: str,
        response_model: Type[T],
        model: str,
        system_instruction: str,
        temperature: float,
    ) -> GenerationResult:
        schema = response_model.model_json_schema()
        
        system_msg = f"{system_instruction}\n\nYou must respond in JSON format matching this schema:\n{json.dumps(schema, indent=2)}\nDO NOT wrap the JSON in markdown code blocks. Output RAW JSON ONLY."

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": temperature,
            "stream": False,
        }

        response = requests.post(self.base_url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        
        resp_json = response.json()
        raw_text = resp_json["choices"][0]["message"]["content"].strip()
        
        import re
        # Try to find a JSON block in markdown
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
        if match:
            raw_text = match.group(1)
        else:
            # Fallback: try to find first { or [ and matching closing bracket (simple heuristic, not perfect for nested structures but better than rfind)
            start_obj = raw_text.find('{')
            start_arr = raw_text.find('[')
            start_idx = -1
            if start_obj != -1 and start_arr != -1:
                start_idx = min(start_obj, start_arr)
            elif start_obj != -1:
                start_idx = start_obj
            elif start_arr != -1:
                start_idx = start_arr
                
            if start_idx != -1:
                # Find matching closing bracket
                open_char = raw_text[start_idx]
                close_char = '}' if open_char == '{' else ']'
                depth = 0
                end_idx = -1
                for i in range(start_idx, len(raw_text)):
                    if raw_text[i] == open_char:
                        depth += 1
                    elif raw_text[i] == close_char:
                        depth -= 1
                        if depth == 0:
                            end_idx = i
                            break
                if end_idx != -1:
                    raw_text = raw_text[start_idx:end_idx+1]

        parsed_data = json.loads(raw_text.strip())

        usage = resp_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

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
        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": temperature,
            "stream": False,
        }

        response = requests.post(self.base_url, headers=headers, json=payload)
        response.raise_for_status()
        
        resp_json = response.json()
        raw_text = resp_json["choices"][0]["message"]["content"]

        usage = resp_json.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return {
            "text": raw_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        return 0.0

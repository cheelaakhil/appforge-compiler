"""
Global Configuration

Loads environment variables and provides pipeline-wide settings.
Supports multiple LLM providers with auto-detection.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv(override=True)


@dataclass
class ModelConfig:
    """LLM model selection for different pipeline stages."""
    fast_model: str = os.getenv("FAST_MODEL", "moonshotai/kimi-k2.6")
    analytical_model: str = os.getenv("ANALYTICAL_MODEL", "moonshotai/kimi-k2.6")


@dataclass
class PipelineConfig:
    """Pipeline behavior settings."""
    max_repair_cycles: int = int(os.getenv("MAX_REPAIR_CYCLES", "3"))
    timeout_seconds: int = int(os.getenv("PIPELINE_TIMEOUT_SECONDS", "120"))
    output_dir: str = os.getenv("OUTPUT_DIR", "output")


@dataclass
class ProviderConfig:
    """LLM provider configuration with auto-detection."""
    provider: str = ""
    api_keys: list[str] = field(default_factory=list)

    def __post_init__(self):
        """Auto-detect provider from environment variables."""
        explicit_provider = os.getenv("LLM_PROVIDER", "").lower()

        # Provider → env var mapping
        provider_keys = {
            "nvidia": "NVIDIA_API_KEYS",
            "gemini": "GEMINI_API_KEYS",
            "openai": "OPENAI_API_KEYS",
            "groq": "GROQ_API_KEYS",
        }

        # Fallback to singular for backward compatibility
        provider_keys_singular = {
            "nvidia": "NVIDIA_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY",
        }

        if explicit_provider and explicit_provider in provider_keys:
            self.provider = explicit_provider
            keys_str = os.getenv(provider_keys[explicit_provider]) or os.getenv(provider_keys_singular[explicit_provider], "")
            self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        else:
            # Auto-detect: check which API key is set
            for prov, env_key in provider_keys.items():
                keys_str = os.getenv(env_key) or os.getenv(provider_keys_singular[prov], "")
                if keys_str:
                    self.provider = prov
                    self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
                    break

        if not self.provider:
            self.provider = "nvidia"

    def validate(self) -> None:
        """Raise if the configuration is incomplete."""
        if not self.api_keys:
            raise ValueError(
                f"API keys not found for provider '{self.provider}'. "
                f"Set the appropriate environment variable in .env "
                f"(e.g., GROQ_API_KEYS)."
            )


@dataclass
class ServerConfig:
    """Web server configuration."""
    port: int = int(os.getenv("PORT", "8000"))
    host: str = os.getenv("HOST", "0.0.0.0")


@dataclass
class AppConfig:
    """Top-level application configuration."""
    models: ModelConfig = field(default_factory=ModelConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    server: ServerConfig = field(default_factory=ServerConfig)

    def validate(self) -> None:
        """Validate all configuration."""
        self.provider.validate()


# Singleton instance
config = AppConfig()

"""
Pipeline Orchestrator

The main controller that runs all pipeline stages sequentially,
tracks telemetry, and produces the final AppManifest.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from src.config import AppConfig
from src.models.intent import IntentManifest
from src.models.design import SystemDesignIR
from src.models.schema import DBSchema, APISchema, UISchema
from src.models.manifest import (
    AppManifest,
    ManifestMetadata,
    PipelineTelemetry,
    StageTelemetry,
    RuntimeTestResult,
    RuntimeTestStatus,
    ValidationReport,
)
from src.providers.base import BaseLLMProvider
from src.providers.gemini import GeminiProvider
from src.pipeline.stage_1_intent import extract_intent
from src.pipeline.stage_2_design import generate_system_design
from src.pipeline.stage_3_schema import (
    generate_db_schema,
    generate_api_schema,
    generate_ui_schema,
)
from src.pipeline.stage_4_validate import validate_and_repair
from src.runtime.simulator import run_simulation


class PipelineOrchestrator:
    """
    Orchestrates the full compiler pipeline:
      1. Intent Extraction (Fast Model)
      2. System Design IR (Analytical Model)
      3. Schema Generation — DB → API → UI (Analytical Model)
      4. Validation & Repair (Programmatic + Analytical Model)
      5. Runtime Simulation (SQLite + FastAPI)
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.provider = self._create_provider()
        self.stage_telemetry: list[StageTelemetry] = []

    def _create_provider(self) -> BaseLLMProvider:
        """Create the LLM provider based on configuration."""
        self.config.provider.validate()
        if self.config.provider.provider == "groq":
            from src.providers.groq_provider import GroqProvider
            return GroqProvider(
                api_keys=self.config.provider.api_keys,
                max_retries=2,
            )
        elif self.config.provider.provider == "openai":
            from src.providers.openai_provider import OpenAIProvider
            return OpenAIProvider(
                api_keys=self.config.provider.api_keys,
                max_retries=2,
            )
        elif self.config.provider.provider == "nvidia":
            from src.providers.nvidia_provider import NvidiaProvider
            return NvidiaProvider(
                api_keys=self.config.provider.api_keys,
                max_retries=2,
            )
        else:
            from src.providers.gemini import GeminiProvider
            return GeminiProvider(
                api_keys=self.config.provider.api_keys,
                max_retries=2,
            )

    def run(
        self,
        user_input: str,
        on_stage_start=None,
        on_stage_complete=None,
    ) -> AppManifest:
        """
        Run the full pipeline on a user input string.

        Args:
            user_input: Natural language application description.
            on_stage_start: Optional callback(stage_name: str) called when a stage starts.
            on_stage_complete: Optional callback(stage_name: str, telemetry: StageTelemetry)
                              called when a stage completes.

        Returns:
            The final AppManifest with all stages' output.
        """
        pipeline_start = time.time()
        self.stage_telemetry = []

        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        def _save_ckpt(model, suffix: str, app_name: str):
            path = output_dir / f"{app_name}_{suffix}.json"
            with open(path, "w", encoding="utf-8") as f:
                f.write(model.model_dump_json(indent=2))

        # --- Stage 1: Intent Extraction ---
        self._notify(on_stage_start, "intent_extraction")
        intent, intent_telemetry = extract_intent(
            user_input=user_input,
            provider=self.provider,
            model=self.config.models.fast_model,
        )
        self.stage_telemetry.append(intent_telemetry)
        _save_ckpt(intent, "intent", intent.app_name)
        self._notify(on_stage_complete, "intent_extraction", intent_telemetry)

        # --- Stage 2: System Design ---
        self._notify(on_stage_start, "system_design")
        design, design_telemetry = generate_system_design(
            intent=intent,
            provider=self.provider,
            model=self.config.models.analytical_model,
        )
        self.stage_telemetry.append(design_telemetry)
        _save_ckpt(design, "design", intent.app_name)
        self._notify(on_stage_complete, "system_design", design_telemetry)

        # --- Stage 3: Schema Generation (DB → API → UI) ---
        self._notify(on_stage_start, "schema_generation_db")
        db_schema, db_telemetry = generate_db_schema(
            design=design,
            provider=self.provider,
            model=self.config.models.analytical_model,
        )
        self.stage_telemetry.append(db_telemetry)
        _save_ckpt(db_schema, "db_schema", intent.app_name)
        self._notify(on_stage_complete, "schema_generation_db", db_telemetry)

        self._notify(on_stage_start, "schema_generation_api")
        api_schema, api_telemetry = generate_api_schema(
            design=design,
            db_schema=db_schema,
            provider=self.provider,
            model=self.config.models.analytical_model,
        )
        self.stage_telemetry.append(api_telemetry)
        _save_ckpt(api_schema, "api_schema", intent.app_name)
        self._notify(on_stage_complete, "schema_generation_api", api_telemetry)

        self._notify(on_stage_start, "schema_generation_ui")
        ui_schema, ui_telemetry = generate_ui_schema(
            design=design,
            db_schema=db_schema,
            api_schema=api_schema,
            provider=self.provider,
            model=self.config.models.analytical_model,
        )
        self.stage_telemetry.append(ui_telemetry)
        _save_ckpt(ui_schema, "ui_schema", intent.app_name)
        self._notify(on_stage_complete, "schema_generation_ui", ui_telemetry)

        # --- Stage 4: Validation & Repair ---
        self._notify(on_stage_start, "validation_repair")
        db_schema, api_schema, ui_schema, validation_report, val_telemetry = (
            validate_and_repair(
                design=design,
                db_schema=db_schema,
                api_schema=api_schema,
                ui_schema=ui_schema,
                provider=self.provider,
                model=self.config.models.analytical_model,
                max_repair_cycles=self.config.pipeline.max_repair_cycles,
            )
        )
        self.stage_telemetry.append(val_telemetry)
        self._notify(on_stage_complete, "validation_repair", val_telemetry)

        # --- Stage 5: Runtime Simulation ---
        self._notify(on_stage_start, "runtime_simulation")
        runtime_result, sim_telemetry = run_simulation(
            db_schema=db_schema,
            api_schema=api_schema,
        )
        self.stage_telemetry.append(sim_telemetry)
        self._notify(on_stage_complete, "runtime_simulation", sim_telemetry)

        # --- Assemble Final Manifest ---
        pipeline_duration = time.time() - pipeline_start

        telemetry = PipelineTelemetry(
            stages=self.stage_telemetry,
            total_duration_seconds=pipeline_duration,
            total_input_tokens=sum(s.input_tokens for s in self.stage_telemetry),
            total_output_tokens=sum(s.output_tokens for s in self.stage_telemetry),
            total_estimated_cost_usd=sum(s.estimated_cost_usd for s in self.stage_telemetry),
        )

        manifest = AppManifest(
            metadata=ManifestMetadata(
                source_prompt_hash=ManifestMetadata.hash_prompt(user_input),
            ),
            intent=intent,
            design=design,
            db_schema=db_schema,
            api_schema=api_schema,
            ui_schema=ui_schema,
            validation_report=validation_report,
            runtime_test_result=runtime_result,
            telemetry=telemetry,
        )

        return manifest

    def save_manifest(self, manifest: AppManifest, output_path: str) -> Path:
        """Save the manifest to a JSON file."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))

        return path

    @staticmethod
    def _notify(callback, *args):
        """Safely call an optional callback."""
        if callback:
            callback(*args)

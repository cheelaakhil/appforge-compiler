"""
Targeted Repair Engine

When validation finds errors, this engine extracts ONLY the erroneous
schema slice, constructs a minimal repair prompt, and applies the fix
without regenerating the entire manifest.
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel

from src.models.schema import DBSchema, APISchema, UISchema
from src.models.manifest import (
    ValidationError,
    ValidationErrorCategory,
    RepairAction,
)
from src.providers.base import BaseLLMProvider


REPAIR_SYSTEM_INSTRUCTION = """You are a precision repair engine for a JSON schema pipeline.
You receive a specific JSON slice that has a validation error, along with the exact error
description and a fix instruction.

RULES:
- Output ONLY the corrected JSON slice — nothing else.
- Do NOT add explanations, markdown formatting, or commentary.
- Make the MINIMAL change required to fix the error.
- Preserve all other fields exactly as they are.
- Output must be valid JSON.
"""


class RepairEngine:
    """
    Targeted repair engine that fixes specific schema errors
    without regenerating the entire manifest.
    """

    def __init__(self, provider: BaseLLMProvider, model: str):
        self.provider = provider
        self.model = model

    def repair(
        self,
        db_schema: DBSchema,
        api_schema: APISchema,
        ui_schema: UISchema,
        errors: list[ValidationError],
        cycle: int,
    ) -> tuple[DBSchema, APISchema, UISchema, list[RepairAction]]:
        """
        Attempt to repair all given errors.

        Groups errors by affected schema layer and applies targeted fixes.

        Returns:
            Updated schemas and a list of repair actions taken.
        """
        repair_actions: list[RepairAction] = []

        # Group errors by schema layer
        db_errors = [e for e in errors if e.location.startswith("db_schema")]
        api_errors = [e for e in errors if e.location.startswith("api_schema")]
        ui_errors = [e for e in errors if e.location.startswith("ui_schema")]

        # Repair DB schema errors
        if db_errors:
            db_schema, db_repairs = self._repair_schema_layer(
                schema=db_schema,
                schema_name="db_schema",
                model_class=DBSchema,
                errors=db_errors,
                cycle=cycle,
            )
            repair_actions.extend(db_repairs)

        # Repair API schema errors
        if api_errors:
            api_schema, api_repairs = self._repair_schema_layer(
                schema=api_schema,
                schema_name="api_schema",
                model_class=APISchema,
                errors=api_errors,
                cycle=cycle,
            )
            repair_actions.extend(api_repairs)

        # Repair UI schema errors
        if ui_errors:
            ui_schema, ui_repairs = self._repair_schema_layer(
                schema=ui_schema,
                schema_name="ui_schema",
                model_class=UISchema,
                errors=ui_errors,
                cycle=cycle,
            )
            repair_actions.extend(ui_repairs)

        return db_schema, api_schema, ui_schema, repair_actions

    def _repair_schema_layer(
        self,
        schema: BaseModel,
        schema_name: str,
        model_class: type[BaseModel],
        errors: list[ValidationError],
        cycle: int,
    ) -> tuple[BaseModel, list[RepairAction]]:
        """Repair errors in a single schema layer."""
        repair_actions: list[RepairAction] = []
        schema_json = schema.model_dump_json(indent=2)

        # Build a combined repair prompt for all errors in this layer
        error_descriptions = []
        for err in errors:
            desc = f"- Location: {err.location}\n  Error: {err.message}"
            if err.expected:
                desc += f"\n  Expected: {err.expected}"
            if err.actual:
                desc += f"\n  Actual: {err.actual}"
            if err.suggestion:
                desc += f"\n  Fix: {err.suggestion}"
            error_descriptions.append(desc)

        errors_text = "\n\n".join(error_descriptions)

        prompt = f"""Fix the following validation errors in this {schema_name} JSON.

--- ERRORS ---
{errors_text}
--- END ERRORS ---

--- CURRENT {schema_name.upper()} JSON ---
{schema_json}
--- END JSON ---

Output the COMPLETE corrected {schema_name} JSON with all errors fixed.
Make MINIMAL changes — only fix what's broken.
"""

        try:
            repaired, _telemetry = self.provider.generate_structured(
                prompt=prompt,
                response_model=model_class,
                model=self.model,
                system_instruction=REPAIR_SYSTEM_INSTRUCTION,
                temperature=0.05,
            )

            for err in errors:
                repair_actions.append(RepairAction(
                    error=err,
                    repair_prompt=prompt[:500] + "...",  # Truncated for storage
                    schema_slice=schema_name,
                    cycle=cycle,
                    success=True,
                ))

            return repaired, repair_actions

        except Exception as e:
            # If repair fails, return original schema with failed actions
            for err in errors:
                repair_actions.append(RepairAction(
                    error=err,
                    repair_prompt=prompt[:500] + "...",
                    schema_slice=schema_name,
                    cycle=cycle,
                    success=False,
                ))

            return schema, repair_actions

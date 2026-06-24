"""
Stage 4: Validation Orchestration

Runs all programmatic validation checks and triggers the repair engine
when errors are found. This is the "type-checker" of the pipeline.
"""

from __future__ import annotations

from src.models.design import SystemDesignIR
from src.models.schema import DBSchema, APISchema, UISchema
from src.models.manifest import (
    ValidationReport,
    ValidationError,
    ValidationSeverity,
    ValidationErrorCategory,
    StageTelemetry,
)
from src.validation.structural import run_structural_checks
from src.validation.referential import run_referential_checks
from src.providers.base import BaseLLMProvider
from src.validation.repair import RepairEngine

import time


def validate_and_repair(
    design: SystemDesignIR,
    db_schema: DBSchema,
    api_schema: APISchema,
    ui_schema: UISchema,
    provider: BaseLLMProvider,
    model: str,
    max_repair_cycles: int = 3,
) -> tuple[DBSchema, APISchema, UISchema, ValidationReport, StageTelemetry]:
    """
    Run validation checks and attempt repairs on any errors found.

    Args:
        design: The System Design IR for reference.
        db_schema: The generated database schema.
        api_schema: The generated API schema.
        ui_schema: The generated UI schema.
        provider: LLM provider for repair calls.
        model: Model to use for repairs.
        max_repair_cycles: Maximum number of repair iterations.

    Returns:
        Tuple of (possibly-repaired DB schema, API schema, UI schema,
                  validation report, telemetry).
    """
    start_time = time.time()
    total_checks = 0
    checks_passed = 0
    all_errors: list[ValidationError] = []
    all_warnings: list[ValidationError] = []
    repair_actions = []

    repair_engine = RepairEngine(provider=provider, model=model)

    for cycle in range(1, max_repair_cycles + 1):
        # Run all checks
        structural_errors = run_structural_checks(db_schema, api_schema, ui_schema)
        referential_errors = run_referential_checks(design, db_schema, api_schema, ui_schema)

        current_errors = structural_errors + referential_errors

        # Separate errors from warnings
        errors = [e for e in current_errors if e.severity == ValidationSeverity.ERROR]
        warnings = [e for e in current_errors if e.severity != ValidationSeverity.ERROR]

        # Count checks (estimate: each check type covers multiple rules)
        structural_check_count = _count_structural_checks(db_schema, api_schema, ui_schema)
        referential_check_count = _count_referential_checks(db_schema, api_schema, ui_schema)
        total_checks = structural_check_count + referential_check_count
        checks_passed = total_checks - len(errors) - len(warnings)

        all_warnings = warnings

        if not errors:
            # All clear — no critical errors
            all_errors = []
            break

        if cycle == max_repair_cycles:
            # Final cycle — report remaining errors
            all_errors = errors
            break

        # Attempt targeted repairs
        db_schema, api_schema, ui_schema, cycle_repairs = repair_engine.repair(
            db_schema=db_schema,
            api_schema=api_schema,
            ui_schema=ui_schema,
            errors=errors,
            cycle=cycle,
        )
        repair_actions.extend(cycle_repairs)

    elapsed = time.time() - start_time

    report = ValidationReport(
        passed=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
        repair_actions=repair_actions,
        total_checks_run=total_checks,
        checks_passed=checks_passed,
        repair_cycles_used=min(cycle, max_repair_cycles) if current_errors else 0,
    )

    telemetry = StageTelemetry(
        stage_name="validation_repair",
        duration_seconds=elapsed,
        retries=len(repair_actions),
    )

    return db_schema, api_schema, ui_schema, report, telemetry


def _count_structural_checks(db: DBSchema, api: APISchema, ui: UISchema) -> int:
    """Estimate the number of structural checks run."""
    count = 0
    count += len(db.tables) * 3  # table has PK, has created_at, has updated_at
    count += sum(len(t.columns) for t in db.tables)  # column type validity
    count += len(api.endpoints) * 2  # method validity, path format
    count += sum(len(p.components) for p in ui.pages)  # component has id
    return max(count, 1)


def _count_referential_checks(db: DBSchema, api: APISchema, ui: UISchema) -> int:
    """Estimate the number of referential integrity checks run."""
    count = 0
    count += len(api.endpoints)  # target_table exists
    count += sum(len(t.foreign_keys) for t in db.tables)  # FK references valid table
    count += len(ui.all_bound_endpoints)  # UI endpoints exist in API
    return max(count, 1)

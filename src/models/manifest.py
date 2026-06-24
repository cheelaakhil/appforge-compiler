"""
Final Manifest + Validation/Runtime Result Models

The AppManifest is the composite output of the entire pipeline,
containing all stage outputs plus validation and runtime test results.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, computed_field

from src.models.intent import IntentManifest
from src.models.design import SystemDesignIR
from src.models.schema import DBSchema, APISchema, UISchema


# ===========================================================================
# Validation Report
# ===========================================================================

class ValidationSeverity(str, Enum):
    """Severity level of a validation error."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationErrorCategory(str, Enum):
    """Categories of validation errors."""
    STRUCTURAL = "structural"
    REFERENCE_INTEGRITY = "reference_integrity"
    NAMING_MISMATCH = "naming_mismatch"
    MISSING_FIELD = "missing_field"
    TYPE_MISMATCH = "type_mismatch"
    RELATIONSHIP_INTEGRITY = "relationship_integrity"
    ENDPOINT_CONFLICT = "endpoint_conflict"
    ORPHANED_COMPONENT = "orphaned_component"


class ValidationError(BaseModel):
    """A single validation error with location and context."""
    category: ValidationErrorCategory = Field(description="Error category")
    severity: ValidationSeverity = Field(description="Error severity")
    message: str = Field(description="Human-readable error description")
    location: str = Field(
        description="Dot-path to the error location, e.g. 'db_schema.tables[0].columns[2]'"
    )
    expected: Optional[str] = Field(default=None, description="What was expected")
    actual: Optional[str] = Field(default=None, description="What was found")
    suggestion: str = Field(default="", description="Suggested fix")


class RepairAction(BaseModel):
    """Record of a repair action taken by the repair engine."""
    error: ValidationError = Field(description="The error that was repaired")
    repair_prompt: str = Field(description="The targeted repair instruction sent to LLM")
    schema_slice: str = Field(description="The JSON slice that was repaired")
    cycle: int = Field(description="Repair cycle number (1-indexed)")
    success: bool = Field(description="Whether the repair resolved the error")


class ValidationReport(BaseModel):
    """Complete validation report for the generated schemas."""
    passed: bool = Field(default=True, description="Whether all critical checks passed")
    errors: list[ValidationError] = Field(
        default_factory=list,
        description="All validation errors found"
    )
    warnings: list[ValidationError] = Field(
        default_factory=list,
        description="All validation warnings found"
    )
    repair_actions: list[RepairAction] = Field(
        default_factory=list,
        description="Record of repair actions taken"
    )
    total_checks_run: int = Field(default=0, description="Number of validation checks executed")
    checks_passed: int = Field(default=0, description="Number of checks that passed")
    repair_cycles_used: int = Field(default=0, description="Number of repair cycles consumed")

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def pass_rate(self) -> float:
        if self.total_checks_run == 0:
            return 0.0
        return self.checks_passed / self.total_checks_run


# ===========================================================================
# Runtime Test Result
# ===========================================================================

class RuntimeTestStatus(str, Enum):
    """Status of a runtime simulation test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class RuntimeTestDetail(BaseModel):
    """A single runtime test result."""
    test_name: str = Field(description="Test identifier")
    status: RuntimeTestStatus = Field(description="Pass/fail/skip status")
    duration_ms: float = Field(default=0.0, description="Test duration in milliseconds")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    traceback: Optional[str] = Field(default=None, description="Full traceback if failed")
    affected_schema_location: Optional[str] = Field(
        default=None,
        description="Schema location that caused the failure"
    )


class RuntimeTestResult(BaseModel):
    """Results of the simulated runtime verification."""
    overall_status: RuntimeTestStatus = Field(description="Overall pass/fail")
    db_boot_status: RuntimeTestStatus = Field(description="SQLite table creation status")
    api_boot_status: RuntimeTestStatus = Field(description="FastAPI stub boot status")
    details: list[RuntimeTestDetail] = Field(
        default_factory=list,
        description="Individual test results"
    )
    total_tests: int = Field(default=0)
    tests_passed: int = Field(default=0)


# ===========================================================================
# Pipeline Telemetry
# ===========================================================================

class StageTelemetry(BaseModel):
    """Performance metrics for a single pipeline stage."""
    stage_name: str = Field(description="Stage identifier")
    duration_seconds: float = Field(description="Wall-clock time in seconds")
    input_tokens: int = Field(default=0, description="LLM input tokens consumed")
    output_tokens: int = Field(default=0, description="LLM output tokens generated")
    model_used: str = Field(default="", description="LLM model identifier")
    retries: int = Field(default=0, description="Number of retries")
    estimated_cost_usd: float = Field(default=0.0, description="Estimated API cost")


class PipelineTelemetry(BaseModel):
    """Aggregate telemetry for the full pipeline run."""
    stages: list[StageTelemetry] = Field(default_factory=list)
    total_duration_seconds: float = Field(default=0.0)
    total_input_tokens: int = Field(default=0)
    total_output_tokens: int = Field(default=0)
    total_estimated_cost_usd: float = Field(default=0.0)


# ===========================================================================
# Manifest Metadata
# ===========================================================================

class ManifestMetadata(BaseModel):
    """Metadata about the generated manifest."""
    version: str = Field(default="1.0.0", description="Manifest schema version")
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 generation timestamp"
    )
    pipeline_version: str = Field(default="0.1.0", description="Pipeline software version")
    source_prompt_hash: str = Field(
        default="",
        description="SHA-256 hash of the original user prompt for traceability"
    )

    @staticmethod
    def hash_prompt(prompt: str) -> str:
        """Generate a SHA-256 hash of the user prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


# ===========================================================================
# THE FINAL MANIFEST
# ===========================================================================

class AppManifest(BaseModel):
    """
    The complete output of the multi-stage compiler pipeline.

    Contains every stage's output plus validation results, runtime test
    results, and telemetry data for the full pipeline run.
    """
    metadata: ManifestMetadata = Field(
        default_factory=ManifestMetadata,
        description="Generation metadata and traceability"
    )
    intent: IntentManifest = Field(
        description="Stage 1 output: structured intent extraction"
    )
    design: SystemDesignIR = Field(
        description="Stage 2 output: system design intermediate representation"
    )
    db_schema: DBSchema = Field(
        description="Stage 3 output: database schema"
    )
    api_schema: APISchema = Field(
        description="Stage 3 output: API schema"
    )
    ui_schema: UISchema = Field(
        description="Stage 3 output: UI schema"
    )
    validation_report: ValidationReport = Field(
        default_factory=ValidationReport,
        description="Stage 4 output: validation results and repair log"
    )
    runtime_test_result: RuntimeTestResult = Field(
        default_factory=lambda: RuntimeTestResult(
            overall_status="skipped",
            db_boot_status="skipped",
            api_boot_status="skipped",
        ),
        description="Runtime simulation results"
    )
    telemetry: PipelineTelemetry = Field(
        default_factory=PipelineTelemetry,
        description="Pipeline performance telemetry"
    )

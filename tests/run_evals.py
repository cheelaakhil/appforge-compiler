"""
Evaluation Harness

Iterates over test datasets, runs the full pipeline on each prompt,
and generates a comprehensive markdown report tracking:
  - First-Pass Success Rate
  - Recovery Rate
  - Stage Latency (p50, p95)
  - Token Usage
  - Total Cost
  - Structural Completeness
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from src.config import AppConfig, config as app_config
from src.models.manifest import AppManifest
from src.pipeline.orchestrator import PipelineOrchestrator


@dataclass
class EvalResult:
    """Result of a single evaluation run."""
    prompt_id: str
    prompt_name: str
    prompt_text: str
    success: bool = False
    first_pass_success: bool = False
    validation_passed: bool = False
    runtime_passed: bool = False
    repair_attempted: bool = False
    repair_succeeded: bool = False
    total_duration: float = 0.0
    stage_durations: dict[str, float] = field(default_factory=dict)
    total_tokens: int = 0
    total_cost: float = 0.0
    tables_generated: int = 0
    endpoints_generated: int = 0
    pages_generated: int = 0
    error_message: str = ""
    manifest: Optional[AppManifest] = None


@dataclass
class EvalSummary:
    """Aggregate evaluation metrics."""
    total_prompts: int = 0
    successes: int = 0
    first_pass_successes: int = 0
    repairs_attempted: int = 0
    repairs_succeeded: int = 0
    durations: list[float] = field(default_factory=list)
    stage_durations: dict[str, list[float]] = field(default_factory=dict)
    total_tokens: list[int] = field(default_factory=list)
    total_costs: list[float] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return (self.successes / self.total_prompts * 100) if self.total_prompts else 0

    @property
    def first_pass_rate(self) -> float:
        return (self.first_pass_successes / self.total_prompts * 100) if self.total_prompts else 0

    @property
    def recovery_rate(self) -> float:
        return (self.repairs_succeeded / self.repairs_attempted * 100) if self.repairs_attempted else 0

    def percentile(self, data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * pct / 100
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


def run_evaluation(
    datasets_dir: str = "tests/datasets",
    output_path: str = "output/eval_report.md",
    console: Optional[Console] = None,
):
    """Run the full evaluation suite."""
    if console is None:
        console = Console()

    datasets_path = Path(datasets_dir)
    results: list[EvalResult] = []

    # Load datasets
    standard_file = datasets_path / "standard_products.json"
    edge_file = datasets_path / "edge_cases.json"

    prompts = []
    if standard_file.exists():
        with open(standard_file) as f:
            standard = json.load(f)
            for item in standard:
                prompts.append(("standard", item))

    if edge_file.exists():
        with open(edge_file) as f:
            edge_cases = json.load(f)
            for item in edge_cases:
                prompts.append(("edge_case", item))

    if not prompts:
        console.print("[bold red]No datasets found![/bold red]")
        return

    console.print(f"[bold]Running {len(prompts)} evaluation prompts...[/bold]\n")

    # Initialize pipeline
    try:
        orchestrator = PipelineOrchestrator(app_config)
    except Exception as e:
        console.print(f"[bold red]Failed to initialize pipeline:[/bold red] {e}")
        return

    # Run each prompt
    for i, (category, prompt_data) in enumerate(prompts, 1):
        prompt_id = prompt_data.get("id", f"prompt_{i}")
        prompt_name = prompt_data.get("name", f"Prompt {i}")
        prompt_text = prompt_data.get("prompt", "")

        console.print(
            f"  [{i}/{len(prompts)}] {category.upper()}: {prompt_name}",
            end=""
        )

        result = _run_single_eval(orchestrator, prompt_id, prompt_name, prompt_text)
        results.append(result)

        status = "[green]✓[/green]" if result.success else "[red]✗[/red]"
        console.print(f" — {status} ({result.total_duration:.1f}s)")

    # Generate summary
    summary = _compute_summary(results)

    # Display summary table
    console.print()
    _display_summary_table(summary, console)

    # Write report
    report = _generate_report(results, summary)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write(report)

    console.print(f"\n[bold green]Report saved to:[/bold green] {output_path}\n")


def _run_single_eval(
    orchestrator: PipelineOrchestrator,
    prompt_id: str,
    prompt_name: str,
    prompt_text: str,
) -> EvalResult:
    """Run a single evaluation prompt through the pipeline."""
    result = EvalResult(
        prompt_id=prompt_id,
        prompt_name=prompt_name,
        prompt_text=prompt_text,
    )

    if not prompt_text.strip():
        result.error_message = "Empty prompt — skipped"
        return result

    start = time.time()
    try:
        manifest = orchestrator.run(user_input=prompt_text)
        result.total_duration = time.time() - start
        result.manifest = manifest

        # Extract metrics
        result.validation_passed = manifest.validation_report.passed
        result.runtime_passed = manifest.runtime_test_result.overall_status.value == "passed"
        result.success = result.validation_passed and result.runtime_passed

        # Check if repair was needed
        repair_count = manifest.validation_report.repair_cycles_used
        result.repair_attempted = repair_count > 0
        result.repair_succeeded = result.repair_attempted and result.validation_passed
        result.first_pass_success = result.success and not result.repair_attempted

        # Telemetry
        for stage in manifest.telemetry.stages:
            result.stage_durations[stage.stage_name] = stage.duration_seconds
        result.total_tokens = manifest.telemetry.total_input_tokens + manifest.telemetry.total_output_tokens
        result.total_cost = manifest.telemetry.total_estimated_cost_usd

        # Schema metrics
        result.tables_generated = len(manifest.db_schema.tables)
        result.endpoints_generated = len(manifest.api_schema.endpoints)
        result.pages_generated = len(manifest.ui_schema.pages)

    except Exception as e:
        result.total_duration = time.time() - start
        result.error_message = str(e)

    return result


def _compute_summary(results: list[EvalResult]) -> EvalSummary:
    """Compute aggregate metrics from individual results."""
    summary = EvalSummary(total_prompts=len(results))

    for r in results:
        if r.success:
            summary.successes += 1
        if r.first_pass_success:
            summary.first_pass_successes += 1
        if r.repair_attempted:
            summary.repairs_attempted += 1
        if r.repair_succeeded:
            summary.repairs_succeeded += 1

        if r.total_duration > 0:
            summary.durations.append(r.total_duration)
        if r.total_tokens > 0:
            summary.total_tokens.append(r.total_tokens)
        if r.total_cost > 0:
            summary.total_costs.append(r.total_cost)

        for stage, dur in r.stage_durations.items():
            if stage not in summary.stage_durations:
                summary.stage_durations[stage] = []
            summary.stage_durations[stage].append(dur)

    return summary


def _display_summary_table(summary: EvalSummary, console: Console):
    """Display a rich summary table."""
    table = Table(
        title="Evaluation Summary",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Total Prompts", str(summary.total_prompts))
    table.add_row("Success Rate", f"{summary.success_rate:.1f}%")
    table.add_row("First-Pass Rate", f"{summary.first_pass_rate:.1f}%")
    table.add_row("Recovery Rate", f"{summary.recovery_rate:.1f}%")

    if summary.durations:
        table.add_row("Latency (p50)", f"{summary.percentile(summary.durations, 50):.1f}s")
        table.add_row("Latency (p95)", f"{summary.percentile(summary.durations, 95):.1f}s")

    if summary.total_tokens:
        table.add_row("Avg Tokens", f"{statistics.mean(summary.total_tokens):.0f}")

    if summary.total_costs:
        table.add_row("Avg Cost", f"${statistics.mean(summary.total_costs):.4f}")
        table.add_row("Total Cost", f"${sum(summary.total_costs):.4f}")

    console.print(table)


def _generate_report(results: list[EvalResult], summary: EvalSummary) -> str:
    """Generate a markdown evaluation report."""
    lines = [
        "# AppForge Evaluation Report",
        "",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total Prompts:** {summary.total_prompts}",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Success Rate | {summary.success_rate:.1f}% |",
        f"| First-Pass Success Rate | {summary.first_pass_rate:.1f}% |",
        f"| Recovery Rate | {summary.recovery_rate:.1f}% |",
    ]

    if summary.durations:
        lines.append(f"| Latency p50 | {summary.percentile(summary.durations, 50):.1f}s |")
        lines.append(f"| Latency p95 | {summary.percentile(summary.durations, 95):.1f}s |")

    if summary.total_tokens:
        lines.append(f"| Avg Tokens/Run | {statistics.mean(summary.total_tokens):.0f} |")

    if summary.total_costs:
        lines.append(f"| Avg Cost/Run | ${statistics.mean(summary.total_costs):.4f} |")
        lines.append(f"| Total Cost | ${sum(summary.total_costs):.4f} |")

    lines.extend(["", "## Stage Latency Breakdown", ""])

    if summary.stage_durations:
        lines.extend([
            "| Stage | p50 | p95 | Mean |",
            "|-------|-----|-----|------|",
        ])
        for stage, durations in sorted(summary.stage_durations.items()):
            p50 = summary.percentile(durations, 50)
            p95 = summary.percentile(durations, 95)
            mean = statistics.mean(durations)
            lines.append(f"| {stage} | {p50:.1f}s | {p95:.1f}s | {mean:.1f}s |")

    lines.extend(["", "## Individual Results", ""])
    lines.extend([
        "| # | ID | Name | Status | Duration | Tokens | Tables | Endpoints | Pages |",
        "|---|-----|------|--------|----------|--------|--------|-----------|-------|",
    ])

    for i, r in enumerate(results, 1):
        status = "✅" if r.success else "❌"
        if r.error_message:
            status = f"💥 {r.error_message[:30]}"
        lines.append(
            f"| {i} | {r.prompt_id} | {r.prompt_name} | {status} | "
            f"{r.total_duration:.1f}s | {r.total_tokens} | "
            f"{r.tables_generated} | {r.endpoints_generated} | {r.pages_generated} |"
        )

    lines.extend(["", "---", "", "*Report generated by AppForge Evaluation Harness*"])
    return "\n".join(lines)


if __name__ == "__main__":
    run_evaluation()

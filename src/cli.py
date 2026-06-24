"""
AppForge CLI

Command-line interface for the multi-stage compiler pipeline.
Provides commands: generate, validate, simulate, eval.
"""

from __future__ import annotations

import json
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text
from rich import box

from src.config import config as app_config
from src.models.manifest import AppManifest, StageTelemetry

console = Console()

# Stage display names and icons
STAGE_INFO = {
    "intent_extraction": ("🔍 Intent Extraction", "Parsing natural language..."),
    "system_design": ("🏗️  System Design", "Generating architectural IR..."),
    "schema_generation_db": ("🗄️  DB Schema", "Building database tables..."),
    "schema_generation_api": ("🌐 API Schema", "Generating REST endpoints..."),
    "schema_generation_ui": ("🎨 UI Schema", "Designing page layouts..."),
    "validation_repair": ("✅ Validation & Repair", "Running type-checker..."),
    "runtime_simulation": ("🚀 Runtime Simulation", "Booting mock services..."),
}


@click.group()
@click.version_option(version="0.1.0", prog_name="appforge")
def main():
    """AppForge — Multi-Stage Compiler Pipeline

    Transform natural language descriptions into validated application manifests.
    """
    pass


@main.command()
@click.argument("description")
@click.option("--output", "-o", default=None, help="Output file path (default: output/<app_name>_manifest.json)")
@click.option("--fast-model", default=None, help="Override fast model (default: gemini-2.0-flash)")
@click.option("--analytical-model", default=None, help="Override analytical model (default: gemini-2.5-pro)")
def generate(description: str, output: str, fast_model: str, analytical_model: str):
    """Generate an application manifest from a natural language description.

    DESCRIPTION is the natural language description of the app to build.
    Wrap in quotes if it contains spaces.
    """
    # Apply model overrides
    if fast_model:
        app_config.models.fast_model = fast_model
    if analytical_model:
        app_config.models.analytical_model = analytical_model

    console.print()
    console.print(Panel(
        f"[bold cyan]{description}[/bold cyan]",
        title="[bold white]📝 Input Description[/bold white]",
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()

    # Run the pipeline with progress tracking
    from src.pipeline.orchestrator import PipelineOrchestrator

    try:
        app_config.provider.validate()
    except ValueError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        sys.exit(1)

    orchestrator = PipelineOrchestrator(app_config)

    def on_stage_start(stage_name: str):
        print(f"Starting stage: {stage_name}")

    def on_stage_complete(stage_name: str, telemetry: StageTelemetry):
        status = "success" if telemetry.duration_seconds > 0 else "failed"
        print(f"Completed stage: {stage_name} - Status: {status} - Time: {telemetry.duration_seconds:.2f}s")

    try:
        manifest = orchestrator.run(
            user_input=description,
            on_stage_start=on_stage_start,
            on_stage_complete=on_stage_complete,
        )
    except Exception as e:
        console.print(f"\n[bold red]Pipeline Error:[/bold red] {e}")
        sys.exit(1)

    # Determine output path
    if not output:
        output = f"output/{manifest.intent.app_name}_manifest.json"

    output_path = orchestrator.save_manifest(manifest, output)
    console.print()

    # Display results summary
    _display_results(manifest, output_path)


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True))
def validate(manifest_path: str):
    """Run validation checks on an existing manifest file."""
    console.print(f"\n[bold]Validating:[/bold] {manifest_path}\n")

    with open(manifest_path) as f:
        manifest = AppManifest.model_validate_json(f.read())

    from src.validation.structural import run_structural_checks
    from src.validation.referential import run_referential_checks

    structural = run_structural_checks(manifest.db_schema, manifest.api_schema, manifest.ui_schema)
    referential = run_referential_checks(manifest.design, manifest.db_schema, manifest.api_schema, manifest.ui_schema)

    all_errors = structural + referential
    errors = [e for e in all_errors if e.severity.value == "error"]
    warnings = [e for e in all_errors if e.severity.value != "error"]

    if errors:
        console.print(f"[bold red]✗ {len(errors)} errors found[/bold red]")
        for err in errors:
            console.print(f"  [red]ERROR[/red] [{err.location}] {err.message}")
    else:
        console.print("[bold green]✓ No errors found[/bold green]")

    if warnings:
        console.print(f"\n[bold yellow]⚠ {len(warnings)} warnings[/bold yellow]")
        for warn in warnings:
            console.print(f"  [yellow]WARN[/yellow]  [{warn.location}] {warn.message}")

    console.print()


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True))
def simulate(manifest_path: str):
    """Run the simulated runtime test on an existing manifest."""
    console.print(f"\n[bold]Simulating:[/bold] {manifest_path}\n")

    with open(manifest_path) as f:
        manifest = AppManifest.model_validate_json(f.read())

    from src.runtime.simulator import run_simulation

    result, telemetry = run_simulation(manifest.db_schema, manifest.api_schema)

    # Display results
    status_color = "green" if result.overall_status.value == "passed" else "red"
    console.print(f"[bold {status_color}]Overall: {result.overall_status.value.upper()}[/bold {status_color}]")
    console.print(f"  DB Boot:  {result.db_boot_status.value}")
    console.print(f"  API Boot: {result.api_boot_status.value}")
    console.print(f"  Tests:    {result.tests_passed}/{result.total_tests} passed")
    console.print(f"  Duration: {telemetry.duration_seconds:.2f}s")

    if result.details:
        console.print()
        for detail in result.details:
            icon = "✓" if detail.status.value == "passed" else "✗" if detail.status.value == "failed" else "⊘"
            color = "green" if detail.status.value == "passed" else "red" if detail.status.value == "failed" else "dim"
            msg = f"  [{color}]{icon}[/{color}] {detail.test_name}"
            if detail.error_message:
                msg += f" — {detail.error_message[:80]}"
            console.print(msg)

    console.print()


@main.command(name="eval")
@click.option("--output", "-o", default="output/eval_report.md", help="Output report path")
@click.option("--datasets", "-d", default="tests/datasets", help="Datasets directory")
def run_eval(output: str, datasets: str):
    """Run the evaluation suite against test datasets."""
    console.print("\n[bold]Running evaluation suite...[/bold]\n")
    console.print(f"  Datasets: {datasets}")
    console.print(f"  Output:   {output}")
    console.print()

    # Import and run evals
    try:
        from tests.run_evals import run_evaluation
        run_evaluation(datasets_dir=datasets, output_path=output, console=console)
    except ImportError:
        console.print("[bold red]Error:[/bold red] Evaluation module not found. Check tests/run_evals.py")
        sys.exit(1)


def _display_results(manifest: AppManifest, output_path: Path):
    """Display a rich summary of the pipeline results."""
    # Manifest overview table
    table = Table(
        title="Pipeline Results",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    table.add_row("App Name", manifest.intent.app_name)
    table.add_row("Features", str(len(manifest.intent.features)))
    table.add_row("Entities", str(len(manifest.design.entities)))
    table.add_row("Roles", str(len(manifest.design.roles)))
    table.add_row("DB Tables", str(len(manifest.db_schema.tables)))
    table.add_row("API Endpoints", str(len(manifest.api_schema.endpoints)))
    table.add_row("UI Pages", str(len(manifest.ui_schema.pages)))
    table.add_row("Assumptions Made", str(len(manifest.intent.assumptions)))

    # Validation status
    val = manifest.validation_report
    val_status = "[bold green]✓ PASSED[/bold green]" if val.passed else f"[bold red]✗ {val.error_count} errors[/bold red]"
    table.add_row("Validation", val_status)

    # Runtime status
    rt = manifest.runtime_test_result
    rt_status = f"[bold green]✓ PASSED[/bold green]" if rt.overall_status.value == "passed" else f"[bold red]✗ FAILED[/bold red]"
    table.add_row("Runtime Test", rt_status)

    console.print(table)
    console.print()

    # Telemetry table
    tel_table = Table(
        title="Stage Telemetry",
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
    )
    tel_table.add_column("Stage")
    tel_table.add_column("Duration", justify="right")
    tel_table.add_column("Tokens", justify="right")
    tel_table.add_column("Cost", justify="right")
    tel_table.add_column("Model")

    for stage in manifest.telemetry.stages:
        name, _ = STAGE_INFO.get(stage.stage_name, (stage.stage_name, ""))
        tokens = stage.input_tokens + stage.output_tokens
        tel_table.add_row(
            name,
            f"{stage.duration_seconds:.1f}s",
            str(tokens) if tokens else "—",
            f"${stage.estimated_cost_usd:.4f}" if stage.estimated_cost_usd else "—",
            stage.model_used or "—",
        )

    tel = manifest.telemetry
    tel_table.add_row(
        "[bold]Total[/bold]",
        f"[bold]{tel.total_duration_seconds:.1f}s[/bold]",
        f"[bold]{tel.total_input_tokens + tel.total_output_tokens}[/bold]",
        f"[bold]${tel.total_estimated_cost_usd:.4f}[/bold]",
        "",
    )

    console.print(tel_table)
    console.print()
    console.print(f"[bold green]Manifest saved to:[/bold green] {output_path}")
    console.print()


@main.command()
@click.argument("manifest_path", type=click.Path(exists=True))
def preview(manifest_path: str):
    """Generate an HTML UI preview from a manifest."""
    from src.ui_renderer import generate_preview
    console.print(f"\n[bold]Generating UI Preview:[/bold] [cyan]{manifest_path}[/cyan]\n")
    try:
        generate_preview(manifest_path)
    except Exception as e:
        console.print(f"[bold red]Preview Failed:[/bold red] {e}")


if __name__ == "__main__":
    main()

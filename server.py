"""
AppForge Web Server

FastAPI web server that wraps the pipeline orchestrator,
providing a web interface with real-time SSE progress streaming.
"""

from __future__ import annotations

import asyncio
import json
import time
import traceback
import uuid
import sys
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.config import config as app_config
from src.models.manifest import StageTelemetry


# ─── App Setup ──────────────────────────────────────────────────

app = FastAPI(
    title="AppForge",
    description="Multi-stage compiler pipeline: Natural Language → Config → Executable App",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─── In-Memory Task Store ───────────────────────────────────────

tasks: dict[str, dict] = {}


class GenerateRequest(BaseModel):
    prompt: str


class GenerateResponse(BaseModel):
    task_id: str
    status: str


# ─── Routes ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the web interface."""
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return HTMLResponse(content=index_path.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "provider": app_config.provider.provider,
        "fast_model": app_config.models.fast_model,
        "analytical_model": app_config.models.analytical_model,
    }


@app.post("/api/generate", response_model=GenerateResponse)
async def start_generation(request: GenerateRequest):
    """Start a new pipeline run. Returns a task_id for SSE streaming."""
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        "status": "queued",
        "prompt": request.prompt,
        "events": [],
        "result": None,
        "error": None,
        "start_time": time.time(),
    }

    # Launch the pipeline in a background thread
    asyncio.create_task(_run_pipeline_async(task_id, request.prompt))

    return GenerateResponse(task_id=task_id, status="queued")


@app.get("/api/stream/{task_id}")
async def stream_progress(task_id: str):
    """SSE stream for real-time pipeline progress updates."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_event_index = 0
        while True:
            task = tasks.get(task_id)
            if not task:
                break

            # Send any new events
            while last_event_index < len(task["events"]):
                event = task["events"][last_event_index]
                yield {
                    "event": event["type"],
                    "data": json.dumps(event["data"]),
                }
                last_event_index += 1

            # Check if pipeline is done
            if task["status"] in ("completed", "failed"):
                # Send final event
                if task["status"] == "completed":
                    yield {
                        "event": "complete",
                        "data": json.dumps(task["result"]),
                    }
                else:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": task["error"]}),
                    }
                break

            await asyncio.sleep(0.3)

    return EventSourceResponse(event_generator())


@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    """Get the final result for a completed task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    if task["status"] == "completed":
        return JSONResponse(content=task["result"])
    elif task["status"] == "failed":
        raise HTTPException(status_code=500, detail=task["error"])
    else:
        return JSONResponse(
            content={"status": task["status"], "message": "Pipeline still running"},
            status_code=202,
        )


# ─── Pipeline Execution ────────────────────────────────────────

STAGE_LABELS = {
    "intent_extraction": {"icon": "🔍", "label": "Intent Extraction", "desc": "Parsing natural language..."},
    "system_design": {"icon": "🏗️", "label": "System Design", "desc": "Generating architectural IR..."},
    "schema_generation_db": {"icon": "🗄️", "label": "DB Schema", "desc": "Building database tables..."},
    "schema_generation_api": {"icon": "🌐", "label": "API Schema", "desc": "Generating REST endpoints..."},
    "schema_generation_ui": {"icon": "🎨", "label": "UI Schema", "desc": "Designing page layouts..."},
    "validation_repair": {"icon": "✅", "label": "Validation & Repair", "desc": "Running type-checker..."},
    "runtime_simulation": {"icon": "🚀", "label": "Runtime Simulation", "desc": "Booting mock services..."},
}


async def _run_pipeline_async(task_id: str, prompt: str):
    """Run the pipeline in a background thread with progress callbacks."""
    task = tasks[task_id]
    task["status"] = "running"

    def on_stage_start(stage_name: str):
        info = STAGE_LABELS.get(stage_name, {"icon": "⚙️", "label": stage_name, "desc": ""})
        task["events"].append({
            "type": "stage_start",
            "data": {
                "stage": stage_name,
                "icon": info["icon"],
                "label": info["label"],
                "description": info["desc"],
                "timestamp": time.time(),
            },
        })

    def on_stage_complete(stage_name: str, telemetry: StageTelemetry):
        info = STAGE_LABELS.get(stage_name, {"icon": "⚙️", "label": stage_name, "desc": ""})
        task["events"].append({
            "type": "stage_complete",
            "data": {
                "stage": stage_name,
                "icon": info["icon"],
                "label": info["label"],
                "duration": round(telemetry.duration_seconds, 2),
                "tokens": telemetry.input_tokens + telemetry.output_tokens,
                "cost": round(telemetry.estimated_cost_usd, 4),
                "model": telemetry.model_used or "",
                "timestamp": time.time(),
            },
        })

    try:
        from src.pipeline.orchestrator import PipelineOrchestrator

        app_config.provider.validate()
        orchestrator = PipelineOrchestrator(app_config)

        # Run in thread to avoid blocking the event loop
        manifest = await asyncio.to_thread(
            orchestrator.run,
            user_input=prompt,
            on_stage_start=on_stage_start,
            on_stage_complete=on_stage_complete,
        )

        # Save manifest
        output_path = orchestrator.save_manifest(
            manifest, f"output/{manifest.intent.app_name}_manifest.json"
        )

        # Build the response
        manifest_dict = json.loads(manifest.model_dump_json())

        task["result"] = {
            "manifest": manifest_dict,
            "summary": {
                "app_name": manifest.intent.app_name,
                "features": len(manifest.intent.features),
                "assumptions": len(manifest.intent.assumptions),
                "entities": len(manifest.design.entities),
                "roles": len(manifest.design.roles),
                "tables": len(manifest.db_schema.tables),
                "endpoints": len(manifest.api_schema.endpoints),
                "pages": len(manifest.ui_schema.pages),
                "validation_passed": manifest.validation_report.passed,
                "validation_errors": manifest.validation_report.error_count,
                "validation_warnings": manifest.validation_report.warning_count,
                "repair_cycles": manifest.validation_report.repair_cycles_used,
                "runtime_passed": manifest.runtime_test_result.overall_status.value == "passed",
                "runtime_tests_total": manifest.runtime_test_result.total_tests,
                "runtime_tests_passed": manifest.runtime_test_result.tests_passed,
            },
            "telemetry": {
                "total_duration": round(manifest.telemetry.total_duration_seconds, 2),
                "total_tokens": manifest.telemetry.total_input_tokens + manifest.telemetry.total_output_tokens,
                "total_cost": round(manifest.telemetry.total_estimated_cost_usd, 4),
                "stages": [
                    {
                        "name": s.stage_name,
                        "duration": round(s.duration_seconds, 2),
                        "tokens": s.input_tokens + s.output_tokens,
                        "cost": round(s.estimated_cost_usd, 4),
                        "model": s.model_used or "",
                    }
                    for s in manifest.telemetry.stages
                ],
            },
            "output_path": str(output_path),
        }
        task["status"] = "completed"

    except Exception as e:
        task["error"] = f"{type(e).__name__}: {str(e)}"
        task["events"].append({
            "type": "error",
            "data": {
                "error": task["error"],
                "traceback": traceback.format_exc(),
            },
        })
        task["status"] = "failed"


# ─── Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print(f"\n>>> AppForge Web Server starting on http://localhost:{app_config.server.port}\n")
    uvicorn.run(
        "server:app",
        host=app_config.server.host,
        port=app_config.server.port,
        reload=False,
    )

# ⚡ AppForge — Multi-Stage Compiler Pipeline

**Natural Language → Structured Config → Validated → Executable**

AppForge is a deterministic, multi-pass compiler pipeline that transforms natural language application descriptions into validated, executable application manifests. It operates as a 4-stage compiler with a runtime verification layer.

> **This is not a prompt engineering wrapper.** It is an engineered system with modular stages, strict schema enforcement, programmatic validation, targeted repair, and runtime execution proof.

---

## 🏗️ Architecture

```
[User Input "Build a CRM..."]
     │
     ▼
 1. INTENT EXTRACTION ───► IntentManifest (features, users, tech stack, assumptions)
     │                      Model: Fast (speed-optimized)
     ▼
 2. SYSTEM DESIGN ───────► SystemDesignIR (RBAC, entities, workflows, feature gates)
     │                      Model: Analytical (reasoning-optimized)
     ▼
 3. SCHEMA GENERATION ───► DBSchema → APISchema → UISchema (sequential alignment)
     │                      Model: Analytical (reasoning-optimized)
     ▼
 4. VALIDATION & REPAIR ─► Rule-based checks + targeted LLM repair (max 3 cycles)
     │
     ▼
 5. RUNTIME SIMULATION ──► In-memory SQLite + FastAPI stub boot test
     │
     ▼
 [AppManifest JSON] ──────► Saved to output/
```

### Why This Architecture?

| Decision | Rationale |
|----------|-----------|
| **Sequential Schema Generation (DB→API→UI)** | Downstream schemas receive upstream output as context, preventing cross-layer misalignment at generation time |
| **Dual-Model Strategy** | Fast model for intent extraction (speed), analytical model for design/schema (reasoning quality) |
| **Programmatic Validation First** | Stage 4 is entirely rule-based. LLM repair is only invoked when errors are found, with minimal schema slices |
| **Fuzzy Naming Mismatch Detection** | Uses both `fuzz.ratio` and `fuzz.partial_ratio` to catch naming inconsistencies (`user_email` ↔ `email`) |
| **Runtime Verification** | Actually boots SQLite + FastAPI from generated schemas — catches errors static analysis cannot |

---

## 🚀 Quick Start

### 1. Install

```bash
git clone https://github.com/YOUR_USERNAME/appforge.git
cd appforge
pip install -e ".[dev]"
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set your API key and provider
```

Supported providers: `nvidia`, `gemini`, `openai`, `groq`

### 3. Run the Web Interface

```bash
python server.py
# Open http://localhost:8000
```

### 4. Or Use the CLI

```bash
# Generate a manifest
appforge generate "Build a CRM with contact management, deals pipeline, and email integration"

# Validate an existing manifest
appforge validate output/crm_manifest.json

# Run runtime simulation
appforge simulate output/crm_manifest.json

# Run the evaluation suite
appforge eval --output output/eval_report.md
```

---

## 🌐 Web Interface

The web interface provides:

- **Real-time pipeline progress** via Server-Sent Events (SSE)
- **Tabbed JSON viewer** (Intent / Design / DB / API / UI / Validation / Runtime)
- **Telemetry dashboard** (duration, tokens, cost per stage)
- **Validation & runtime status** badges
- **Copy-to-clipboard** for all JSON outputs
- **Example prompts** for quick testing

---

## 📁 Project Structure

```
appforge/
├── server.py                    # FastAPI web server (SSE streaming)
├── static/                      # Frontend (HTML/CSS/JS)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── src/
│   ├── cli.py                   # Rich CLI (generate/validate/simulate/eval)
│   ├── config.py                # Environment-based configuration
│   ├── models/                  # Pydantic typed contracts
│   │   ├── intent.py            # IntentManifest, FeatureSpec, TechPreferences
│   │   ├── design.py            # SystemDesignIR, Role, Entity, Workflow
│   │   ├── schema.py            # DBSchema, APISchema, UISchema
│   │   └── manifest.py          # AppManifest, ValidationReport, Telemetry
│   ├── pipeline/                # Compiler stages
│   │   ├── stage_1_intent.py    # Intent extraction + ambiguity detection
│   │   ├── stage_2_design.py    # Architectural IR generation (RBAC, entities)
│   │   ├── stage_3_schema.py    # Sequential DB→API→UI schema generation
│   │   ├── stage_4_validate.py  # Validation orchestration + repair loop
│   │   └── orchestrator.py      # Main pipeline controller
│   ├── providers/               # LLM provider abstraction
│   │   ├── base.py              # Abstract interface with retry + telemetry
│   │   ├── gemini.py            # Google Gemini (constrained decoding)
│   │   ├── nvidia_provider.py   # NVIDIA NIM API
│   │   ├── openai_provider.py   # OpenAI-compatible
│   │   └── groq_provider.py     # Groq
│   ├── validation/              # Validation engine
│   │   ├── structural.py        # Rule-based structural checks
│   │   ├── referential.py       # Cross-layer reference integrity
│   │   └── repair.py            # Targeted LLM repair (minimal slices)
│   └── runtime/                 # Execution verification
│       ├── simulator.py         # SQLite table creation + FastAPI stub boot
│       └── error_capture.py     # Structured traceback capture
├── tests/
│   ├── test_pipeline.py         # 20 unit tests (models, serialization)
│   ├── test_validation.py       # 13 unit tests (structural, referential)
│   ├── run_evals.py             # Evaluation harness (6 metrics)
│   └── datasets/
│       ├── standard_products.json  # 10 real product prompts
│       └── edge_cases.json         # 10 adversarial prompts
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 🧪 Testing

### Unit Tests (33/33 passing)

```bash
pytest tests/ -v
```

Key test coverage:
- Model serialization round-trip (JSON → Pydantic → JSON → Pydantic)
- Runtime simulator boots SQLite and FastAPI from schema fixtures
- Structural validator catches duplicate tables, empty columns, FK errors
- Referential validator catches cross-layer mismatches (API→DB, UI→API)
- Fuzzy naming mismatch detection (`user_email` ↔ `email`)

### Evaluation Suite

```bash
appforge eval --output output/eval_report.md
```

Runs 20 prompts (10 standard + 10 edge cases) and tracks:

| Metric | Description |
|--------|-------------|
| First-Pass Success Rate | % of prompts that pass validation on first generation |
| Recovery Rate | % of failed validations recovered by repair engine |
| Stage Latency (p50, p95) | Per-stage and total pipeline latency |
| Token Usage | Input + output tokens per run |
| Total Cost | Estimated API cost per run |
| Structural Completeness | Tables, endpoints, pages generated |

---

## 📈 Scalability Optimizations

Large application manifests originally caused context growth across pipeline stages.

To address this, AppForge introduces:

- **Context Compression**
- **Stage Summaries**
- **Checkpointing**
- **Runtime Verification**

These optimizations significantly reduce token usage and improve pipeline resilience.

---

## ⚙️ Validation & Repair System

This is the core differentiator. The system uses a **two-phase validation** approach:

### Phase 1: Rule-Based Validation (No LLM)
- **Structural checks**: Duplicate tables/endpoints, empty columns, missing PKs, FK integrity
- **Referential checks**: API fields must map to DB columns, UI data sources must map to API endpoints
- **Fuzzy naming**: Detects near-mismatches like `user_email` vs `email` using Levenshtein distance

### Phase 2: Targeted LLM Repair (Only When Errors Found)
- Extracts **minimal error slices** — only the broken schema fragment + error description
- Sends focused repair prompts (not full regeneration)
- Maximum 3 repair cycles (configurable)
- Each cycle only fixes the specific errors found, not the entire output

---

## 💰 Cost vs Quality Tradeoff

| Strategy | Latency | Cost | Quality |
|----------|---------|------|---------|
| Fast model for all stages | Low | Low | Medium |
| Analytical model for all stages | High | High | High |
| **Dual-model (default)** | **Medium** | **Medium** | **High** |
| Programmatic validation first | — | $0 | — |
| Targeted repair (vs full retry) | -60% | -70% | Same |

The dual-model strategy uses a fast model for Stage 1 (intent extraction) where speed matters, and an analytical model for Stages 2-4 where reasoning quality matters. This achieves high quality at ~60% of the cost of using the analytical model everywhere.

---

## 🔧 Configuration

All settings are controlled via environment variables (`.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `nvidia` | Provider: `nvidia`, `gemini`, `openai`, `groq` |
| `NVIDIA_API_KEY` | — | API key for NVIDIA NIM |
| `GEMINI_API_KEY` | — | API key for Google Gemini |
| `FAST_MODEL` | `moonshotai/kimi-k2.6` | Model for intent extraction |
| `ANALYTICAL_MODEL` | `moonshotai/kimi-k2.6` | Model for design/schema/repair |
| `MAX_REPAIR_CYCLES` | `3` | Maximum validation repair attempts |
| `PORT` | `8000` | Web server port |

---

## 📜 License

MIT

/**
 * AppForge Frontend — Pipeline Interaction Logic
 *
 * Handles:
 * - SSE streaming for real-time pipeline progress
 * - Dynamic stage rendering with status transitions
 * - Tabbed JSON viewer with syntax highlighting
 * - Copy-to-clipboard
 * - Example prompt buttons
 */

// ─── State ─────────────────────────────────────────────────────
let currentTaskId = null;
let manifestData = null;
let pipelineStartTime = null;
let timerInterval = null;

// ─── Stage Definitions ────────────────────────────────────────
const STAGES = [
  { id: "intent_extraction",    icon: "🔍", label: "Intent Extraction",    desc: "Parsing natural language..." },
  { id: "system_design",        icon: "🏗️", label: "System Design",       desc: "Generating architectural IR..." },
  { id: "schema_generation_db", icon: "🗄️", label: "DB Schema",           desc: "Building database tables..." },
  { id: "schema_generation_api",icon: "🌐", label: "API Schema",          desc: "Generating REST endpoints..." },
  { id: "schema_generation_ui", icon: "🎨", label: "UI Schema",           desc: "Designing page layouts..." },
  { id: "validation_repair",    icon: "✅", label: "Validation & Repair", desc: "Running type-checker..." },
  { id: "runtime_simulation",   icon: "🚀", label: "Runtime Simulation",  desc: "Booting mock services..." },
];


// ─── Initialization ────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadProviderInfo();
  setupExampleButtons();
  setupTabBar();
  setupKeyboardShortcut();
});


function loadProviderInfo() {
  fetch("/api/health")
    .then(r => r.json())
    .then(data => {
      const el = document.getElementById("provider-info");
      el.textContent = `${data.provider.toUpperCase()} · ${data.fast_model.split('/').pop()}`;
    })
    .catch(() => {
      document.getElementById("provider-info").textContent = "Offline";
    });
}


function setupExampleButtons() {
  document.querySelectorAll(".example-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.getElementById("prompt-input").value = btn.dataset.prompt;
      document.getElementById("prompt-input").focus();
    });
  });
}


function setupTabBar() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      renderCurrentTab();
    });
  });
}


function setupKeyboardShortcut() {
  document.getElementById("prompt-input").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      startGeneration();
    }
  });
}


// ─── Pipeline Execution ────────────────────────────────────────

async function startGeneration() {
  const prompt = document.getElementById("prompt-input").value.trim();
  if (!prompt) return;

  const btn = document.getElementById("generate-btn");
  btn.disabled = true;
  btn.classList.add("loading");

  // Reset UI
  hideSection("results-section");
  hideSection("json-section");
  hideSection("error-section");
  showSection("progress-section");
  renderInitialStages();
  startTimer();

  try {
    // 1. Start the pipeline
    const response = await fetch("/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || "Failed to start pipeline");
    }

    const { task_id } = await response.json();
    currentTaskId = task_id;

    // 2. Connect to SSE stream
    connectSSE(task_id);

  } catch (error) {
    showError(error.message);
    resetButton();
    stopTimer();
  }
}


function connectSSE(taskId) {
  const eventSource = new EventSource(`/api/stream/${taskId}`);

  eventSource.addEventListener("stage_start", (e) => {
    const data = JSON.parse(e.data);
    updateStageStatus(data.stage, "running");
  });

  eventSource.addEventListener("stage_complete", (e) => {
    const data = JSON.parse(e.data);
    updateStageStatus(data.stage, "completed", data);
  });

  eventSource.addEventListener("complete", (e) => {
    const data = JSON.parse(e.data);
    manifestData = data;
    eventSource.close();
    stopTimer();
    resetButton();
    renderResults(data);
  });

  eventSource.addEventListener("error", (e) => {
    try {
      const data = JSON.parse(e.data);
      showError(data.error);
    } catch {
      showError("Pipeline failed — connection lost");
    }
    eventSource.close();
    stopTimer();
    resetButton();
  });

  eventSource.onerror = () => {
    // EventSource auto-reconnects; we close on terminal events above
  };
}


// ─── Stage Rendering ───────────────────────────────────────────

function renderInitialStages() {
  const container = document.getElementById("pipeline-stages");
  container.innerHTML = STAGES.map(stage => `
    <div class="stage-item pending" id="stage-${stage.id}">
      <div class="stage-indicator">${stage.icon}</div>
      <div class="stage-info">
        <div class="stage-label">${stage.label}</div>
        <div class="stage-desc">${stage.desc}</div>
      </div>
      <div class="stage-meta" id="stage-meta-${stage.id}"></div>
    </div>
  `).join("");
}


function updateStageStatus(stageId, status, data = null) {
  const el = document.getElementById(`stage-${stageId}`);
  if (!el) return;

  // Remove old status classes
  el.classList.remove("pending", "running", "completed", "failed");
  el.classList.add(status);

  // Update indicator
  const indicator = el.querySelector(".stage-indicator");
  if (status === "completed") {
    indicator.textContent = "✓";
  } else if (status === "failed") {
    indicator.textContent = "✗";
  }

  // Update meta info for completed stages
  if (status === "completed" && data) {
    const meta = document.getElementById(`stage-meta-${stageId}`);
    const parts = [];
    if (data.duration) parts.push(`<span>⏱ ${data.duration}s</span>`);
    if (data.tokens) parts.push(`<span>📊 ${data.tokens.toLocaleString()} tok</span>`);
    if (data.model) parts.push(`<span>🤖 ${data.model.split('/').pop()}</span>`);
    meta.innerHTML = parts.join("");
  }
}


// ─── Results Rendering ─────────────────────────────────────────

function renderResults(data) {
  renderStatusBadges(data.summary);
  renderSummaryGrid(data.summary);
  renderTelemetry(data.telemetry);
  renderJSON(data.manifest);

  showSection("results-section");
  showSection("json-section");
}


function renderStatusBadges(summary) {
  const container = document.getElementById("status-badges");
  const badges = [];

  badges.push(`<span class="status-badge ${summary.validation_passed ? 'passed' : 'failed'}">
    ${summary.validation_passed ? '✓' : '✗'} Validation ${summary.validation_passed ? 'Passed' : 'Failed'}
    ${summary.validation_errors > 0 ? `(${summary.validation_errors} errors)` : ''}
  </span>`);

  badges.push(`<span class="status-badge ${summary.runtime_passed ? 'passed' : 'failed'}">
    ${summary.runtime_passed ? '✓' : '✗'} Runtime ${summary.runtime_passed ? 'Passed' : 'Failed'}
    (${summary.runtime_tests_passed}/${summary.runtime_tests_total} tests)
  </span>`);

  if (summary.repair_cycles > 0) {
    badges.push(`<span class="status-badge passed">🔧 ${summary.repair_cycles} Repair Cycle${summary.repair_cycles > 1 ? 's' : ''}</span>`);
  }

  if (summary.assumptions > 0) {
    badges.push(`<span class="status-badge passed">💡 ${summary.assumptions} Assumption${summary.assumptions > 1 ? 's' : ''} Made</span>`);
  }

  container.innerHTML = badges.join("");
}


function renderSummaryGrid(summary) {
  const container = document.getElementById("summary-grid");
  const cards = [
    { value: summary.app_name.replace(/_/g, " "), label: "App Name", cls: "" },
    { value: summary.features, label: "Features", cls: "" },
    { value: summary.entities, label: "Entities", cls: "" },
    { value: summary.roles, label: "Roles", cls: "" },
    { value: summary.tables, label: "DB Tables", cls: "" },
    { value: summary.endpoints, label: "API Endpoints", cls: "" },
    { value: summary.pages, label: "UI Pages", cls: "" },
    { value: summary.validation_passed && summary.runtime_passed ? "✓ Pass" : "✗ Fail",
      label: "Overall Status",
      cls: summary.validation_passed && summary.runtime_passed ? "success" : "error" },
  ];

  container.innerHTML = cards.map(c => `
    <div class="summary-card ${c.cls}">
      <div class="value">${c.value}</div>
      <div class="label">${c.label}</div>
    </div>
  `).join("");
}


function renderTelemetry(telemetry) {
  const container = document.getElementById("telemetry-list");

  const items = [
    { label: "Total Duration", value: `${telemetry.total_duration}s` },
    { label: "Total Tokens", value: telemetry.total_tokens.toLocaleString() },
    { label: "Estimated Cost", value: `$${telemetry.total_cost.toFixed(4)}` },
  ];

  // Add per-stage breakdown
  telemetry.stages.forEach(s => {
    const name = s.name.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    items.push({ label: `  └ ${name}`, value: `${s.duration}s · ${s.tokens} tok` });
  });

  container.innerHTML = items.map(i => `
    <div class="telemetry-item">
      <span class="t-label">${i.label}</span>
      <span class="t-value">${i.value}</span>
    </div>
  `).join("");
}


// ─── JSON Viewer ───────────────────────────────────────────────

const TAB_PATHS = {
  full: null,
  intent: "intent",
  design: "design",
  db: "db_schema",
  api: "api_schema",
  ui: "ui_schema",
  validation: "validation_report",
  runtime: "runtime_test_result",
};

function renderJSON(manifest) {
  manifestData = { manifest };
  renderCurrentTab();
}


function renderCurrentTab() {
  if (!manifestData?.manifest) return;

  const activeTab = document.querySelector(".tab-btn.active")?.dataset.tab || "full";
  const path = TAB_PATHS[activeTab];

  let data;
  if (path) {
    data = manifestData.manifest[path];
  } else {
    data = manifestData.manifest;
  }

  const formatted = JSON.stringify(data, null, 2);
  document.getElementById("json-output").innerHTML = syntaxHighlight(formatted);
}


function syntaxHighlight(json) {
  return json.replace(
    /("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    (match) => {
      let cls = "json-number";
      if (/^"/.test(match)) {
        if (/:$/.test(match)) {
          cls = "json-key";
        } else {
          cls = "json-string";
        }
      } else if (/true|false/.test(match)) {
        cls = "json-boolean";
      } else if (/null/.test(match)) {
        cls = "json-null";
      }
      return `<span class="${cls}">${match}</span>`;
    }
  );
}


function copyJSON() {
  const activeTab = document.querySelector(".tab-btn.active")?.dataset.tab || "full";
  const path = TAB_PATHS[activeTab];

  let data;
  if (path) {
    data = manifestData?.manifest?.[path];
  } else {
    data = manifestData?.manifest;
  }

  if (!data) return;

  const text = JSON.stringify(data, null, 2);
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById("copy-btn");
    btn.textContent = "✓ Copied!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = "📋 Copy";
      btn.classList.remove("copied");
    }, 2000);
  });
}


// ─── Timer ─────────────────────────────────────────────────────

function startTimer() {
  pipelineStartTime = Date.now();
  const timerEl = document.getElementById("pipeline-timer");
  timerInterval = setInterval(() => {
    const elapsed = ((Date.now() - pipelineStartTime) / 1000).toFixed(1);
    timerEl.textContent = `${elapsed}s`;
  }, 100);
}


function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}


// ─── UI Helpers ────────────────────────────────────────────────

function showSection(id) {
  document.getElementById(id).classList.add("visible");
}

function hideSection(id) {
  document.getElementById(id).classList.remove("visible");
}

function showError(message) {
  document.getElementById("error-box").innerHTML = `<code>${escapeHtml(message)}</code>`;
  showSection("error-section");
}

function resetButton() {
  const btn = document.getElementById("generate-btn");
  btn.disabled = false;
  btn.classList.remove("loading");
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

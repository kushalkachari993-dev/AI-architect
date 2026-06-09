const form = document.querySelector("#generateForm");
const requirementsFile = document.querySelector("#requirementsFile");
const storiesFile = document.querySelector("#storiesFile");
const requirementsText = document.querySelector("#requirementsText");
const storiesText = document.querySelector("#storiesText");
const domainSelect = document.querySelector("#domainSelect");
const requirementsName = document.querySelector("#requirementsName");
const storiesName = document.querySelector("#storiesName");
const generateButton = document.querySelector("#generateButton");
const downloadButton = document.querySelector("#downloadButton");
const refreshHistory = document.querySelector("#refreshHistory");
const historyList = document.querySelector("#historyList");
const approveButton = document.querySelector("#approveButton");
const architectureEditor = document.querySelector("#architectureEditor");
const runState = document.querySelector("#runState");
const results = document.querySelector("#results");
const emptyState = document.querySelector("#emptyState");
const projectName = document.querySelector("#projectName");
const projectSummary = document.querySelector("#projectSummary");
const generationMode = document.querySelector("#generationMode");
const modeLabel = document.querySelector("#modeLabel");
const costTotal = document.querySelector("#costTotal");

let lastFormData = null;
let lastPackage = null;
let lastProjectId = null;

mermaidReady().then(() => {
  if (window.mermaid) {
    window.mermaid.initialize({ startOnLoad: false, securityLevel: "loose", theme: "base" });
  }
});

requirementsFile.addEventListener("change", () => updateFileName(requirementsFile, requirementsName));
storiesFile.addEventListener("change", () => updateFileName(storiesFile, storiesName));
refreshHistory.addEventListener("click", loadHistory);
approveButton.addEventListener("click", approveEditedArchitecture);
loadStatus();
loadHistory();

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => activateTab(tab.dataset.tab));
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = buildFormData();
  if (!formData) {
    setState("error", "Missing input");
    projectSummary.textContent = "Upload files or paste text for both requirements and user stories.";
    return;
  }
  lastFormData = formData;

  setState("running", "Generating");
  generateButton.disabled = true;
  downloadButton.disabled = true;

  try {
    const response = await fetch("/generate", { method: "POST", body: formData });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    lastPackage = await response.json();
    lastProjectId = lastPackage.project_persisted ? lastPackage.project_id : null;
    renderPackage(lastPackage);
    setState("done", "Complete");
    downloadButton.disabled = false;
    loadHistory();
  } catch (error) {
    setState("error", "Failed");
    projectSummary.textContent = readableError(error);
  } finally {
    generateButton.disabled = false;
  }
});

downloadButton.addEventListener("click", async () => {
  if (!lastFormData && !lastProjectId) return;

  downloadButton.disabled = true;
  try {
    const response = lastProjectId
      ? await fetch(`/projects/${lastProjectId}/zip`)
      : await fetch("/generate.zip", { method: "POST", body: lastFormData });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "architecture-package.zip";
    link.click();
    URL.revokeObjectURL(url);
  } finally {
    downloadButton.disabled = false;
  }
});

function buildFormData() {
  const hasRequirements = requirementsFile.files[0] || requirementsText.value.trim();
  const hasStories = storiesFile.files[0] || storiesText.value.trim();
  if (!hasRequirements || !hasStories) return null;

  const formData = new FormData();
  if (requirementsFile.files[0]) formData.append("requirements_file", requirementsFile.files[0]);
  if (storiesFile.files[0]) formData.append("user_stories_file", storiesFile.files[0]);
  formData.append("requirements_text", requirementsText.value.trim());
  formData.append("user_stories_text", storiesText.value.trim());
  formData.append("domain", domainSelect.value);
  return formData;
}

function updateFileName(input, target) {
  target.textContent = input.files[0]?.name || "Choose file";
}

function setState(kind, label) {
  runState.className = `run-state ${kind}`;
  runState.textContent = label;
  modeLabel.textContent = label;
}

function activateTab(name) {
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
}

function renderPackage(pkg) {
  emptyState.classList.add("hidden");
  results.classList.remove("hidden");
  projectName.textContent = pkg.project_name;
  projectSummary.textContent = pkg.summary;
  generationMode.textContent = pkg.generation_mode;
  costTotal.textContent = formatUsd(sum(pkg.cost_estimate.map((item) => item.monthly_usd)));

  renderDiagram(pkg.architecture_diagram_mermaid);
  renderSchema(pkg.database_schema);
  renderApi(pkg.api_design);
  renderServices(pkg.microservices);
  renderOptions(pkg.architecture_options || []);
  renderReview(pkg.review_findings || [], pkg.scorecard || []);
  renderValidation(pkg.validation_report || []);
  renderCost(pkg.cost_estimate);
  renderNfrs(pkg.non_functional_requirements || []);
  renderAdrs(pkg.architecture_decision_records || []);
  renderDeploy(pkg.deployment_plan);
  renderFiles(pkg.generated_files);
  renderEditor(pkg);
}

async function loadStatus() {
  try {
    const response = await fetch("/status");
    if (!response.ok) return;
    const status = await response.json();
    modeLabel.textContent = status.llm_configured ? `${status.model} configured` : "Fallback mode";
  } catch {
    modeLabel.textContent = "Status unavailable";
  }
}

async function loadHistory() {
  try {
    const response = await fetch("/projects");
    if (!response.ok) return;
    const projects = await response.json();
    historyList.innerHTML = projects.length
      ? projects.map((project) => historyButton(project)).join("")
      : '<div class="history-item"><strong>No projects yet</strong><span>Generated runs appear here</span></div>';

    historyList.querySelectorAll("[data-project-id]").forEach((button) => {
      button.addEventListener("click", () => loadProject(button.dataset.projectId));
    });
  } catch {
    historyList.innerHTML = '<div class="history-item"><strong>History unavailable</strong><span>Try refreshing</span></div>';
  }
}

function historyButton(project) {
  return `
    <button class="history-item" type="button" data-project-id="${escapeHtml(project.id)}">
      <strong>${escapeHtml(project.project_name)}</strong>
      <span>${escapeHtml(project.generation_mode)} - ${formatDate(project.created_at)}</span>
    </button>
  `;
}

async function loadProject(projectId) {
  setState("running", "Loading");
  try {
    const response = await fetch(`/projects/${projectId}`);
    if (!response.ok) throw new Error(await response.text());
    lastPackage = await response.json();
    lastProjectId = projectId;
    lastFormData = null;
    renderPackage(lastPackage);
    downloadButton.disabled = false;
    setState("done", "Loaded");
  } catch (error) {
    setState("error", "Failed");
    projectSummary.textContent = readableError(error);
  }
}

async function renderDiagram(source) {
  const normalizedSource = normalizeMermaid(source);
  document.querySelector("#diagramSource").textContent = normalizedSource;
  const diagramView = document.querySelector("#diagramView");
  diagramView.textContent = "";

  await mermaidReady();
  if (!window.mermaid) {
    diagramView.textContent = normalizedSource;
    return;
  }

  try {
    const id = `architecture-${Date.now()}`;
    const rendered = await window.mermaid.render(id, normalizedSource);
    diagramView.innerHTML = rendered.svg;
  } catch {
    diagramView.innerHTML = '<div class="diagram-error">Diagram preview unavailable. Mermaid source is shown below.</div>';
  }
}

function normalizeMermaid(source) {
  let text = String(source || "").trim().replaceAll("\\n", "\n");
  if (!text) return "flowchart LR\n  client[Client] --> api[API]\n  api --> db[(Database)]";

  text = text.replace(/^```mermaid/i, "").replace(/^```/, "").replace(/```$/, "").trim();
  if (!/^(flowchart|graph)\s+(TD|TB|BT|RL|LR)\b/i.test(text)) {
    text = `flowchart LR\n${text}`;
  }
  if (!text.includes("\n")) {
    text = text
      .replace(/\s+(classDef\s+)/g, "\n$1")
      .replace(/\s+(class\s+[A-Za-z0-9_,]+\s+)/g, "\n$1")
      .replace(/\s+([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|-.->|==>))/g, "\n$1")
      .replace(/(?<!>)\s+([A-Za-z][A-Za-z0-9_]*(?:\[[^\]]+\]|\(\([^)]+\)\)|\([^)]+\)))/g, "\n$1")
      .replace(/^(flowchart|graph)\s+(TD|TB|BT|RL|LR)\s+/i, "$1 $2\n");
  }
  return text
    .split("\n")
    .map((line, index) => (index === 0 ? line.trim() : `  ${sanitizeMermaidLine(line.trim().replace(/;$/, ""))}`))
    .filter(Boolean)
    .join("\n");
}

function sanitizeMermaidLine(line) {
  return line.replace(/([A-Za-z][A-Za-z0-9_]*)\[([^\]"()]+)\]/g, (_match, id, label) => {
    return `${id}["${label.replaceAll('"', "")}"]`;
  });
}

function renderSchema(entities) {
  document.querySelector("#schemaGrid").innerHTML = entities
    .map(
      (entity) => `
        <article class="item-card">
          <h3>${escapeHtml(entity.name)}</h3>
          <div class="chip-row">${entity.fields.map((field) => `<span class="chip">${escapeHtml(field)}</span>`).join("")}</div>
          ${entity.relationships?.length ? `<p>${escapeHtml(entity.relationships.join(", "))}</p>` : ""}
        </article>
      `,
    )
    .join("");
}

function renderApi(endpoints) {
  document.querySelector("#apiTable").innerHTML = `
    <table>
      <thead><tr><th>Method</th><th>Path</th><th>Purpose</th></tr></thead>
      <tbody>
        ${endpoints
          .map(
            (endpoint) => `
              <tr>
                <td><strong>${escapeHtml(endpoint.method)}</strong></td>
                <td><code>${escapeHtml(endpoint.path)}</code></td>
                <td>${escapeHtml(endpoint.purpose)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderServices(services) {
  document.querySelector("#serviceGrid").innerHTML = services
    .map(
      (service) => `
        <article class="item-card">
          <h3>${escapeHtml(service.name)}</h3>
          <p>${escapeHtml(service.responsibility)}</p>
          <div class="chip-row">${service.owns.map((item) => `<span class="chip">${escapeHtml(item)}</span>`).join("")}</div>
        </article>
      `,
    )
    .join("");
}

function renderOptions(options) {
  document.querySelector("#optionsGrid").innerHTML = options
    .map(
      (option) => `
        <article class="item-card">
          <h3>${escapeHtml(option.name)}</h3>
          <p>${escapeHtml(option.description)}</p>
          <p><strong>Recommended for:</strong> ${escapeHtml(option.recommended_for)}</p>
          <div class="split-list">
            <div><strong>Pros</strong>${listHtml(option.pros)}</div>
            <div><strong>Cons</strong>${listHtml(option.cons)}</div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderReview(findings, scorecard) {
  document.querySelector("#reviewGrid").innerHTML = findings
    .map(
      (finding) => `
        <article class="item-card">
          <h3>${escapeHtml(finding.area)}</h3>
          <span class="severity ${escapeHtml(finding.severity)}">${escapeHtml(finding.severity)}</span>
          <p>${escapeHtml(finding.finding)}</p>
          <p><strong>Recommendation:</strong> ${escapeHtml(finding.recommendation)}</p>
        </article>
      `,
    )
    .join("");

  document.querySelector("#scorecardTable").innerHTML = `
    <div class="scorecard-heading">
      <h3>Risk Scorecard</h3>
      <p>Lower is better: 1 means low risk, 10 means high risk.</p>
    </div>
    <table>
      <thead><tr><th>Category</th><th>Risk</th><th>Rationale</th></tr></thead>
      <tbody>
        ${scorecard
          .map(
            (item) => `
              <tr>
                <td>${escapeHtml(item.category)}</td>
                <td>${riskBadge(item.score)}</td>
                <td>${escapeHtml(item.rationale)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderValidation(items) {
  document.querySelector("#validationTable").innerHTML = `
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Details</th><th>Recommendation</th></tr></thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>${escapeHtml(item.check)}</td>
                <td><span class="validation-status ${escapeHtml(item.status)}">${escapeHtml(item.status)}</span></td>
                <td>${escapeHtml(item.details)}</td>
                <td>${escapeHtml(item.recommendation)}</td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function riskBadge(score) {
  const numericScore = Number(score || 0);
  const level = numericScore <= 3 ? "low" : numericScore <= 6 ? "medium" : "high";
  return `<span class="risk-badge ${level}">${escapeHtml(level)} risk - ${escapeHtml(numericScore)}/10</span>`;
}

function renderCost(items) {
  document.querySelector("#costTable").innerHTML = `
    <table>
      <thead><tr><th>Component</th><th>Assumption</th><th>Monthly</th></tr></thead>
      <tbody>
        ${items
          .map(
            (item) => `
              <tr>
                <td>${escapeHtml(item.component)}</td>
                <td>${escapeHtml(item.assumption)}</td>
                <td><strong>${formatUsd(item.monthly_usd)}</strong></td>
              </tr>
            `,
          )
          .join("")}
      </tbody>
    </table>
  `;
}

function renderNfrs(items) {
  document.querySelector("#nfrGrid").innerHTML = items
    .map(
      (item) => `
        <article class="item-card">
          <h3>${escapeHtml(item.category)}</h3>
          <p>${escapeHtml(item.recommendation)}</p>
        </article>
      `,
    )
    .join("");
}

function renderAdrs(items) {
  document.querySelector("#adrGrid").innerHTML = items
    .map(
      (item) => `
        <article class="item-card">
          <h3>${escapeHtml(item.id)}: ${escapeHtml(item.decision)}</h3>
          <p>${escapeHtml(item.rationale)}</p>
          <div class="split-list">
            <div><strong>Alternatives</strong>${listHtml(item.alternatives)}</div>
            <div><strong>Consequences</strong>${listHtml(item.consequences)}</div>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderDeploy(steps) {
  document.querySelector("#deployList").innerHTML = steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("");
}

function listHtml(items) {
  return `<ul>${(items || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderFiles(files) {
  const groups = [
    ["FastAPI", files.fastapi_code],
    ["React", files.react_frontend || {}],
    ["Database", files.database_files || {}],
    ["Docker", files.docker_files],
    ["Terraform", files.terraform],
  ];
  document.querySelector("#filesGrid").innerHTML = groups
    .flatMap(([group, entries]) =>
      Object.entries(entries).map(
        ([path, content]) => `
          <button class="file-button" type="button" data-content="${encodeURIComponent(content)}">
            <strong>${escapeHtml(group)}</strong><br />
            <span>${escapeHtml(path)}</span>
          </button>
        `,
      ),
    )
    .join("");

  document.querySelectorAll(".file-button").forEach((button) => {
    button.addEventListener("click", () => {
      const content = decodeURIComponent(button.dataset.content);
      const blob = new Blob([content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = button.querySelector("span").textContent.split("/").pop();
      link.click();
      URL.revokeObjectURL(url);
    });
  });
}

function renderEditor(pkg) {
  const editable = { ...pkg };
  delete editable.generated_files;
  delete editable.generation_mode;
  delete editable.project_id;
  delete editable.created_at;
  architectureEditor.value = JSON.stringify(editable, null, 2);
}

async function approveEditedArchitecture() {
  approveButton.disabled = true;
  setState("running", "Approving");
  try {
    const plan = JSON.parse(architectureEditor.value);
    const response = await fetch("/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    });
    if (!response.ok) throw new Error(await response.text());
    lastPackage = await response.json();
    lastProjectId = lastPackage.project_persisted ? lastPackage.project_id : null;
    lastFormData = null;
    renderPackage(lastPackage);
    downloadButton.disabled = false;
    setState("done", "Approved");
    loadHistory();
    activateTab("files");
  } catch (error) {
    setState("error", "Invalid edit");
    projectSummary.textContent = readableError(error);
  } finally {
    approveButton.disabled = false;
  }
}

function formatUsd(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function formatDate(value) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(
    new Date(value),
  );
}

function sum(values) {
  return values.reduce((total, value) => total + Number(value || 0), 0);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function readableError(error) {
  const message = error?.message || "Request failed.";
  return message.length > 220 ? `${message.slice(0, 220)}...` : message;
}

function mermaidReady() {
  return new Promise((resolve) => {
    if (window.mermaid) {
      resolve();
      return;
    }
    window.addEventListener("load", resolve, { once: true });
  });
}

(function initializePlanner(global) {
  "use strict";

  const STORAGE_KEY = "cloudforge_visual_planner_blueprint";
  const DEFAULT_PROMPT = "Deploy a production-ready FastAPI app with PostgreSQL, S3 storage, and HTTPS.";

  const state = {
    prompt: "",
    activeBlueprint: null,
    loading: false,
    actionLoading: "",
    error: "",
  };

  const icons = {
    diagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h5v5H5zM14 4h5v5h-5zM14 15h5v5h-5z"></path><path d="M10 10.5h2c1.1 0 2-.9 2-2v-2M10 10.5h2c1.1 0 2 .9 2 2v5"></path></svg>',
    resources: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.5-8 4.5-8-4.5L12 3Z"></path><path d="m4 12 8 4.5 8-4.5M4 16.5 12 21l8-4.5"></path></svg>',
    cost: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7H14a3.5 3.5 0 0 1 0 7H6"></path></svg>',
    shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 20 7v5c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V7l8-4Z"></path><path d="m9 12 2 2 4-5"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function isMounted() {
    return global.router?.currentView === "visual-planner";
  }

  function currencyFormatter(currency) {
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency || "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    } catch {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
    }
  }

  function titleCase(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function statusTone(status) {
    if (["approved", "deployed"].includes(status)) return "success";
    if (["deploying", "saved"].includes(status)) return "warning";
    if (["failed", "cancelled"].includes(status)) return "danger";
    return "primary";
  }

  function riskTone(level) {
    if (["critical", "high"].includes(level)) return "danger";
    if (level === "medium") return "warning";
    if (level === "low") return "success";
    return "primary";
  }

  function visibilityTone(visibility) {
    if (visibility === "public") return "warning";
    if (visibility === "private") return "success";
    return "primary";
  }

  function badge(text, tone = "primary", className = "") {
    return `<span class="planner-badge planner-badge--${tone}${className ? ` ${className}` : ""}">${escapeHtml(text)}</span>`;
  }

  function persistBlueprint(blueprint) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(blueprint));
    } catch {
      /* Local persistence is optional; the planner still works without it. */
    }
  }

  function loadStoredBlueprint() {
    try {
      const blueprint = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (blueprint && typeof blueprint === "object" && blueprint.blueprint_id) {
        state.activeBlueprint = blueprint;
        state.prompt = blueprint.user_prompt || state.prompt;
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  function render() {
    const prompt = state.prompt || DEFAULT_PROMPT;
    return `
      <div class="view planner-view" data-view="visual-planner">
        <section class="planner-composer" aria-labelledby="planner-composer-title">
          <div class="planner-composer__copy">
            <span class="planner-kicker">CloudForge Visual Planner</span>
            <h2 id="planner-composer-title">What do you want to deploy?</h2>
          </div>
          <form class="planner-form" id="planner-generate-form">
            <label class="sr-only" for="planner-prompt">Deployment prompt</label>
            <textarea
              class="planner-textarea"
              id="planner-prompt"
              name="prompt"
              rows="4"
              placeholder="Describe the application, data stores, networking, and production requirements."
            >${escapeHtml(prompt)}</textarea>
            <div class="planner-form__footer">
              <p class="planner-form__hint">Blueprint generation creates a reviewed plan only. It does not deploy AWS resources.</p>
              <button class="planner-button planner-button--primary" type="submit" data-planner-generate>
                <span class="planner-button__label">Generate Plan</span>
              </button>
            </div>
          </form>
        </section>

        <section class="planner-result-shell" id="planner-result" aria-live="polite"></section>
      </div>
    `;
  }

  function mount() {
    if (!state.activeBlueprint) {
      loadStoredBlueprint();
    }
    renderPlannerBody();
  }

  function setGenerateLoading(isLoading) {
    const button = document.querySelector("[data-planner-generate]");
    if (!button) return;
    const label = button.querySelector(".planner-button__label");
    button.disabled = isLoading;
    button.setAttribute("aria-busy", String(isLoading));
    if (isLoading) {
      label.dataset.originalText = label.textContent;
      label.textContent = "Generating";
      button.insertAdjacentHTML("afterbegin", global.Components.spinner());
    } else {
      button.querySelector(".spinner")?.remove();
      label.textContent = label.dataset.originalText || "Generate Plan";
      button.removeAttribute("aria-busy");
    }
  }

  function renderPlannerBody() {
    if (!isMounted()) return;
    const result = document.getElementById("planner-result");
    if (!result) return;

    setGenerateLoading(state.loading);

    if (state.loading) {
      result.innerHTML = loadingState();
      return;
    }

    if (state.error) {
      result.innerHTML = errorState(state.error);
      return;
    }

    if (!state.activeBlueprint) {
      result.innerHTML = emptyState();
      return;
    }

    result.innerHTML = blueprintState(state.activeBlueprint);
  }

  function emptyState() {
    return `
      <div class="planner-empty">
        <div>
          <h3>No blueprint generated yet</h3>
          <p>Enter a deployment prompt above to generate a diagram, resource list, cost estimate, and security review.</p>
        </div>
      </div>
    `;
  }

  function loadingState() {
    return `
      <div class="planner-loading" role="status">
        ${global.Components.spinner()}
        <div>
          <strong>Generating deployment blueprint</strong>
          <p>Planning resources, diagram text, cost, and security review.</p>
        </div>
      </div>
    `;
  }

  function errorState(message) {
    return `
      <div class="planner-error" role="alert">
        <div>
          <strong>Unable to generate plan</strong>
          <p>${escapeHtml(message)}</p>
        </div>
        <button class="planner-button planner-button--secondary" type="button" data-planner-retry>Try again</button>
      </div>
    `;
  }

  function blueprintState(blueprint) {
    const status = blueprint.status || "draft";
    return `
      <div class="planner-blueprint">
        <header class="planner-blueprint__header">
          <div>
            <div class="planner-title-row">
              <h2>${escapeHtml(blueprint.name || "Deployment Blueprint")}</h2>
              ${badge(titleCase(status), statusTone(status))}
            </div>
            <p>${escapeHtml(blueprint.summary || "Review the generated architecture before approving it.")}</p>
          </div>
          <div class="planner-actions" aria-label="Blueprint actions">
            <button class="planner-button planner-button--secondary" type="button" data-planner-action="save" ${buttonDisabled("save", blueprint)}>
              ${actionButtonContent("save", "Save Plan")}
            </button>
            <button class="planner-button planner-button--primary" type="button" data-planner-action="approve" ${buttonDisabled("approve", blueprint)}>
              ${actionButtonContent("approve", "Approve")}
            </button>
            <button class="planner-button planner-button--outline" type="button" disabled title="Execution gate not ready">
              Execute
            </button>
          </div>
        </header>

        <section class="planner-prompt-summary">
          <span>Prompt</span>
          <p>${escapeHtml(blueprint.user_prompt)}</p>
        </section>

        <div class="planner-grid">
          ${diagramPanel(blueprint)}
          ${costPanel(blueprint)}
          ${resourcesPanel(blueprint)}
          ${securityPanel(blueprint)}
        </div>
      </div>
    `;
  }

  function buttonDisabled(action, blueprint) {
    const status = blueprint.status || "draft";
    const loading = state.actionLoading === action;
    if (loading) return "disabled aria-busy=\"true\"";
    if (action === "save" && status !== "draft") return "disabled";
    if (action === "approve" && !["draft", "saved"].includes(status)) return "disabled";
    if (state.actionLoading) return "disabled";
    return "";
  }

  function actionButtonContent(action, label) {
    if (state.actionLoading !== action) {
      return escapeHtml(label);
    }
    return `${global.Components.spinner()}<span>${escapeHtml(action === "save" ? "Saving" : "Approving")}</span>`;
  }

  function panelHeader(icon, title, meta = "") {
    return `
      <header class="planner-panel__header">
        <span class="planner-panel__icon">${icon}</span>
        <h3>${escapeHtml(title)}</h3>
        ${meta ? `<span class="planner-panel__meta">${meta}</span>` : ""}
      </header>
    `;
  }

  function diagramPanel(blueprint) {
    const diagram = blueprint.diagram_mermaid || "graph TD\n  plan[Deployment blueprint]\n  review[Security review]\n  plan --> review";
    return `
      <section class="planner-panel planner-panel--diagram">
        ${panelHeader(icons.diagram, "Architecture Diagram", badge("Mermaid", "primary"))}
        <pre class="planner-diagram" aria-label="Mermaid architecture diagram"><code>${escapeHtml(diagram)}</code></pre>
      </section>
    `;
  }

  function resourcesPanel(blueprint) {
    const resources = Array.isArray(blueprint.resources) ? blueprint.resources : [];
    const rows = resources.map((resource) => `
      <tr>
        <td>
          <strong>${escapeHtml(resource.name)}</strong>
          <code>${escapeHtml(resource.id)}</code>
        </td>
        <td>${escapeHtml(resource.service || "-")}</td>
        <td>${escapeHtml(resource.type || "-")}</td>
        <td>${badge(titleCase(resource.visibility), visibilityTone(resource.visibility), "planner-badge--compact")}</td>
        <td>${badge(titleCase(resource.risk_level), riskTone(resource.risk_level), "planner-badge--compact")}</td>
        <td class="planner-table__cost">${escapeHtml(currencyFormatter(blueprint.estimated_cost?.currency).format(Number(resource.estimated_monthly_cost || 0)))}</td>
      </tr>
    `).join("");

    return `
      <section class="planner-panel planner-panel--resources">
        ${panelHeader(icons.resources, "Resources", `<span>${resources.length} planned</span>`)}
        <div class="planner-table-wrap">
          ${resources.length ? `
            <table class="planner-table">
              <thead>
                <tr>
                  <th>Resource</th>
                  <th>Service</th>
                  <th>Type</th>
                  <th>Visibility</th>
                  <th>Risk</th>
                  <th>Monthly</th>
                </tr>
              </thead>
              <tbody>${rows}</tbody>
            </table>
          ` : '<p class="planner-muted">No resources were returned for this blueprint.</p>'}
        </div>
      </section>
    `;
  }

  function costPanel(blueprint) {
    const estimate = blueprint.estimated_cost || {};
    const format = currencyFormatter(estimate.currency);
    const total = format.format(Number(estimate.estimated_monthly_total || 0));
    const breakdown = estimate.breakdown && typeof estimate.breakdown === "object"
      ? Object.entries(estimate.breakdown)
      : [];
    const assumptions = Array.isArray(estimate.assumptions) ? estimate.assumptions : [];

    return `
      <section class="planner-panel planner-panel--cost">
        ${panelHeader(icons.cost, "Cost Estimate", `<span>${escapeHtml(estimate.currency || "USD")}</span>`)}
        <div class="planner-cost-total">
          <span>Total monthly</span>
          <strong>${escapeHtml(total)}</strong>
        </div>
        ${breakdown.length ? `
          <dl class="planner-cost-list">
            ${breakdown.map(([name, value]) => `
              <div>
                <dt>${escapeHtml(name)}</dt>
                <dd>${escapeHtml(format.format(Number(value || 0)))}</dd>
              </div>
            `).join("")}
          </dl>
        ` : ""}
        ${assumptions.length ? `<p class="planner-muted">${escapeHtml(assumptions[0])}</p>` : ""}
      </section>
    `;
  }

  function securityPanel(blueprint) {
    const review = blueprint.security_review || {};
    const warnings = Array.isArray(review.warnings) ? review.warnings : [];
    const risk = review.risk_level || "low";
    const warningRows = warnings.map((warning) => `
      <li class="planner-warning">
        ${badge(titleCase(warning.severity), riskTone(warning.severity), "planner-badge--compact")}
        <div>
          <strong>${escapeHtml(warning.message)}</strong>
          ${warning.resource_id ? `<code>${escapeHtml(warning.resource_id)}</code>` : ""}
          ${warning.recommendation ? `<p>${escapeHtml(warning.recommendation)}</p>` : ""}
        </div>
      </li>
    `).join("");

    return `
      <section class="planner-panel planner-panel--security">
        ${panelHeader(icons.shield, "Security Review", badge(titleCase(risk), riskTone(risk)))}
        <div class="planner-security-score">
          <span>Score</span>
          <strong>${Number(review.security_score ?? 0)}</strong>
          <small>${review.passed ? "Passed" : "Needs review"}</small>
        </div>
        <p class="planner-security-summary">${escapeHtml(review.summary || "Security review completed.")}</p>
        ${warnings.length ? `
          <ul class="planner-warning-list">${warningRows}</ul>
        ` : '<p class="planner-muted">No security warnings were returned for this blueprint.</p>'}
      </section>
    `;
  }

  async function handleGenerate(form) {
    const prompt = form.elements.prompt.value.trim();
    state.prompt = prompt;
    state.error = "";

    if (!prompt) {
      state.error = "Describe what you want CloudForge to deploy.";
      renderPlannerBody();
      return;
    }

    state.loading = true;
    renderPlannerBody();
    try {
      const blueprint = await global.api.request("POST", "/blueprints/generate", { prompt });
      state.activeBlueprint = blueprint;
      state.prompt = blueprint.user_prompt || prompt;
      persistBlueprint(blueprint);
      global.Components.toast("Blueprint generated.", "success");
    } catch (error) {
      state.error = error.message || "The blueprint API request failed.";
    } finally {
      state.loading = false;
      renderPlannerBody();
    }
  }

  async function updateBlueprint(action) {
    const blueprintId = state.activeBlueprint?.blueprint_id;
    if (!blueprintId || state.actionLoading) return;

    state.actionLoading = action;
    renderPlannerBody();
    try {
      const blueprint = await global.api.request("POST", `/blueprints/${encodeURIComponent(blueprintId)}/${action}`);
      state.activeBlueprint = blueprint;
      persistBlueprint(blueprint);
      global.Components.toast(action === "save" ? "Plan saved." : "Blueprint approved.", "success");
    } catch (error) {
      global.Components.toast(error.message || "Unable to update blueprint.", "danger");
    } finally {
      state.actionLoading = "";
      renderPlannerBody();
    }
  }

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "planner-generate-form" || !isMounted()) return;
    event.preventDefault();
    handleGenerate(event.target);
  });

  document.addEventListener("input", (event) => {
    if (event.target.id !== "planner-prompt" || !isMounted()) return;
    state.prompt = event.target.value;
    state.error = "";
  });

  document.addEventListener("click", (event) => {
    if (!isMounted()) return;

    if (event.target.closest("[data-planner-retry]")) {
      const form = document.getElementById("planner-generate-form");
      if (form) handleGenerate(form);
      return;
    }

    const actionButton = event.target.closest("[data-planner-action]");
    if (actionButton) {
      updateBlueprint(actionButton.dataset.plannerAction);
    }
  });

  global.Planner = { render, mount };
})(window);

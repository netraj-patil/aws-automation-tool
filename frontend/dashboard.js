(function initializeDashboard(global) {
  "use strict";

  const state = {
    data: null,
    loading: false,
    error: "",
    serviceFilter: "all",
    search: "",
  };

  const icons = {
    resources: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 4.5-8 4.5-8-4.5L12 3Z"></path><path d="m4 12 8 4.5 8-4.5M4 16.5 12 21l8-4.5"></path></svg>',
    running: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7L8 5Z"></path></svg>',
    broken: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 9v4M12 17h.01"></path><path d="m10.3 3.9-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3.1l-8-14a2 2 0 0 0-3.4 0Z"></path></svg>',
    cost: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7H14a3.5 3.5 0 0 1 0 7H6"></path></svg>',
    plan: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16M4 12h12M4 19h8"></path><path d="m16 17 2 2 4-5"></path></svg>',
    approval: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 20 7v5c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V7l8-4Z"></path><path d="m9 12 2 2 4-5"></path></svg>',
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
    return global.router?.currentView === "dashboard";
  }

  function activeRegion() {
    return document.querySelector('[data-action="select-region"]')?.value
      || localStorage.getItem("active_aws_region")
      || "us-east-1";
  }

  function titleCase(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function currencyFormatter(currency) {
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency || "USD",
        maximumFractionDigits: 2,
      });
    } catch {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      });
    }
  }

  function formatMoney(value, currency) {
    return currencyFormatter(currency).format(Number(value || 0));
  }

  function formatDate(value) {
    if (!value) return "-";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function tone(value) {
    const normalized = String(value || "").toLowerCase();
    if (["running", "active", "healthy", "success", "low", "deployed", "completed"].includes(normalized)) return "success";
    if (["warning", "medium", "planned", "pending_approval", "approved", "executing"].includes(normalized)) return "warning";
    if (["failed", "critical", "high", "error", "cancelled"].includes(normalized)) return "danger";
    return "neutral";
  }

  function badge(value, className = "") {
    return `<span class="state-badge state-badge--${tone(value)}${className ? ` ${className}` : ""}">${escapeHtml(titleCase(value))}</span>`;
  }

  function render() {
    return `
      <div class="view dashboard-view" data-view="dashboard">
        <section id="dashboard-root" aria-live="polite">
          ${loadingState()}
        </section>
      </div>
    `;
  }

  function loadingState() {
    return `
      <div class="dashboard-loading-grid">
        ${Array.from({ length: 6 }, (_, index) => `
          <article class="summary-card summary-card--loading">
            <span class="skeleton skeleton--icon"></span>
            <div>
              <span class="skeleton skeleton--text" style="--skeleton-index: ${index}"></span>
              <span class="skeleton skeleton--text" style="--skeleton-index: ${index + 1}"></span>
            </div>
          </article>
        `).join("")}
      </div>
    `;
  }

  function errorState(message) {
    return `
      <div class="dashboard-error" role="alert">
        <span class="dashboard-error__icon" aria-hidden="true">!</span>
        <div>
          <strong>Unable to load dashboard</strong>
          <p>${escapeHtml(message)}</p>
        </div>
        <button class="button button--secondary" type="button" data-dashboard-action="retry">Retry</button>
      </div>
    `;
  }

  function renderBody() {
    if (!isMounted()) return;
    const root = document.getElementById("dashboard-root");
    if (!root) return;
    if (state.loading) {
      root.innerHTML = loadingState();
      return;
    }
    if (state.error) {
      root.innerHTML = errorState(state.error);
      return;
    }
    if (!state.data) {
      root.innerHTML = loadingState();
      return;
    }

    root.innerHTML = `
      ${modeBanner(state.data)}
      ${warningsPanel(state.data.warnings)}
      ${overviewPanel(state.data)}
      ${summaryGrid(state.data)}
      <div class="dashboard-workbench">
        ${inventorySection(state.data.resources || [])}
        ${costSection(state.data.costs || {})}
        ${runningSection(state.data.running_resources || [])}
        ${brokenSection(state.data.broken_resources || [])}
        ${agentPlanSection(state.data.agent_next_actions || [])}
        ${approvalsSection(state.data.pending_approvals || [])}
        ${activitySection(state.data.recent_activity || [])}
      </div>
    `;
  }

  function overviewPanel(data) {
    const summary = data.summary || {};
    const costs = data.costs || {};
    const currency = costs.currency || "USD";
    const broken = Number(summary.broken_resources || 0);
    const approvals = Number(summary.pending_approvals || 0);
    const actions = Number(summary.pending_agent_actions || 0);
    const attentionTone = broken || approvals ? "warning" : "success";

    return `
      <section class="dashboard-overview" aria-label="AWS account overview">
        <div class="dashboard-overview__main">
          <span class="dashboard-overview__eyebrow">Active region</span>
          <h2>${escapeHtml(activeRegion())}</h2>
          <p>${escapeHtml(summary.total_resources || 0)} resources monitored across the current workspace.</p>
          <div class="dashboard-overview__stats">
            <span><strong>${escapeHtml(summary.running_resources || 0)}</strong> running</span>
            <span><strong>${escapeHtml(formatMoney(summary.monthly_cost_estimate, currency))}</strong> monthly estimate</span>
            <span><strong>${escapeHtml(actions)}</strong> agent actions</span>
          </div>
        </div>
        <aside class="dashboard-attention dashboard-attention--${attentionTone}">
          <span class="dashboard-attention__label">Needs attention</span>
          <strong>${escapeHtml(broken + approvals)}</strong>
          <p>${escapeHtml(broken)} broken checks and ${escapeHtml(approvals)} approvals waiting.</p>
        </aside>
      </section>
    `;
  }

  function modeBanner(data) {
    if (data.mode !== "demo" || !data.banner) return "";
    return `
      <div class="dashboard-mode-banner" role="status">
        <strong>Demo mode</strong>
        <span>${escapeHtml(data.banner)}</span>
      </div>
    `;
  }

  function warningsPanel(warnings) {
    if (!Array.isArray(warnings) || !warnings.length) return "";
    return `
      <div class="dashboard-warning-list" role="status">
        ${warnings.map((warning) => `<span>${escapeHtml(warning)}</span>`).join("")}
      </div>
    `;
  }

  function summaryGrid(data) {
    const summary = data.summary || {};
    const currency = data.costs?.currency || "USD";
    const cards = [
      ["resources", summary.total_resources, "Total resources", "Inventory across supported services"],
      ["running", summary.running_resources, "Running resources", "Currently active or healthy"],
      ["broken", summary.broken_resources, "Broken resources", "Alarms, drift, failed checks"],
      ["cost", formatMoney(summary.monthly_cost_estimate, currency), "Monthly estimate", "Projected AWS spend"],
      ["plan", summary.pending_agent_actions, "Agent next actions", "Planned or executing work"],
      ["approval", summary.pending_approvals, "Pending approvals", "Waiting for your review"],
    ];
    return `
      <section class="summary-grid summary-grid--six" aria-label="Dashboard summary">
        ${cards.map(([key, value, label, helper]) => `
          <article class="summary-card summary-card--${key}">
            <span class="summary-card__icon" aria-hidden="true">${icons[key]}</span>
            <div class="summary-card__content">
              <p class="summary-card__label">${escapeHtml(label)}</p>
              <p class="summary-card__value">${escapeHtml(value)}</p>
              <p class="summary-card__detail">${escapeHtml(helper)}</p>
            </div>
          </article>
        `).join("")}
      </section>
    `;
  }

  function panel(title, subtitle, body, className = "") {
    return `
      <section class="dashboard-panel ${className}">
        <header class="dashboard-panel__header">
          <h2>${escapeHtml(title)}</h2>
          ${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ""}
        </header>
        ${body}
      </section>
    `;
  }

  function inventorySection(resources) {
    const services = ["all", ...Array.from(new Set(resources.map((resource) => resource.service))).sort()];
    const query = state.search.trim().toLowerCase();
    const visible = resources.filter((resource) => {
      const matchesService = state.serviceFilter === "all" || resource.service === state.serviceFilter;
      const matchesQuery = !query || JSON.stringify(resource).toLowerCase().includes(query);
      return matchesService && matchesQuery;
    });
    const toolbar = `
      <div class="dashboard-toolbar">
        <label>
          <span class="sr-only">Search resources</span>
          <input class="input" type="search" value="${escapeHtml(state.search)}" placeholder="Search resources" data-dashboard-search>
        </label>
        <label>
          <span class="sr-only">Filter by service</span>
          <select class="select" data-dashboard-service-filter>
            ${services.map((service) => `<option value="${escapeHtml(service)}"${state.serviceFilter === service ? " selected" : ""}>${escapeHtml(service === "all" ? "All services" : service)}</option>`).join("")}
          </select>
        </label>
      </div>
    `;
    const rows = visible.map((resource) => `
      <tr>
        <td><strong>${escapeHtml(resource.name)}</strong><code>${escapeHtml(resource.id)}</code></td>
        <td>${escapeHtml(resource.service)}</td>
        <td>${escapeHtml(resource.type)}</td>
        <td><code>${escapeHtml(resource.region)}</code></td>
        <td>${badge(resource.status)}</td>
        <td>${badge(resource.cost_impact, "state-badge--compact")}</td>
        <td>${escapeHtml(formatDate(resource.created_at))}</td>
      </tr>
    `).join("");
    const body = `
      ${toolbar}
      <div class="dashboard-table-wrap">
        ${visible.length ? `
          <table class="dashboard-table">
            <thead><tr><th>Name</th><th>Service</th><th>Type</th><th>Region</th><th>Status</th><th>Cost Impact</th><th>Created At</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        ` : '<p class="dashboard-empty">No resources match this view.</p>'}
      </div>
    `;
    return panel("What Exists", "Resource inventory normalized across AWS services.", body, "dashboard-panel--wide");
  }

  function runningSection(items) {
    const rows = items.map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.name)}</strong><code>${escapeHtml(item.id)}</code></td>
        <td>${escapeHtml(item.service)}</td>
        <td>${badge(item.current_state)}</td>
        <td>${badge(item.health)}</td>
        <td><code>${escapeHtml(item.region)}</code></td>
      </tr>
    `).join("");
    return panel(
      "What Is Running",
      "Active services and current health.",
      `<div class="dashboard-table-wrap">${items.length ? `
        <table class="dashboard-table">
          <thead><tr><th>Resource</th><th>Service</th><th>Current State</th><th>Health</th><th>Region</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      ` : '<p class="dashboard-empty">No running resources detected.</p>'}</div>`,
    );
  }

  function brokenSection(items) {
    const rows = items.map((item) => `
      <tr>
        <td>${badge(item.severity)}</td>
        <td><strong>${escapeHtml(item.name)}</strong><code>${escapeHtml(item.id)}</code></td>
        <td>${escapeHtml(item.service)}</td>
        <td>${escapeHtml(item.problem)}</td>
        <td>${escapeHtml(item.recommended_fix)}</td>
        <td>${escapeHtml(item.source)}</td>
      </tr>
    `).join("");
    return panel(
      "What Is Broken",
      "Alarms, failed checks, degraded services, and failed deployments.",
      `<div class="dashboard-table-wrap">${items.length ? `
        <table class="dashboard-table dashboard-table--wrap">
          <thead><tr><th>Severity</th><th>Resource</th><th>Service</th><th>Problem</th><th>Recommended Fix</th><th>Source</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      ` : '<p class="dashboard-empty dashboard-empty--positive">No broken resources detected.</p>'}</div>`,
      "dashboard-panel--wide",
    );
  }

  function costSection(costs) {
    const currency = costs.currency || "USD";
    return panel(
      "What It Costs",
      "Cost Explorer trends by service and day.",
      `
        <div class="dashboard-cost-metrics">
          <div><span>Today</span><strong>${escapeHtml(formatMoney(costs.today, currency))}</strong></div>
          <div><span>Month to date</span><strong>${escapeHtml(formatMoney(costs.month_to_date, currency))}</strong></div>
          <div><span>Monthly estimate</span><strong>${escapeHtml(formatMoney(costs.monthly_estimate, currency))}</strong></div>
        </div>
        <div class="dashboard-chart-grid">
          <div>
            <h3>Cost by service</h3>
            ${serviceBars(costs.by_service || [], currency)}
          </div>
          <div>
            <h3>Daily trend</h3>
            ${dailyBars(costs.daily_trend || [], currency)}
          </div>
        </div>
      `,
      "dashboard-panel--wide",
    );
  }

  function serviceBars(items, currency) {
    if (!items.length) return '<p class="dashboard-empty">No service cost data available.</p>';
    const max = Math.max(...items.map((item) => Number(item.amount || 0)), 0.01);
    return `<ul class="dashboard-bars">${items.map((item) => `
      <li>
        <span>${escapeHtml(item.service)}</span>
        <div><i style="width: ${Math.max(4, (Number(item.amount || 0) / max) * 100).toFixed(2)}%"></i></div>
        <strong>${escapeHtml(formatMoney(item.amount, currency))}</strong>
      </li>
    `).join("")}</ul>`;
  }

  function dailyBars(items, currency) {
    if (!items.length) return '<p class="dashboard-empty">No daily trend data available.</p>';
    const max = Math.max(...items.map((item) => Number(item.amount || 0)), 0.01);
    return `
      <div class="dashboard-trend" role="img" aria-label="Daily cost trend">
        ${items.map((item) => `
          <span style="height: ${Math.max(2, (Number(item.amount || 0) / max) * 100).toFixed(2)}%" title="${escapeHtml(item.date)}: ${escapeHtml(formatMoney(item.amount, currency))}"></span>
        `).join("")}
      </div>
    `;
  }

  function agentPlanSection(items) {
    const rows = items.map((item) => `
      <tr>
        <td><strong>${escapeHtml(item.title)}</strong><code>${escapeHtml(item.plan_id)}</code></td>
        <td>${escapeHtml(titleCase(item.action_type))}</td>
        <td>${escapeHtml((item.target_services || []).join(", ") || "-")}</td>
        <td>${badge(item.risk_level)}</td>
        <td>${escapeHtml(formatMoney(item.estimated_cost, state.data?.costs?.currency))}</td>
        <td>${badge(item.status)}</td>
        <td>${escapeHtml(formatDate(item.created_at))}</td>
      </tr>
    `).join("");
    return panel(
      "What The Agent Plans Next",
      "Queued infrastructure changes.",
      `<div class="dashboard-table-wrap">${items.length ? `
        <table class="dashboard-table">
          <thead><tr><th>Plan</th><th>Action</th><th>Target Services</th><th>Risk</th><th>Estimated Cost</th><th>Status</th><th>Created At</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      ` : '<p class="dashboard-empty">No pending agent actions.</p>'}</div>`,
      "dashboard-panel--wide",
    );
  }

  function approvalsSection(items) {
    const cards = items.map((item) => `
      <article class="approval-card">
        <header>
          <div>
            <h3>${escapeHtml(item.summary || item.user_prompt || "Pending approval")}</h3>
            <p>${escapeHtml(item.user_prompt)}</p>
          </div>
          ${badge(item.risk_level)}
        </header>
        <dl>
          <div><dt>Create</dt><dd>${escapeHtml((item.services_to_create || []).join(", ") || "None")}</dd></div>
          <div><dt>Modify</dt><dd>${escapeHtml((item.services_to_modify || []).join(", ") || "None")}</dd></div>
          <div><dt>Delete</dt><dd>${escapeHtml((item.services_to_delete || []).join(", ") || "None")}</dd></div>
          <div><dt>Monthly Cost</dt><dd>${escapeHtml(formatMoney(item.estimated_monthly_cost, state.data?.costs?.currency))}</dd></div>
        </dl>
        <div class="approval-card__actions">
          <button class="button button--primary" type="button" disabled>Approve</button>
          <button class="button button--secondary" type="button" disabled>Reject</button>
          <button class="button button--secondary" type="button" disabled>Edit Plan</button>
        </div>
      </article>
    `).join("");
    return panel(
      "What Needs User Approval",
      "Plans waiting for review.",
      items.length ? `<div class="approval-grid">${cards}</div>` : '<p class="dashboard-empty dashboard-empty--positive">No plans need approval.</p>',
      "dashboard-panel--wide",
    );
  }

  function activitySection(items) {
    const rows = items.map((item) => `
      <li class="action-row">
        <span class="action-row__icon">${icons.plan}</span>
        <div class="action-row__content">
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml(item.description)}</small>
        </div>
        <span>${badge(item.status)}</span>
        <time>${escapeHtml(formatDate(item.timestamp))}</time>
      </li>
    `).join("");
    return panel(
      "Recent Activity",
      "Plans, deployments, discovered resources, warnings, and cost signals.",
      items.length ? `<ul class="action-feed dashboard-activity-feed">${rows}</ul>` : '<p class="dashboard-empty">No recent activity yet.</p>',
      "dashboard-panel--wide",
    );
  }

  async function loadDashboard() {
    state.loading = true;
    state.error = "";
    renderBody();
    try {
      state.data = await global.api.request(
        "GET",
        `/dashboard?region=${encodeURIComponent(activeRegion())}`,
      );
    } catch (error) {
      state.error = error.message || "The dashboard API request failed.";
    } finally {
      state.loading = false;
      renderBody();
    }
  }

  function mount() {
    loadDashboard();
  }

  function reloadRegion() {
    if (isMounted()) {
      loadDashboard();
    }
  }

  document.addEventListener("click", (event) => {
    if (!isMounted()) return;
    if (event.target.closest('[data-dashboard-action="retry"]')) {
      loadDashboard();
    }
  });

  document.addEventListener("input", (event) => {
    if (!isMounted()) return;
    if (event.target.matches("[data-dashboard-search]")) {
      state.search = event.target.value;
      renderBody();
      document.querySelector("[data-dashboard-search]")?.focus();
    }
  });

  document.addEventListener("change", (event) => {
    if (!isMounted()) return;
    if (event.target.matches("[data-dashboard-service-filter]")) {
      state.serviceFilter = event.target.value;
      renderBody();
    }
  });

  global.Dashboard = { render, mount, reloadRegion };
})(window);

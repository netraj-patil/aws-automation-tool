(function initializeDashboard(global) {
  "use strict";

  const ACTIONS_KEY = "agent_executions";
  const sectionLoaders = {};

  const icons = {
    ec2: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2"></rect><path d="M8 9h8M8 13h5M8 17h3"></path></svg>',
    s3: '<svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="5" rx="7" ry="3"></ellipse><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7"></path></svg>',
    rds: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16v12H4zM7 4h10v3M8 11h8M8 15h5"></path></svg>',
    iam: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="3"></circle><path d="M5 20c.5-4 2.8-6 7-6s6.5 2 7 6"></path></svg>',
    vpc: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="6" r="2"></circle><circle cx="18" cy="6" r="2"></circle><circle cx="12" cy="18" r="2"></circle><path d="m7.7 7.1 3.2 8.8M16.3 7.1l-3.2 8.8M8 6h8"></path></svg>',
    action: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m13 2-9 12h7l-1 8 9-12h-7l1-8Z"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function skeletonLines(count, className = "") {
    return Array.from(
      { length: count },
      (_, index) => `<span class="skeleton ${className}" style="--skeleton-index: ${index}"></span>`,
    ).join("");
  }

  function summarySkeleton() {
    return `
      <div class="summary-grid" aria-label="Loading resource summary">
        ${Array.from({ length: 5 }, () => `
          <article class="summary-card summary-card--loading">
            <span class="skeleton skeleton--icon"></span>
            <div>${skeletonLines(2, "skeleton--text")}</div>
          </article>
        `).join("")}
      </div>
    `;
  }

  function panelSkeleton(type) {
    if (type === "table") {
      return `
        <div class="table-skeleton">
          ${skeletonLines(1, "skeleton--heading")}
          ${Array.from({ length: 6 }, () => skeletonLines(1, "skeleton--row")).join("")}
        </div>
      `;
    }
    if (type === "actions") {
      return `<div class="actions-skeleton">${Array.from({ length: 5 }, () => `
        <div class="actions-skeleton__row">
          <span class="skeleton skeleton--icon"></span>
          ${skeletonLines(1, "skeleton--row")}
        </div>
      `).join("")}</div>`;
    }
    return `
      <div class="chart-skeleton">
        ${skeletonLines(2, "skeleton--text")}
        <span class="skeleton skeleton--chart"></span>
      </div>
    `;
  }

  function render() {
    return `
      <div class="view dashboard-view" data-view="dashboard">
        <section id="dashboard-summary" aria-live="polite">${summarySkeleton()}</section>

        <div class="dashboard-main-grid">
          <section class="dashboard-panel" id="dashboard-costs" aria-live="polite">
            ${panelSkeleton("chart")}
          </section>
          <section class="dashboard-panel" id="dashboard-ec2" aria-live="polite">
            ${panelSkeleton("table")}
          </section>
        </div>

        <section class="dashboard-panel dashboard-panel--actions" id="dashboard-actions" aria-live="polite">
          ${panelSkeleton("actions")}
        </section>
      </div>
    `;
  }

  function activeRegion() {
    return document.querySelector('[data-action="select-region"]')?.value
      || localStorage.getItem("active_aws_region")
      || "us-east-1";
  }

  function isMounted() {
    return global.router?.currentView === "dashboard";
  }

  function sectionElement(section) {
    return document.getElementById(`dashboard-${section}`);
  }

  function renderError(section, message) {
    const element = sectionElement(section);
    if (!element || !isMounted()) {
      return;
    }
    element.innerHTML = `
      <div class="dashboard-error" role="alert">
        <span class="dashboard-error__icon" aria-hidden="true">!</span>
        <div>
          <strong>Unable to load ${section === "ec2" ? "EC2 instances" : section}</strong>
          <p>${escapeHtml(message || "The request to AWS failed.")}</p>
        </div>
        <button class="button button--secondary" type="button" data-dashboard-retry="${section}">Retry</button>
      </div>
    `;
  }

  function summaryCard(service, value, label, detail = "") {
    return `
      <article class="summary-card summary-card--${service}">
        <span class="summary-card__icon">${icons[service]}</span>
        <div class="summary-card__content">
          <p class="summary-card__value">${value}</p>
          <p class="summary-card__label">${escapeHtml(label)}</p>
          ${detail ? `<p class="summary-card__detail">${detail}</p>` : ""}
        </div>
      </article>
    `;
  }

  function renderSummary(data) {
    const element = sectionElement("summary");
    if (!element || !isMounted()) {
      return;
    }
    element.innerHTML = `
      <div class="summary-grid">
        ${summaryCard(
          "ec2",
          `<span class="summary-card__running">${Number(data.ec2?.running || 0)}</span><span class="summary-card__total"> / ${Number(data.ec2?.total || 0)}</span>`,
          "EC2 Instances",
          "running / total",
        )}
        ${summaryCard("s3", Number(data.s3?.total || 0), "S3 Buckets")}
        ${summaryCard("rds", Number(data.rds?.total || 0), "RDS Instances")}
        ${summaryCard("iam", Number(data.iam?.total || 0), "IAM Users")}
        ${summaryCard("vpc", Number(data.vpc?.active || 0), "Active VPCs")}
      </div>
    `;
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
      });
    }
  }

  function costChart(daily, currency) {
    const width = 660;
    const height = 190;
    const chartTop = 10;
    const chartBottom = 150;
    const chartHeight = chartBottom - chartTop;
    const values = daily.map((item) => Number(item.amount || 0));
    const maximum = Math.max(...values, 0.01);
    const slot = width / Math.max(daily.length, 1);
    const barWidth = Math.max(4, slot - 5);
    const format = currencyFormatter(currency);

    const bars = daily.map((item, index) => {
      const value = Number(item.amount || 0);
      const barHeight = Math.max(value ? 2 : 0, (value / maximum) * chartHeight);
      const x = index * slot + (slot - barWidth) / 2;
      const y = chartBottom - barHeight;
      return `
        <rect class="cost-chart__bar" x="${x.toFixed(2)}" y="${y.toFixed(2)}"
          width="${barWidth.toFixed(2)}" height="${barHeight.toFixed(2)}" rx="2">
          <title>${escapeHtml(item.date)}: ${escapeHtml(format.format(value))}</title>
        </rect>
      `;
    }).join("");
    const ticks = daily.map((item, index) => {
      if (index % 6 !== 0 && index !== daily.length - 1) {
        return "";
      }
      const date = new Date(`${item.date}T00:00:00`);
      const label = date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      return `<text x="${(index * slot + slot / 2).toFixed(2)}" y="178" text-anchor="middle">${escapeHtml(label)}</text>`;
    }).join("");

    return `
      <svg class="cost-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Daily AWS spend for the last 30 days">
        <line x1="0" y1="${chartBottom}" x2="${width}" y2="${chartBottom}"></line>
        ${bars}
        ${ticks}
      </svg>
    `;
  }

  function renderCosts(data) {
    const element = sectionElement("costs");
    if (!element || !isMounted()) {
      return;
    }
    const delta = Number(data.delta_percent || 0);
    const direction = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
    const arrow = delta > 0 ? "\u2191" : delta < 0 ? "\u2193" : "\u2192";
    const format = currencyFormatter(data.currency);
    const daily = Array.isArray(data.daily) ? data.daily : [];

    element.innerHTML = `
      <header class="dashboard-panel__header">
        <div>
          <h2>Cost <span>(Last 30 days)</span></h2>
          <div class="cost-total">
            <strong>${escapeHtml(format.format(Number(data.total || 0)))}</strong>
            <span class="cost-delta cost-delta--${direction}">${arrow} ${Math.abs(delta).toFixed(1)}% vs last month</span>
          </div>
        </div>
      </header>
      <div class="dashboard-panel__body dashboard-panel__body--chart">
        ${daily.length ? costChart(daily, data.currency) : '<p class="dashboard-empty">No cost data is available for this period.</p>'}
      </div>
    `;
  }

  function stateClass(state) {
    if (state === "running") {
      return "success";
    }
    if (["pending", "stopping", "shutting-down", "in_progress"].includes(state)) {
      return "warning";
    }
    if (["terminated", "stopped", "failed", "error"].includes(state)) {
      return "danger";
    }
    return "neutral";
  }

  function formatLaunchTime(value) {
    if (!value) {
      return "\u2014";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function renderInstances(data) {
    const element = sectionElement("ec2");
    if (!element || !isMounted()) {
      return;
    }
    const instances = Array.isArray(data.instances) ? data.instances : [];
    const rows = instances.map((instance) => `
      <tr>
        <td>
          <strong class="instance-name" title="${escapeHtml(instance.id)}">${escapeHtml(instance.name || instance.id || "Unnamed")}</strong>
        </td>
        <td><code>${escapeHtml(instance.type || "\u2014")}</code></td>
        <td><span class="state-badge state-badge--${stateClass(instance.state)}">${escapeHtml(instance.state || "unknown")}</span></td>
        <td><code>${escapeHtml(instance.region || data.region || "\u2014")}</code></td>
        <td class="launch-time">${escapeHtml(formatLaunchTime(instance.launch_time))}</td>
      </tr>
    `).join("");

    element.innerHTML = `
      <header class="dashboard-panel__header dashboard-panel__header--inline">
        <h2>EC2 Instances</h2>
        <a href="#resource-explorer" data-route="resource-explorer">View all <span aria-hidden="true">\u2192</span></a>
      </header>
      <div class="dashboard-table-wrap">
        ${instances.length ? `
          <table class="dashboard-table">
            <thead><tr><th>Name</th><th>Type</th><th>State</th><th>Region</th><th>Launch time</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        ` : '<p class="dashboard-empty">No EC2 instances were found in this region.</p>'}
      </div>
    `;
  }

  function timeAgo(value) {
    const timestamp = new Date(value).getTime();
    if (!Number.isFinite(timestamp)) {
      return "Recently";
    }
    const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
    if (seconds < 60) return "Just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return new Date(timestamp).toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  function readActions() {
    try {
      const value = JSON.parse(localStorage.getItem(ACTIONS_KEY) || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function renderActions() {
    const element = sectionElement("actions");
    if (!element || !isMounted()) {
      return;
    }
    const actions = readActions()
      .sort((left, right) => new Date(right.timestamp || right.created_at || 0) - new Date(left.timestamp || left.created_at || 0))
      .slice(0, 5);
    const rows = actions.map((action) => {
      const status = String(action.status || action.phase || "completed").toLowerCase();
      return `
        <li class="action-row">
          <span class="action-row__icon">${icons.action}</span>
          <div class="action-row__content">
            <strong>${escapeHtml(action.summary || action.action || action.message || "AWS automation executed")}</strong>
            <small>${escapeHtml(timeAgo(action.timestamp || action.created_at || action.time))}</small>
          </div>
          <span class="state-badge state-badge--${stateClass(status === "completed" || status === "done" ? "running" : status)}">${escapeHtml(status)}</span>
        </li>
      `;
    }).join("");

    element.innerHTML = `
      <header class="dashboard-panel__header"><h2>Recent Actions</h2></header>
      <div class="dashboard-panel__body dashboard-panel__body--actions">
        ${actions.length
          ? `<ul class="action-feed">${rows}</ul>`
          : '<p class="dashboard-empty">No agent executions yet. Completed actions will appear here.</p>'}
      </div>
    `;
  }

  async function loadSummary() {
    const element = sectionElement("summary");
    if (element) element.innerHTML = summarySkeleton();
    try {
      const data = await global.api.request(
        "GET",
        `/dashboard/summary?region=${encodeURIComponent(activeRegion())}`,
      );
      renderSummary(data);
    } catch (error) {
      renderError("summary", error.message);
    }
  }

  async function loadCosts() {
    const element = sectionElement("costs");
    if (element) element.innerHTML = panelSkeleton("chart");
    try {
      renderCosts(await global.api.request("GET", "/dashboard/costs"));
    } catch (error) {
      renderError("costs", error.message);
    }
  }

  async function loadEc2() {
    const element = sectionElement("ec2");
    if (element) element.innerHTML = panelSkeleton("table");
    try {
      const data = await global.api.request(
        "GET",
        `/dashboard/ec2?region=${encodeURIComponent(activeRegion())}&limit=10`,
      );
      renderInstances(data);
    } catch (error) {
      renderError("ec2", error.message);
    }
  }

  function loadActions() {
    const element = sectionElement("actions");
    if (element) element.innerHTML = panelSkeleton("actions");
    window.setTimeout(renderActions, 80);
  }

  Object.assign(sectionLoaders, {
    summary: loadSummary,
    costs: loadCosts,
    ec2: loadEc2,
    actions: loadActions,
  });

  function mount() {
    loadSummary();
    loadCosts();
    loadEc2();
    loadActions();
  }

  function reloadRegion() {
    if (isMounted()) {
      loadSummary();
      loadEc2();
    }
  }

  document.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-dashboard-retry]");
    if (retry) {
      sectionLoaders[retry.dataset.dashboardRetry]?.();
    }
  });

  global.Dashboard = { render, mount, reloadRegion };
})(window);

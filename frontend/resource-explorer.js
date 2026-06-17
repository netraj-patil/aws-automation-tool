(function initializeResourceExplorer(global) {
  "use strict";

  const QUERY_KEY = "resource_explorer_query";
  const DEFAULT_QUERY = "*";
  const state = {
    items: [],
    searched: false,
    loading: false,
    filter: "",
    query: "",
    sort: { key: "identifier", direction: "asc" },
  };

  const icons = {
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path></svg>',
    copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function activeRegion() {
    return document.querySelector('[data-action="select-region"]')?.value
      || localStorage.getItem("active_aws_region")
      || "us-east-1";
  }

  function isMounted() {
    return global.router?.currentView === "resource-explorer";
  }

  function render() {
    return `
      <div class="view resource-view" data-view="resource-explorer">
        <section class="resource-tab-panel" id="resource-panel" aria-live="polite"></section>
      </div>
    `;
  }

  function sortValue(item, key) {
    const value = item[key];
    if (value === null || value === undefined) return "";
    if (key.includes("time") || key.includes("date") || key === "last_reported_at") {
      return new Date(value).getTime() || 0;
    }
    return typeof value === "number" ? value : String(value).toLowerCase();
  }

  function sorted(items, sort) {
    const direction = sort.direction === "asc" ? 1 : -1;
    return [...items].sort((left, right) => {
      const a = sortValue(left, sort.key);
      const b = sortValue(right, sort.key);
      if (a < b) return -1 * direction;
      if (a > b) return 1 * direction;
      return 0;
    });
  }

  function sortHeader(label, key) {
    const active = state.sort.key === key;
    const arrow = active ? (state.sort.direction === "asc" ? "\u2191" : "\u2193") : "";
    return `<th aria-sort="${active ? (state.sort.direction === "asc" ? "ascending" : "descending") : "none"}">
      <button class="sort-button" type="button" data-sort-key="${key}">
        ${escapeHtml(label)} <span aria-hidden="true">${arrow}</span>
      </button>
    </th>`;
  }

  function searchControl(placeholder, value) {
    return `<label class="resource-filter">
      <span>${icons.search}</span>
      <span class="sr-only">${escapeHtml(placeholder)}</span>
      <input type="search" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(value)}"
        data-resource-filter="results">
    </label>`;
  }

  function loadingState(label) {
    return `<div class="resource-loading">${global.Components.spinner()}<span>${escapeHtml(label)}</span></div>`;
  }

  function errorState(message) {
    return `<div class="resource-error" role="alert">
      <strong>Unable to load resources</strong>
      <p>${escapeHtml(message)}</p>
      <button class="button button--secondary" type="button" data-resource-retry="search">Retry</button>
    </div>`;
  }

  function formatDate(value) {
    if (!value) return "\u2014";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function renderPanel() {
    if (!isMounted()) return;
    const panel = document.getElementById("resource-panel");
    if (!panel) return;

    if (state.loading) {
      panel.innerHTML = loadingState("Searching AWS Resource Explorer...");
      return;
    }

    const visible = sorted(
      state.items.filter((item) => {
        const needle = state.filter.toLowerCase();
        return !needle || JSON.stringify(item).toLowerCase().includes(needle);
      }),
      state.sort,
    );
    const query = state.query || sessionStorage.getItem(QUERY_KEY) || DEFAULT_QUERY;

    panel.innerHTML = `
      <form class="resource-search-form" id="resource-search-form">
        <label>
          <span>${icons.search}</span>
          <span class="sr-only">Search AWS resources</span>
          <input id="resource-search" type="search" value="${escapeHtml(query)}"
            placeholder="Search by resource, service, tag, or ARN" autocomplete="off">
        </label>
        <button class="button button--primary" type="submit">Search</button>
      </form>
      ${state.searched ? `
        <div class="resource-toolbar">
          ${searchControl("Filter results...", state.filter)}
          <span class="resource-count">${visible.length} resource${visible.length === 1 ? "" : "s"}</span>
        </div>
        ${resourceTable(visible)}
      ` : `
        <div class="resource-initial-empty">
          <span>${icons.search}</span>
          <h2>Explore resources</h2>
          <p>Search all resources visible in the active AWS Resource Explorer view.</p>
        </div>
      `}
    `;
  }

  function resourceTable(items) {
    if (!items.length) return '<p class="resource-empty">No resources match this search.</p>';
    const rows = items.map((item) => {
      const tags = Array.isArray(item.tags) ? item.tags : [];
      const identifier = item.identifier || item.name || "Unnamed";
      const name = item.name && item.name !== identifier ? `<span class="resource-name-secondary">${escapeHtml(item.name)}</span>` : "";
      return `<tr>
        <td><strong>${escapeHtml(identifier)}</strong>${name}</td>
        <td><code>${escapeHtml(item.resource_type || item.type || "\u2014")}</code></td>
        <td><code>${escapeHtml(item.region || "global")}</code></td>
        <td><code>${escapeHtml(item.account_id || "\u2014")}</code></td>
        <td>${escapeHtml(item.service || "\u2014")}</td>
        <td>${escapeHtml(formatDate(item.last_reported_at))}</td>
        <td>
          <button class="copy-value copy-value--truncate" type="button" data-copy="${escapeHtml(item.arn || "")}"
            title="${escapeHtml(item.arn || "")}"><code>${escapeHtml(item.arn || "\u2014")}</code>${icons.copy}</button>
        </td>
        <td><div class="tag-list">
          ${tags.slice(0, 3).map((tag) => `<span class="tag-chip">${escapeHtml(tag.key)}=${escapeHtml(tag.value)}</span>`).join("")}
          ${tags.length > 3 ? `<span class="tag-more">+${tags.length - 3} more</span>` : ""}
          ${tags.length ? "" : '<span class="muted-value">\u2014</span>'}
        </div></td>
      </tr>`;
    }).join("");

    return `<div class="resource-table-wrap"><table class="resource-table">
      <thead><tr>
        ${sortHeader("Resource identifier", "identifier")}
        ${sortHeader("Resource type", "resource_type")}
        ${sortHeader("AWS Region", "region")}
        ${sortHeader("Account ID", "account_id")}
        ${sortHeader("Service", "service")}
        ${sortHeader("Last reported", "last_reported_at")}
        ${sortHeader("ARN", "arn")}
        <th>Tags</th>
      </tr></thead><tbody>${rows}</tbody>
    </table></div>`;
  }

  async function searchResources(rawQuery) {
    const query = rawQuery.trim() || DEFAULT_QUERY;
    state.loading = true;
    state.searched = true;
    state.query = query;
    sessionStorage.setItem(QUERY_KEY, query);
    renderPanel();

    try {
      const data = await global.api.request(
        "GET",
        `/resources/search?q=${encodeURIComponent(query)}&region=${encodeURIComponent(activeRegion())}`,
      );
      state.items = Array.isArray(data.resources) ? data.resources : [];
    } catch (error) {
      state.loading = false;
      const panel = document.getElementById("resource-panel");
      if (panel) panel.innerHTML = errorState(error.message);
      return;
    }

    state.loading = false;
    renderPanel();
  }

  function mount() {
    state.filter = "";
    state.query = sessionStorage.getItem(QUERY_KEY) || DEFAULT_QUERY;
    searchResources(state.query);
  }

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "resource-search-form") return;
    event.preventDefault();
    const query = event.target.querySelector("#resource-search").value;
    searchResources(query);
  });

  document.addEventListener("click", (event) => {
    const sortButton = event.target.closest("[data-sort-key]");
    if (sortButton && isMounted()) {
      const key = sortButton.dataset.sortKey;
      state.sort.direction = state.sort.key === key && state.sort.direction === "asc" ? "desc" : "asc";
      state.sort.key = key;
      renderPanel();
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton && isMounted()) {
      navigator.clipboard.writeText(copyButton.dataset.copy)
        .then(() => global.Components.toast("Copied to clipboard.", "success"))
        .catch(() => global.Components.toast("Unable to copy.", "danger"));
      return;
    }

    const retry = event.target.closest("[data-resource-retry]");
    if (retry && isMounted()) searchResources(state.query || DEFAULT_QUERY);
  });

  document.addEventListener("input", (event) => {
    if (event.target.dataset.resourceFilter !== "results" || !isMounted()) return;
    state.filter = event.target.value;
    const position = event.target.selectionStart;
    renderPanel();
    const next = document.querySelector('[data-resource-filter="results"]');
    next?.focus();
    next?.setSelectionRange(position, position);
  });

  global.ResourceExplorer = { render, mount };
})(window);

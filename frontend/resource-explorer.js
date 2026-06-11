(function initializeResourceExplorer(global) {
  "use strict";

  const QUERY_KEY = "resource_explorer_query";
  const state = {
    activeTab: "all",
    all: { items: [], searched: false, filter: "", sort: { key: "name", direction: "asc" } },
    ec2: {
      items: [], loaded: false, loading: false, filter: "", region: "", instanceState: "",
      expanded: "", sort: { key: "name", direction: "asc" },
    },
    s3: {
      items: [], loaded: false, loading: false, filter: "",
      sort: { key: "name", direction: "asc" }, bucket: "", prefix: "", objects: [], objectsLoading: false,
    },
  };

  const icons = {
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path></svg>',
    copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"></path></svg>',
    close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"></path></svg>',
    folder: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v10H3V7Z"></path></svg>',
    file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2h8l4 4v16H6V2Z"></path><path d="M14 2v5h5"></path></svg>',
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
        <nav class="resource-tabs" aria-label="Resource types">
          ${tabButton("all", "All Resources")}
          ${tabButton("ec2", "EC2")}
          ${tabButton("s3", "S3")}
        </nav>
        <section class="resource-tab-panel" id="resource-panel" aria-live="polite"></section>
        <div id="bucket-panel-root"></div>
      </div>
    `;
  }

  function tabButton(tab, label) {
    return `<button class="resource-tab${state.activeTab === tab ? " active" : ""}" type="button"
      data-resource-tab="${tab}" aria-selected="${state.activeTab === tab}">${label}</button>`;
  }

  function updateTabs() {
    document.querySelectorAll("[data-resource-tab]").forEach((button) => {
      const active = button.dataset.resourceTab === state.activeTab;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
  }

  function sortValue(item, key) {
    const value = item[key];
    if (value === null || value === undefined) return "";
    if (key.includes("time") || key.includes("date")) return new Date(value).getTime() || 0;
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

  function sortHeader(label, table, key, sort) {
    const active = sort.key === key;
    const arrow = active ? (sort.direction === "asc" ? "\u2191" : "\u2193") : "";
    return `<th aria-sort="${active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}">
      <button class="sort-button" type="button" data-sort-table="${table}" data-sort-key="${key}">
        ${escapeHtml(label)} <span aria-hidden="true">${arrow}</span>
      </button>
    </th>`;
  }

  function searchControl(placeholder, value, action) {
    return `<label class="resource-filter">
      <span>${icons.search}</span>
      <span class="sr-only">${escapeHtml(placeholder)}</span>
      <input type="search" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(value)}"
        data-resource-filter="${action}">
    </label>`;
  }

  function loadingState(label) {
    return `<div class="resource-loading">${global.Components.spinner()}<span>${escapeHtml(label)}</span></div>`;
  }

  function errorState(message, action) {
    return `<div class="resource-error" role="alert">
      <strong>Unable to load resources</strong>
      <p>${escapeHtml(message)}</p>
      <button class="button button--secondary" type="button" data-resource-retry="${action}">Retry</button>
    </div>`;
  }

  function renderPanel() {
    if (!isMounted()) return;
    updateTabs();
    if (state.activeTab === "all") renderAll();
    if (state.activeTab === "ec2") renderEc2();
    if (state.activeTab === "s3") renderS3();
  }

  function renderAll() {
    const panel = document.getElementById("resource-panel");
    const initialQuery = sessionStorage.getItem(QUERY_KEY) || "";
    const query = document.getElementById("resource-search")?.value ?? initialQuery;
    const visible = sorted(
      state.all.items.filter((item) => {
        const needle = state.all.filter.toLowerCase();
        return !needle || JSON.stringify(item).toLowerCase().includes(needle);
      }),
      state.all.sort,
    );

    panel.innerHTML = `
      <form class="resource-search-form" id="resource-search-form">
        <label>
          <span>${icons.search}</span>
          <span class="sr-only">Search AWS resources</span>
          <input id="resource-search" type="search" value="${escapeHtml(query)}"
            placeholder="Search by name, tag, or ARN" autocomplete="off">
        </label>
        <button class="button button--primary" type="submit">Search</button>
      </form>
      ${state.all.searched ? `
        <div class="resource-toolbar">
          ${searchControl("Filter these results...", state.all.filter, "all")}
          <span class="resource-count">${visible.length} resource${visible.length === 1 ? "" : "s"}</span>
        </div>
        ${allTable(visible)}
      ` : `
        <div class="resource-initial-empty">
          <span>${icons.search}</span>
          <h2>Search your AWS resources by name, tag, or ARN</h2>
          <p>Resource Explorer searches across supported services and regions.</p>
        </div>
      `}
    `;
  }

  function allTable(items) {
    if (!items.length) return '<p class="resource-empty">No resources match this search.</p>';
    const rows = items.map((item) => {
      const tags = Array.isArray(item.tags) ? item.tags : [];
      return `<tr>
        <td><strong>${escapeHtml(item.name || "Unnamed")}</strong></td>
        <td>${escapeHtml(item.type || "\u2014")}</td>
        <td><code>${escapeHtml(item.region || "Global")}</code></td>
        <td>
          <button class="copy-value copy-value--truncate" type="button" data-copy="${escapeHtml(item.arn)}"
            title="${escapeHtml(item.arn)}"><code>${escapeHtml(item.arn)}</code>${icons.copy}</button>
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
        ${sortHeader("Resource name", "all", "name", state.all.sort)}
        ${sortHeader("Type", "all", "type", state.all.sort)}
        ${sortHeader("Region", "all", "region", state.all.sort)}
        ${sortHeader("ARN", "all", "arn", state.all.sort)}
        <th>Tags</th>
      </tr></thead><tbody>${rows}</tbody>
    </table></div>`;
  }

  async function searchResources(query) {
    const panel = document.getElementById("resource-panel");
    state.all.searched = true;
    sessionStorage.setItem(QUERY_KEY, query);
    panel.innerHTML = loadingState("Searching AWS Resource Explorer...");
    try {
      const data = await global.api.request(
        "GET",
        `/resources/search?q=${encodeURIComponent(query)}&region=${encodeURIComponent(activeRegion())}`,
      );
      state.all.items = Array.isArray(data.resources) ? data.resources : [];
      renderAll();
    } catch (error) {
      panel.innerHTML = errorState(error.message, "all");
    }
  }

  function formatDate(value, withTime = false) {
    if (!value) return "\u2014";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("en-US", withTime
      ? { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }
      : { month: "short", day: "numeric", year: "numeric" });
  }

  function stateClass(value) {
    if (value === "running") return "success";
    if (["pending", "stopping", "shutting-down"].includes(value)) return "warning";
    if (["stopped", "terminated"].includes(value)) return "danger";
    return "neutral";
  }

  function renderEc2() {
    const panel = document.getElementById("resource-panel");
    if (state.ec2.loading) {
      panel.innerHTML = loadingState("Loading EC2 instances across regions...");
      return;
    }
    if (!state.ec2.loaded) {
      loadEc2();
      return;
    }
    const regions = [...new Set(state.ec2.items.map((item) => item.region))].sort();
    const states = [...new Set(state.ec2.items.map((item) => item.state))].sort();
    const needle = state.ec2.filter.toLowerCase();
    const visible = sorted(state.ec2.items.filter((item) => (
      (!needle || JSON.stringify(item).toLowerCase().includes(needle))
      && (!state.ec2.region || item.region === state.ec2.region)
      && (!state.ec2.instanceState || item.state === state.ec2.instanceState)
    )), state.ec2.sort);

    panel.innerHTML = `
      <div class="resource-toolbar resource-toolbar--filters">
        ${searchControl("Filter instances...", state.ec2.filter, "ec2")}
        <label class="resource-select"><span>Region</span><select data-ec2-select="region">
          <option value="">All regions</option>
          ${regions.map((region) => `<option value="${region}"${state.ec2.region === region ? " selected" : ""}>${region}</option>`).join("")}
        </select></label>
        <label class="resource-select"><span>State</span><select data-ec2-select="instanceState">
          <option value="">All states</option>
          ${states.map((value) => `<option value="${value}"${state.ec2.instanceState === value ? " selected" : ""}>${value}</option>`).join("")}
        </select></label>
        <span class="resource-count">${visible.length} instance${visible.length === 1 ? "" : "s"}</span>
      </div>
      ${ec2Table(visible)}
    `;
  }

  function ec2Table(items) {
    if (!items.length) return '<p class="resource-empty">No EC2 instances match these filters.</p>';
    const rows = items.map((item) => {
      const expanded = state.ec2.expanded === item.instance_id;
      return `<tr class="resource-row resource-row--clickable${expanded ? " expanded" : ""}"
          data-ec2-row="${escapeHtml(item.instance_id)}" tabindex="0" aria-expanded="${expanded}">
        <td><strong>${escapeHtml(item.name)}</strong></td>
        <td><button class="copy-value" type="button" data-copy="${escapeHtml(item.instance_id)}"><code>${escapeHtml(item.instance_id)}</code>${icons.copy}</button></td>
        <td><code>${escapeHtml(item.type || "\u2014")}</code></td>
        <td><span class="state-badge state-badge--${stateClass(item.state)}">${escapeHtml(item.state)}</span></td>
        <td><code>${escapeHtml(item.region)}</code></td>
        <td>${escapeHtml(formatDate(item.launch_time, true))}</td>
        <td><code>${escapeHtml(item.public_ip || "\u2014")}</code></td>
      </tr>
      ${expanded ? `<tr class="ec2-detail-row"><td colspan="7">${ec2Detail(item)}</td></tr>` : ""}`;
    }).join("");
    return `<div class="resource-table-wrap"><table class="resource-table">
      <thead><tr>
        ${sortHeader("Name", "ec2", "name", state.ec2.sort)}
        ${sortHeader("Instance ID", "ec2", "instance_id", state.ec2.sort)}
        ${sortHeader("Type", "ec2", "type", state.ec2.sort)}
        ${sortHeader("State", "ec2", "state", state.ec2.sort)}
        ${sortHeader("Region", "ec2", "region", state.ec2.sort)}
        ${sortHeader("Launch Time", "ec2", "launch_time", state.ec2.sort)}
        ${sortHeader("Public IP", "ec2", "public_ip", state.ec2.sort)}
      </tr></thead><tbody>${rows}</tbody>
    </table></div>`;
  }

  function ec2Detail(item) {
    const groups = item.security_groups || [];
    const tags = item.tags || [];
    return `<div class="ec2-detail">
      <dl class="detail-grid">
        <div><dt>AMI ID</dt><dd><code>${escapeHtml(item.ami_id || "\u2014")}</code></dd></div>
        <div><dt>VPC ID</dt><dd><code>${escapeHtml(item.vpc_id || "\u2014")}</code></dd></div>
        <div><dt>Key Pair</dt><dd>${escapeHtml(item.key_pair || "\u2014")}</dd></div>
        <div><dt>Security Groups</dt><dd>${groups.length
          ? groups.map((group) => `<span class="tag-chip">${escapeHtml(group.name || group.id)}</span>`).join(" ")
          : "\u2014"}</dd></div>
      </dl>
      <h3>Tags</h3>
      ${tags.length ? `<table class="detail-tags"><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody>
        ${tags.map((tag) => `<tr><td>${escapeHtml(tag.key)}</td><td>${escapeHtml(tag.value)}</td></tr>`).join("")}
      </tbody></table>` : '<p class="muted-value">No tags</p>'}
    </div>`;
  }

  async function loadEc2() {
    state.ec2.loading = true;
    renderEc2();
    try {
      const data = await global.api.request("GET", `/resources/ec2?region=${encodeURIComponent(activeRegion())}`);
      state.ec2.items = Array.isArray(data.instances) ? data.instances : [];
      state.ec2.loaded = true;
    } catch (error) {
      document.getElementById("resource-panel").innerHTML = errorState(error.message, "ec2");
      state.ec2.loading = false;
      return;
    }
    state.ec2.loading = false;
    renderEc2();
  }

  function formatBytes(value) {
    if (value === null || value === undefined) return "\u2014";
    if (value === 0) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB", "PB"];
    const unit = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / (1024 ** unit)).toFixed(unit ? 1 : 0)} ${units[unit]}`;
  }

  function renderS3() {
    const panel = document.getElementById("resource-panel");
    if (state.s3.loading) {
      panel.innerHTML = loadingState("Loading S3 buckets...");
      return;
    }
    if (!state.s3.loaded) {
      loadS3();
      return;
    }
    const needle = state.s3.filter.toLowerCase();
    const visible = sorted(
      state.s3.items.filter((item) => !needle || JSON.stringify(item).toLowerCase().includes(needle)),
      state.s3.sort,
    );
    panel.innerHTML = `
      <div class="resource-toolbar">
        ${searchControl("Filter buckets...", state.s3.filter, "s3")}
        <span class="resource-count">${visible.length} bucket${visible.length === 1 ? "" : "s"}</span>
      </div>
      ${s3Table(visible)}
    `;
    renderBucketPanel();
  }

  function s3Table(items) {
    if (!items.length) return '<p class="resource-empty">No S3 buckets match this filter.</p>';
    const rows = items.map((item) => `<tr class="resource-row resource-row--clickable"
      data-bucket-row="${escapeHtml(item.name)}" tabindex="0">
      <td><strong>${escapeHtml(item.name)}</strong></td>
      <td><code>${escapeHtml(item.region)}</code></td>
      <td>${escapeHtml(formatDate(item.creation_date))}</td>
      <td><span class="state-badge state-badge--${item.access === "public" ? "danger" : "success"}">${escapeHtml(item.access)}</span></td>
      <td>${item.object_count === null ? "\u2014" : Number(item.object_count).toLocaleString()}</td>
      <td>${formatBytes(item.size)}</td>
    </tr>`).join("");
    return `<div class="resource-table-wrap"><table class="resource-table">
      <thead><tr>
        ${sortHeader("Name", "s3", "name", state.s3.sort)}
        ${sortHeader("Region", "s3", "region", state.s3.sort)}
        ${sortHeader("Creation Date", "s3", "creation_date", state.s3.sort)}
        ${sortHeader("Access", "s3", "access", state.s3.sort)}
        ${sortHeader("Object Count", "s3", "object_count", state.s3.sort)}
        ${sortHeader("Size", "s3", "size", state.s3.sort)}
      </tr></thead><tbody>${rows}</tbody>
    </table></div>`;
  }

  async function loadS3() {
    state.s3.loading = true;
    renderS3();
    try {
      const data = await global.api.request("GET", "/resources/s3");
      state.s3.items = Array.isArray(data.buckets) ? data.buckets : [];
      state.s3.loaded = true;
    } catch (error) {
      document.getElementById("resource-panel").innerHTML = errorState(error.message, "s3");
      state.s3.loading = false;
      return;
    }
    state.s3.loading = false;
    renderS3();
  }

  function renderBucketPanel() {
    const root = document.getElementById("bucket-panel-root");
    if (!root) return;
    if (!state.s3.bucket) {
      root.innerHTML = "";
      return;
    }
    const segments = state.s3.prefix.split("/").filter(Boolean);
    let accumulated = "";
    const crumbs = [
      `<button type="button" data-object-prefix="">${escapeHtml(state.s3.bucket)}</button>`,
      ...segments.map((segment) => {
        accumulated += `${segment}/`;
        return `<span>/</span><button type="button" data-object-prefix="${escapeHtml(accumulated)}">${escapeHtml(segment)}</button>`;
      }),
    ].join("");
    const objects = state.s3.objects.map((item) => `<button class="object-row" type="button"
      ${item.type === "folder" ? `data-object-prefix="${escapeHtml(item.prefix)}"` : ""}>
      <span class="object-row__icon object-row__icon--${item.type}">${item.type === "folder" ? icons.folder : icons.file}</span>
      <span class="object-row__name">${escapeHtml(item.name)}</span>
      <span>${item.type === "file" ? formatBytes(item.size) : ""}</span>
      <span>${item.type === "file" ? escapeHtml(formatDate(item.last_modified, true)) : ""}</span>
    </button>`).join("");
    root.innerHTML = `
      <button class="bucket-panel-backdrop" type="button" data-close-bucket aria-label="Close bucket browser"></button>
      <aside class="bucket-panel" aria-label="${escapeHtml(state.s3.bucket)} objects">
        <header><div><small>S3 bucket</small><h2>${escapeHtml(state.s3.bucket)}</h2></div>
          <button class="icon-button" type="button" data-close-bucket aria-label="Close">${icons.close}</button></header>
        <nav class="object-breadcrumb" aria-label="Object path">${crumbs}</nav>
        <div class="object-browser">
          <div class="object-browser__heading"><span>Name</span><span>Size</span><span>Last modified</span></div>
          ${state.s3.objectsLoading ? loadingState("Loading objects...") : (objects || '<p class="resource-empty">This folder is empty.</p>')}
        </div>
      </aside>`;
  }

  async function openBucket(bucket, prefix = "") {
    state.s3.bucket = bucket;
    state.s3.prefix = prefix;
    state.s3.objectsLoading = true;
    renderBucketPanel();
    try {
      const data = await global.api.request(
        "GET",
        `/resources/s3/${encodeURIComponent(bucket)}/objects?prefix=${encodeURIComponent(prefix)}`,
      );
      state.s3.objects = Array.isArray(data.objects) ? data.objects : [];
    } catch (error) {
      global.Components.toast(error.message, "danger");
      state.s3.objects = [];
    }
    state.s3.objectsLoading = false;
    renderBucketPanel();
  }

  function mount() {
    state.activeTab = "all";
    renderPanel();
    const pendingQuery = sessionStorage.getItem(QUERY_KEY);
    if (pendingQuery) searchResources(pendingQuery);
  }

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "resource-search-form") return;
    event.preventDefault();
    const query = event.target.querySelector("#resource-search").value.trim();
    if (query) searchResources(query);
  });

  document.addEventListener("click", (event) => {
    const tab = event.target.closest("[data-resource-tab]");
    if (tab && isMounted()) {
      state.activeTab = tab.dataset.resourceTab;
      renderPanel();
      return;
    }

    const sortButton = event.target.closest("[data-sort-table]");
    if (sortButton && isMounted()) {
      const target = state[sortButton.dataset.sortTable];
      const key = sortButton.dataset.sortKey;
      target.sort.direction = target.sort.key === key && target.sort.direction === "asc" ? "desc" : "asc";
      target.sort.key = key;
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

    const ec2Row = event.target.closest("[data-ec2-row]");
    if (ec2Row && !event.target.closest("button")) {
      state.ec2.expanded = state.ec2.expanded === ec2Row.dataset.ec2Row ? "" : ec2Row.dataset.ec2Row;
      renderEc2();
      return;
    }

    const bucketRow = event.target.closest("[data-bucket-row]");
    if (bucketRow) {
      openBucket(bucketRow.dataset.bucketRow);
      return;
    }

    const prefix = event.target.closest("[data-object-prefix]");
    if (prefix) {
      openBucket(state.s3.bucket, prefix.dataset.objectPrefix);
      return;
    }

    if (event.target.closest("[data-close-bucket]")) {
      state.s3.bucket = "";
      state.s3.objects = [];
      renderBucketPanel();
      return;
    }

    const retry = event.target.closest("[data-resource-retry]");
    if (retry) {
      if (retry.dataset.resourceRetry === "all") renderAll();
      if (retry.dataset.resourceRetry === "ec2") loadEc2();
      if (retry.dataset.resourceRetry === "s3") loadS3();
    }
  });

  document.addEventListener("input", (event) => {
    const filter = event.target.dataset.resourceFilter;
    if (!filter || !isMounted()) return;
    state[filter].filter = event.target.value;
    const position = event.target.selectionStart;
    renderPanel();
    const next = document.querySelector(`[data-resource-filter="${filter}"]`);
    next?.focus();
    next?.setSelectionRange(position, position);
  });

  document.addEventListener("change", (event) => {
    const key = event.target.dataset.ec2Select;
    if (key && isMounted()) {
      state.ec2[key] = event.target.value;
      renderEc2();
    }
  });

  document.addEventListener("keydown", (event) => {
    const row = event.target.closest("[data-ec2-row], [data-bucket-row]");
    if (row && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      row.click();
    }
  });

  global.ResourceExplorer = { render, mount };
})(window);

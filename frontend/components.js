(function initializeComponents(global) {
  "use strict";

  const allowedTypes = new Set(["primary", "success", "warning", "danger"]);

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function normalizeType(type) {
    return allowedTypes.has(type) ? type : "primary";
  }

  function badge(text, type = "primary") {
    const safeType = normalizeType(type);
    return `<span class="badge badge--${safeType}">${escapeHtml(text)}</span>`;
  }

  function card(title, content) {
    return `
      <article class="card">
        <header class="card__header">
          <h2 class="card__title">${escapeHtml(title)}</h2>
        </header>
        <div class="card__body">${content ?? ""}</div>
      </article>
    `;
  }

  function spinner() {
    return '<span class="spinner" role="status" aria-label="Loading"></span>';
  }

  function emptyState(icon, title, subtitle) {
    return `
      <div class="empty-state">
        <span class="empty-state__icon" aria-hidden="true">${escapeHtml(icon)}</span>
        <h2 class="empty-state__title">${escapeHtml(title)}</h2>
        <p class="empty-state__subtitle">${escapeHtml(subtitle)}</p>
      </div>
    `;
  }

  function toast(message, type = "primary") {
    const region = document.getElementById("toast-region");
    if (!region) {
      return null;
    }

    const safeType = normalizeType(type);
    const icons = {
      primary: "i",
      success: "OK",
      warning: "!",
      danger: "X",
    };
    const element = document.createElement("div");

    element.className = `toast toast--${safeType}`;
    element.setAttribute("role", safeType === "danger" ? "alert" : "status");
    element.innerHTML = `
      <span class="toast__icon" aria-hidden="true">${icons[safeType]}</span>
      <span class="toast__message">${escapeHtml(message)}</span>
    `;

    region.append(element);

    window.setTimeout(() => {
      element.classList.add("toast--leaving");
      window.setTimeout(() => element.remove(), 180);
    }, 3000);

    return element;
  }

  global.Components = {
    badge,
    card,
    spinner,
    emptyState,
    toast,
  };
})(window);

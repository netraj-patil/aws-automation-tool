(function initializeLayout(global) {
  "use strict";

  const ACTIVE_PROFILE_KEY = "active_aws_profile";
  const PROFILES_KEY = "aws_profiles";
  const USER_KEY = "auth_user";
  const GUEST_CREDENTIALS_KEY = "guest_aws_credentials";
  const SIDEBAR_COLLAPSED_KEY = "sidebar_collapsed";

  const viewTitles = {
    dashboard: "Dashboard",
    chat: "Chat",
    "resource-explorer": "Resource Explorer",
    profile: "Profile",
    "audit-log": "Audit Log",
    settings: "Settings",
  };

  const icons = {
    logo: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 7.5 12 4l5 3.5v6L12 17l-5-3.5v-6Z"></path><path d="m7 13.5-3 2L12 21l8-5.5-3-2"></path></svg>',
    dashboard: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1"></rect><rect x="14" y="3" width="7" height="7" rx="1"></rect><rect x="3" y="14" width="7" height="7" rx="1"></rect><rect x="14" y="14" width="7" height="7" rx="1"></rect></svg>',
    chat: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4v8Z"></path><path d="M8 9h8M8 13h5"></path></svg>',
    resources: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 2 9 5-9 5-9-5 9-5Z"></path><path d="m3 12 9 5 9-5M3 17l9 5 9-5"></path></svg>',
    audit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-4"></path><rect x="9" y="3" width="6" height="4" rx="1"></rect><path d="m8 14 2 2 5-5"></path></svg>',
    settings: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.88-.34A1.7 1.7 0 0 0 14 20.92V21h-4v-.08A1.7 1.7 0 0 0 8.96 19.4a1.7 1.7 0 0 0-1.88.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.6 15 1.7 1.7 0 0 0 3.08 14H3v-4h.08A1.7 1.7 0 0 0 4.6 8.96a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 8.96 4.6 1.7 1.7 0 0 0 10 3.08V3h4v.08a1.7 1.7 0 0 0 1.03 1.53 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.83 2.83-.06.06a1.7 1.7 0 0 0-.34 1.88A1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z"></path></svg>',
    profile: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="8" r="4"></circle><path d="M4 21a8 8 0 0 1 16 0"></path></svg>',
    collapse: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 7-5 5 5 5"></path></svg>',
    search: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-4-4"></path></svg>',
    bell: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path><path d="M10 21h4"></path></svg>',
    logout: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10 17l5-5-5-5M15 12H3"></path><path d="M14 3h5a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-5"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function readJson(storage, key) {
    try {
      return JSON.parse(storage.getItem(key) || "null");
    } catch {
      return null;
    }
  }

  function getActiveProfile() {
    const storedProfile = readJson(localStorage, ACTIVE_PROFILE_KEY);
    if (storedProfile && typeof storedProfile === "object") {
      return storedProfile;
    }

    const activeName = localStorage.getItem(ACTIVE_PROFILE_KEY);
    const profiles = readJson(localStorage, PROFILES_KEY);
    if (activeName && profiles) {
      if (Array.isArray(profiles)) {
        const match = profiles.find((profile) => profile?.name === activeName);
        if (match) {
          return match;
        }
      } else if (profiles[activeName]) {
        return { name: activeName, ...profiles[activeName] };
      }
    }

    const guestCredentials = readJson(sessionStorage, GUEST_CREDENTIALS_KEY);
    if (guestCredentials) {
      return {
        name: "Temporary profile",
        accessKeyId: guestCredentials.aws_access_key_id,
        region: guestCredentials.region,
      };
    }

    return {
      name: "Default profile",
      accessKeyId: "",
      region: localStorage.getItem("active_aws_region") || "us-east-1",
    };
  }

  function getUser() {
    const user = readJson(localStorage, USER_KEY);
    if (user) {
      return user;
    }
    const isGuest = Boolean(sessionStorage.getItem(GUEST_CREDENTIALS_KEY));
    return {
      name: isGuest ? "Guest User" : "AWS User",
      email: isGuest ? "Temporary session" : "",
    };
  }

  function getInitials(name) {
    const initials = String(name || "AWS User")
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part[0])
      .join("");
    return initials.toUpperCase() || "AU";
  }

  function getAvatarHue(value) {
    return Array.from(String(value || "AWS"))
      .reduce((total, character) => total + character.charCodeAt(0), 0) % 360;
  }

  function maskAccessKey(accessKey) {
    const value = String(accessKey || "");
    if (!value) {
      return "No access key";
    }
    const prefix = value.startsWith("AKIA") ? "AKIA" : value.slice(0, 4);
    return `${prefix}...${value.slice(-4).padStart(4, "X")}`;
  }

  function navItem(view, label, icon, activeView, options = {}) {
    const active = view === activeView;
    const disabled = Boolean(options.disabled);
    const classes = [
      "app-nav__item",
      active ? "active" : "",
      disabled ? "app-nav__item--disabled" : "",
    ].filter(Boolean).join(" ");
    const routeAttributes = disabled
      ? 'aria-disabled="true" tabindex="-1"'
      : `href="#${view}" data-route="${view}"${active ? ' aria-current="page"' : ""}`;

    return `
      <a class="${classes}" ${routeAttributes} aria-label="${escapeHtml(label)}">
        <span class="app-nav__indicator" aria-hidden="true"></span>
        <span class="app-nav__icon">${icon}</span>
        <span class="app-nav__label">${escapeHtml(label)}</span>
        ${options.badge ? `<span class="app-nav__badge">${escapeHtml(options.badge)}</span>` : ""}
      </a>
    `;
  }

  function renderLayout(viewName, contentHTML) {
    const profile = getActiveProfile();
    const user = getUser();
    const profileName = profile.name
      || profile.profileName
      || profile.profile_name
      || "Default profile";
    const accessKey = profile.accessKeyId
      || profile.aws_access_key_id
      || profile.access_key_id
      || "";
    const region = profile.region || profile.aws_region || "us-east-1";
    const userName = user.name || user.full_name || "AWS User";
    const userEmail = user.email || "";
    const avatarHue = getAvatarHue(userEmail || userName);
    const isCollapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
    const title = viewTitles[viewName] || "AWS Automation";
    const regions = [
      "us-east-1",
      "us-east-2",
      "us-west-1",
      "us-west-2",
      "ap-south-1",
      "ap-southeast-1",
      "eu-west-1",
      "eu-central-1",
    ];

    return `
      <div class="app-layout${isCollapsed ? " app-layout--collapsed" : ""}" data-view="${escapeHtml(viewName)}">
        <aside class="app-sidebar" aria-label="Main navigation">
          <div class="app-sidebar__brand-row">
            <a class="app-brand" href="#dashboard" data-route="dashboard" aria-label="AWS Automation home">
              <span class="app-brand__mark">${icons.logo}</span>
              <span class="app-brand__name">AWS Automate</span>
            </a>
            <button class="icon-button app-sidebar__toggle" type="button" data-action="toggle-sidebar" aria-label="${isCollapsed ? "Expand" : "Collapse"} sidebar">
              ${icons.collapse}
            </button>
          </div>

          <nav class="app-nav" aria-label="Workspace">
            <p class="app-sidebar__section-label">Workspace</p>
            ${navItem("dashboard", "Dashboard", icons.dashboard, viewName)}
            ${navItem("chat", "Chat", icons.chat, viewName)}
            ${navItem("resource-explorer", "Resource Explorer", icons.resources, viewName)}
            ${navItem("profile", "Profile", icons.profile, viewName)}
            ${navItem("audit-log", "Audit Log", icons.audit, viewName, { disabled: true, badge: "Coming soon" })}
            ${navItem("settings", "Settings", icons.settings, viewName, { disabled: true })}
          </nav>

          <section class="profile-card" aria-label="Active AWS credential profile">
            <p class="app-sidebar__section-label">Active profile</p>
            <div class="profile-card__details">
              <strong title="${escapeHtml(profileName)}">${escapeHtml(profileName)}</strong>
              <code>${escapeHtml(maskAccessKey(accessKey))}</code>
            </div>
            <button class="profile-card__switch" type="button" data-action="switch-profile">Switch profile</button>
          </section>

          <div class="app-user">
            <span class="app-user__avatar" style="--avatar-hue: ${avatarHue}" aria-hidden="true">${escapeHtml(getInitials(userName))}</span>
            <span class="app-user__details">
              <strong title="${escapeHtml(userName)}">${escapeHtml(userName)}</strong>
              <small title="${escapeHtml(userEmail)}">${escapeHtml(userEmail)}</small>
            </span>
            <button class="icon-button app-user__logout" id="logout-button" type="button" data-action="logout" aria-label="Log out">
              ${icons.logout}
            </button>
          </div>
        </aside>

        <div class="app-workspace">
          <header class="app-header">
            <h1 class="app-header__title">${escapeHtml(title)}</h1>
            <label class="global-search">
              <span class="global-search__icon">${icons.search}</span>
              <span class="sr-only">Search resources</span>
              <input type="search" placeholder="Search resources..." aria-label="Search resources"
                data-action="global-resource-search"
                value="${escapeHtml(sessionStorage.getItem("resource_explorer_query") || "")}">
            </label>
            <div class="app-header__actions">
              <button class="icon-button notification-button" type="button" aria-label="Notifications">
                ${icons.bell}
                <span class="notification-button__dot" aria-hidden="true"></span>
              </button>
              <label class="region-select">
                <span class="sr-only">AWS region</span>
                <select data-action="select-region" aria-label="AWS region">
                  ${regions.map((item) => `
                    <option value="${item}"${item === region ? " selected" : ""}>${item}</option>
                  `).join("")}
                </select>
              </label>
            </div>
          </header>

          <main class="app-content" id="main-content">
            ${contentHTML ?? ""}
          </main>
        </div>
      </div>
    `;
  }

  global.renderLayout = renderLayout;
})(window);

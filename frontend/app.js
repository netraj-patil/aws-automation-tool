(function initializeApp(global) {
  "use strict";

  const BASE_URL = "http://localhost:8000/api/v1";
  const TOKEN_KEY = "jwt_token";
  const USER_KEY = "auth_user";
  const GUEST_CREDENTIALS_KEY = "guest_aws_credentials";
  const PUBLIC_VIEWS = new Set(["login", "register", "guest"]);
  const DEFAULT_AUTHENTICATED_VIEW = "dashboard";
  const DEFAULT_PUBLIC_VIEW = "login";

  const auth = {
    getToken() {
      return localStorage.getItem(TOKEN_KEY);
    },

    setToken(token, user) {
      localStorage.setItem(TOKEN_KEY, token);
      if (user) {
        localStorage.setItem(USER_KEY, JSON.stringify(user));
      }
      sessionStorage.removeItem(GUEST_CREDENTIALS_KEY);
    },

    removeToken() {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      sessionStorage.removeItem(GUEST_CREDENTIALS_KEY);
    },

    getUser() {
      try {
        return JSON.parse(localStorage.getItem(USER_KEY) || "null");
      } catch {
        return null;
      }
    },

    setGuestCredentials(credentials) {
      sessionStorage.setItem(GUEST_CREDENTIALS_KEY, JSON.stringify(credentials));
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    },

    getGuestCredentials() {
      try {
        return JSON.parse(sessionStorage.getItem(GUEST_CREDENTIALS_KEY) || "null");
      } catch {
        return null;
      }
    },

    getActiveAwsProfile() {
      try {
        const profile = JSON.parse(
          localStorage.getItem("active_aws_profile") || "null",
        );
        return profile && typeof profile === "object" ? profile : null;
      } catch {
        return null;
      }
    },

    isGuest() {
      return Boolean(this.getGuestCredentials());
    },

    isLoggedIn() {
      return Boolean(this.getToken()) || this.isGuest();
    },
  };

  function getErrorMessage(data, status) {
    if (typeof data === "string" && data.trim()) {
      return data;
    }

    if (typeof data?.detail === "string") {
      return data.detail;
    }

    if (typeof data?.detail?.detail === "string") {
      return data.detail.detail;
    }

    if (typeof data?.detail?.message === "string") {
      return data.detail.message;
    }

    if (typeof data?.detail?.error === "string") {
      return data.detail.error;
    }

    if (typeof data?.message === "string") {
      return data.message;
    }

    if (typeof data?.error === "string") {
      return data.error;
    }

    return `Request failed with status ${status}`;
  }

  const api = {
    async request(method, path, body) {
      const headers = {
        Accept: "application/json",
      };
      const token = auth.getToken();
      const guestCredentials = auth.getGuestCredentials();
      const awsCredentials = guestCredentials || auth.getActiveAwsProfile();
      const options = {
        method: method.toUpperCase(),
        headers,
      };

      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      if (awsCredentials) {
        const accessKey = awsCredentials.aws_access_key_id
          || awsCredentials.accessKeyId
          || awsCredentials.access_key_id;
        const secretKey = awsCredentials.aws_secret_access_key
          || awsCredentials.secretAccessKey
          || awsCredentials.secret_access_key;
        const sessionToken = awsCredentials.aws_session_token
          || awsCredentials.sessionToken;
        if (accessKey && secretKey) {
          headers["X-AWS-Access-Key-Id"] = accessKey;
          headers["X-AWS-Secret-Access-Key"] = secretKey;
        }
        if (sessionToken) {
          headers["X-AWS-Session-Token"] = sessionToken;
        }
      }

      if (body !== undefined && body !== null) {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
      }

      const normalizedPath = path.startsWith("/") ? path : `/${path}`;
      const response = await fetch(`${BASE_URL}${normalizedPath}`, options);
      const contentType = response.headers.get("content-type") || "";
      const data = contentType.includes("application/json")
        ? await response.json()
        : await response.text();

      if (!response.ok) {
        const error = new Error(getErrorMessage(data, response.status));
        error.status = response.status;
        error.data = data;
        throw error;
      }

      return data;
    },
  };

  function logoMarkup() {
    return `
      <div class="auth-brand">
        <span class="auth-brand__mark" aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="M7 7.5 12 4l5 3.5v6L12 17l-5-3.5v-6Z"></path>
            <path d="m7 13.5-3 2L12 21l8-5.5-3-2"></path>
          </svg>
        </span>
        <h1>AWS Automation Tool</h1>
        <p>Manage your infrastructure with AI</p>
      </div>
    `;
  }

  function passwordField(id, label, autocomplete, placeholder) {
    return `
      <div class="field" data-field="${id}">
        <label class="field__label" for="${id}">${label}</label>
        <div class="password-input">
          <input
            class="input"
            id="${id}"
            name="${id}"
            type="password"
            autocomplete="${autocomplete}"
            placeholder="${placeholder}"
            aria-describedby="${id}-error"
          >
          <button
            class="password-toggle"
            type="button"
            data-password-toggle="${id}"
            aria-label="Show ${label.toLowerCase()}"
            aria-pressed="false"
          >
            <svg class="eye-icon" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path>
              <circle cx="12" cy="12" r="2.5"></circle>
            </svg>
          </button>
        </div>
        <p class="field-error" id="${id}-error"></p>
      </div>
    `;
  }

  function renderLogin() {
    return `
      <div class="view view--auth" data-view="login">
        <article class="auth-card">
          ${logoMarkup()}
          <form class="auth-form" id="login-form" novalidate>
            <div class="field" data-field="login-email">
              <label class="field__label" for="login-email">Email</label>
              <input
                class="input"
                id="login-email"
                name="email"
                type="email"
                autocomplete="email"
                placeholder="you@example.com"
                aria-describedby="login-email-error"
              >
              <p class="field-error" id="login-email-error"></p>
            </div>

            ${passwordField("login-password", "Password", "current-password", "Enter your password")}

            <button class="button button--primary button--full" type="submit">
              <span class="button__label">Sign in</span>
            </button>
            <p class="form-error" data-form-error role="alert"></p>
          </form>

          <p class="auth-switch">
            Don't have an account?
            <a href="#register" data-route="register">Register</a>
          </p>

          <div class="auth-divider"><span>or continue with</span></div>

          <a class="guest-link" href="#guest" data-route="guest">
            <span class="guest-link__icon" aria-hidden="true">key</span>
            <span>
              <strong>Use temporary credentials</strong>
              <small>Paste AWS keys for this browser session</small>
            </span>
            <span aria-hidden="true">-&gt;</span>
          </a>
        </article>
      </div>
    `;
  }

  function renderRegister() {
    return `
      <div class="view view--auth" data-view="register">
        <article class="auth-card">
          ${logoMarkup()}
          <form class="auth-form" id="register-form" novalidate>
            <div class="field" data-field="register-name">
              <label class="field__label" for="register-name">Full name</label>
              <input
                class="input"
                id="register-name"
                name="name"
                type="text"
                autocomplete="name"
                placeholder="Your full name"
                aria-describedby="register-name-error"
              >
              <p class="field-error" id="register-name-error"></p>
            </div>

            <div class="field" data-field="register-email">
              <label class="field__label" for="register-email">Email</label>
              <input
                class="input"
                id="register-email"
                name="email"
                type="email"
                autocomplete="email"
                placeholder="you@example.com"
                aria-describedby="register-email-error"
              >
              <p class="field-error" id="register-email-error"></p>
            </div>

            ${passwordField("register-password", "Password", "new-password", "At least 8 characters")}
            ${passwordField("register-confirm-password", "Confirm password", "new-password", "Enter your password again")}

            <button class="button button--primary button--full" type="submit">
              <span class="button__label">Create account</span>
            </button>
            <p class="form-error" data-form-error role="alert"></p>
          </form>

          <p class="auth-switch">
            Already have an account?
            <a href="#login" data-route="login">Sign in</a>
          </p>
        </article>
      </div>
    `;
  }

  function renderGuest() {
    return `
      <div class="view view--auth" data-view="guest">
        <article class="auth-card">
          ${logoMarkup()}
          <div class="auth-card__intro">
            <span class="badge badge--warning">Demo mode</span>
            <h2>Use temporary AWS credentials</h2>
            <p>Credentials stay in this browser tab and are cleared when you sign out or close the session.</p>
          </div>

          <form class="auth-form" id="guest-form" novalidate>
            <div class="field" data-field="guest-access-key">
              <label class="field__label" for="guest-access-key">AWS access key ID</label>
              <input
                class="input resource-value"
                id="guest-access-key"
                name="aws_access_key_id"
                type="text"
                autocomplete="off"
                placeholder="AKIA..."
                aria-describedby="guest-access-key-error"
              >
              <p class="field-error" id="guest-access-key-error"></p>
            </div>

            ${passwordField("guest-secret-key", "AWS secret access key", "off", "Enter secret access key")}

            <div class="field" data-field="guest-region">
              <label class="field__label" for="guest-region">AWS region</label>
              <select class="select resource-value" id="guest-region" name="region">
                <option value="us-east-1">us-east-1</option>
                <option value="us-east-2">us-east-2</option>
                <option value="us-west-1">us-west-1</option>
                <option value="us-west-2">us-west-2</option>
                <option value="ap-south-1">ap-south-1</option>
                <option value="ap-southeast-1">ap-southeast-1</option>
                <option value="eu-west-1">eu-west-1</option>
                <option value="eu-central-1">eu-central-1</option>
              </select>
              <p class="field-error" id="guest-region-error"></p>
            </div>

            <button class="button button--primary button--full" type="submit">
              <span class="button__label">Continue in demo mode</span>
            </button>
            <p class="form-error" data-form-error role="alert"></p>
          </form>

          <p class="auth-switch">
            Prefer an account?
            <a href="#login" data-route="login">Back to sign in</a>
          </p>
        </article>
      </div>
    `;
  }

  function renderPlaceholder(view, title, subtitle, icon) {
    return `
      <div class="view view-placeholder" data-view="${view}">
        <div class="view-placeholder__content">
          <span class="view-placeholder__icon" aria-hidden="true">${icon}</span>
          <h2>${title}</h2>
          <p>${subtitle}</p>
        </div>
      </div>
    `;
  }

  function renderDashboard() {
    return global.Dashboard.render();
  }

  function renderChat() {
    return global.Chat.render();
  }

  function renderResourceExplorer() {
    return global.ResourceExplorer.render();
  }

  function renderProfile() {
    return global.Profile.render();
  }

  const viewTitles = {
    login: "Sign in",
    register: "Create account",
    guest: "Temporary credentials",
    dashboard: "Dashboard",
    chat: "Automation chat",
    "resource-explorer": "Resource explorer",
    profile: "Profile",
  };

  const router = {
    routes: {
      login: renderLogin,
      register: renderRegister,
      guest: renderGuest,
      dashboard: renderDashboard,
      chat: renderChat,
      "resource-explorer": renderResourceExplorer,
      profile: renderProfile,
    },

    currentView: null,

    resolve(view) {
      return Object.hasOwn(this.routes, view) ? view : null;
    },

    render(view) {
      const resolvedView = this.resolve(view);
      if (!resolvedView) {
        navigate(auth.isLoggedIn() ? DEFAULT_AUTHENTICATED_VIEW : DEFAULT_PUBLIC_VIEW, true);
        return;
      }

      if (!PUBLIC_VIEWS.has(resolvedView) && !auth.isLoggedIn()) {
        navigate(DEFAULT_PUBLIC_VIEW, true);
        return;
      }

      if (PUBLIC_VIEWS.has(resolvedView) && auth.isLoggedIn()) {
        navigate(DEFAULT_AUTHENTICATED_VIEW, true);
        return;
      }

      const app = document.getElementById("app");
      const isPublic = PUBLIC_VIEWS.has(resolvedView);
      const content = this.routes[resolvedView]();

      this.currentView = resolvedView;
      app.innerHTML = isPublic
        ? `
          <div class="app-shell app-shell--auth">
            <main class="main">
              <section class="view-container">${content}</section>
            </main>
          </div>
        `
        : global.renderLayout(resolvedView, content);
      document.title = `${viewTitles[resolvedView]} | AWS Automation Tool`;
      if (resolvedView === "dashboard") {
        global.Dashboard.mount();
      } else if (resolvedView === "chat") {
        global.Chat.mount();
      } else if (resolvedView === "resource-explorer") {
        global.ResourceExplorer.mount();
      } else if (resolvedView === "profile") {
        global.Profile.mount();
      }
    },
  };

  function navigate(view, replace = false) {
    const targetView = router.resolve(view)
      || (auth.isLoggedIn() ? DEFAULT_AUTHENTICATED_VIEW : DEFAULT_PUBLIC_VIEW);
    const targetHash = `#${targetView}`;

    if (window.location.hash === targetHash) {
      router.render(targetView);
      return;
    }

    if (replace) {
      history.replaceState({ view: targetView }, "", targetHash);
      router.render(targetView);
    } else {
      window.location.hash = targetView;
    }
  }

  function getViewFromHash() {
    return window.location.hash.slice(1).trim();
  }

  function setFieldError(inputId, message) {
    const input = document.getElementById(inputId);
    const error = document.getElementById(`${inputId}-error`);
    const field = input?.closest(".field");

    if (error) {
      error.textContent = message;
    }
    if (input) {
      input.setAttribute("aria-invalid", message ? "true" : "false");
    }
    field?.classList.toggle("field--invalid", Boolean(message));
  }

  function clearFormErrors(form) {
    form.querySelectorAll(".field-error").forEach((error) => {
      error.textContent = "";
    });
    form.querySelectorAll(".field--invalid").forEach((field) => {
      field.classList.remove("field--invalid");
    });
    form.querySelectorAll("[aria-invalid]").forEach((input) => {
      input.setAttribute("aria-invalid", "false");
    });
    const formError = form.querySelector("[data-form-error]");
    if (formError) {
      formError.textContent = "";
    }
  }

  function setFormError(form, message) {
    const formError = form.querySelector("[data-form-error]");
    if (formError) {
      formError.textContent = message;
    }
  }

  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }

  function setSubmitting(form, isSubmitting) {
    const button = form.querySelector('button[type="submit"]');
    const label = button?.querySelector(".button__label");

    if (!button || !label) {
      return;
    }

    if (isSubmitting) {
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      label.dataset.originalText = label.textContent;
      label.textContent = "Please wait";
      button.insertAdjacentHTML("afterbegin", global.Components.spinner());
    } else {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.querySelector(".spinner")?.remove();
      label.textContent = label.dataset.originalText || label.textContent;
    }
  }

  function normalizeAuthResponse(data, fallbackUser) {
    const token = data?.access_token || data?.token || data?.jwt;
    const sourceUser = data?.user || data?.account || fallbackUser;
    const user = {
      id: sourceUser?.id || sourceUser?.user_id || null,
      name: sourceUser?.name || sourceUser?.full_name || fallbackUser?.name || "",
      email: sourceUser?.email || fallbackUser?.email || "",
    };
    return { token, user };
  }

  async function handleLogin(form) {
    clearFormErrors(form);
    const email = form.elements.email.value.trim();
    const password = form.elements["login-password"].value;
    let valid = true;

    if (!isValidEmail(email)) {
      setFieldError("login-email", "Enter a valid email address.");
      valid = false;
    }
    if (!password) {
      setFieldError("login-password", "Enter your password.");
      valid = false;
    }
    if (!valid) {
      return;
    }

    setSubmitting(form, true);
    try {
      const data = await api.request("POST", "/auth/login", { email, password });
      const session = normalizeAuthResponse(data, { email });
      if (!session.token) {
        throw new Error("The server did not return an authentication token.");
      }
      auth.setToken(session.token, session.user);
      navigate("dashboard");
    } catch (error) {
      setFormError(form, error.message || "Unable to sign in.");
    } finally {
      setSubmitting(form, false);
    }
  }

  async function handleRegister(form) {
    clearFormErrors(form);
    const name = form.elements.name.value.trim();
    const email = form.elements.email.value.trim();
    const password = form.elements["register-password"].value;
    const confirmPassword = form.elements["register-confirm-password"].value;
    let valid = true;

    if (!name) {
      setFieldError("register-name", "Enter your full name.");
      valid = false;
    }
    if (!isValidEmail(email)) {
      setFieldError("register-email", "Enter a valid email address.");
      valid = false;
    }
    if (password.length < 8) {
      setFieldError("register-password", "Password must be at least 8 characters.");
      valid = false;
    }
    if (!confirmPassword) {
      setFieldError("register-confirm-password", "Confirm your password.");
      valid = false;
    } else if (confirmPassword !== password) {
      setFieldError("register-confirm-password", "Passwords do not match.");
      valid = false;
    }
    if (!valid) {
      return;
    }

    setSubmitting(form, true);
    try {
      const data = await api.request("POST", "/auth/register", {
        name,
        email,
        password,
      });
      const session = normalizeAuthResponse(data, { name, email });
      if (session.token) {
        auth.setToken(session.token, session.user);
        navigate("dashboard");
      } else {
        global.Components.toast("Account created. You can now sign in.", "success");
        navigate("login");
      }
    } catch (error) {
      setFormError(form, error.message || "Unable to create your account.");
    } finally {
      setSubmitting(form, false);
    }
  }

  function handleGuest(form) {
    clearFormErrors(form);
    const accessKey = form.elements.aws_access_key_id.value.trim();
    const secretKey = form.elements["guest-secret-key"].value.trim();
    const region = form.elements.region.value;
    let valid = true;

    if (!accessKey) {
      setFieldError("guest-access-key", "Enter an AWS access key ID.");
      valid = false;
    }
    if (!secretKey) {
      setFieldError("guest-secret-key", "Enter an AWS secret access key.");
      valid = false;
    }
    if (!region) {
      setFieldError("guest-region", "Select an AWS region.");
      valid = false;
    }
    if (!valid) {
      return;
    }

    auth.setGuestCredentials({
      aws_access_key_id: accessKey,
      aws_secret_access_key: secretKey,
      region,
    });
    global.Components.toast("Temporary credentials saved for this session.", "success");
    navigate("dashboard");
  }

  function handleRouteChange() {
    const requestedView = getViewFromHash();
    router.render(
      requestedView
      || (auth.isLoggedIn() ? DEFAULT_AUTHENTICATED_VIEW : DEFAULT_PUBLIC_VIEW),
    );
  }

  function bindEvents() {
    document.addEventListener("click", (event) => {
      const routeLink = event.target.closest("[data-route]");
      if (routeLink) {
        event.preventDefault();
        navigate(routeLink.dataset.route);
        return;
      }

      const action = event.target.closest("[data-action]")?.dataset.action;
      if (action === "logout") {
        auth.removeToken();
        navigate(DEFAULT_PUBLIC_VIEW, true);
        return;
      }

      if (action === "toggle-sidebar") {
        const layout = document.querySelector(".app-layout");
        const isCollapsed = layout?.classList.toggle("app-layout--collapsed");
        localStorage.setItem("sidebar_collapsed", String(Boolean(isCollapsed)));
        return;
      }

      if (action === "switch-profile") {
        navigate("profile");
        return;
      }

      const passwordToggle = event.target.closest("[data-password-toggle]");
      if (passwordToggle) {
        const input = document.getElementById(passwordToggle.dataset.passwordToggle);
        if (!input) {
          return;
        }
        const showPassword = input.type === "password";
        input.type = showPassword ? "text" : "password";
        passwordToggle.classList.toggle("password-toggle--visible", showPassword);
        passwordToggle.setAttribute("aria-pressed", String(showPassword));
        passwordToggle.setAttribute(
          "aria-label",
          `${showPassword ? "Hide" : "Show"} ${input.closest(".field")?.querySelector("label")?.textContent.toLowerCase() || "password"}`,
        );
      }
    });

    document.addEventListener("input", (event) => {
      if (event.target.matches(".input, .select")) {
        setFieldError(event.target.id, "");
        const formError = event.target.form?.querySelector("[data-form-error]");
        if (formError) {
          formError.textContent = "";
        }
      }
    });

    document.addEventListener("submit", (event) => {
      event.preventDefault();
      if (event.target.id === "login-form") {
        handleLogin(event.target);
      } else if (event.target.id === "register-form") {
        handleRegister(event.target);
      } else if (event.target.id === "guest-form") {
        handleGuest(event.target);
      }
    });

    document.addEventListener("change", (event) => {
      if (event.target.matches('[data-action="select-region"]')) {
        localStorage.setItem("active_aws_region", event.target.value);
        global.Dashboard.reloadRegion();
      }
    });

    document.addEventListener("keydown", (event) => {
      if (!event.target.matches('[data-action="global-resource-search"]') || event.key !== "Enter") {
        return;
      }
      const query = event.target.value.trim();
      if (!query) {
        return;
      }
      sessionStorage.setItem("resource_explorer_query", query);
      navigate("resource-explorer");
    });

    window.addEventListener("hashchange", handleRouteChange);
    window.addEventListener("popstate", handleRouteChange);
  }

  function start() {
    bindEvents();
    const initialView = getViewFromHash();
    if (!initialView) {
      navigate(auth.isLoggedIn() ? DEFAULT_AUTHENTICATED_VIEW : DEFAULT_PUBLIC_VIEW, true);
      return;
    }
    router.render(initialView);
  }

  global.router = router;
  global.auth = auth;
  global.api = api;
  global.navigate = navigate;

  start();
})(window);

(function initializeProfile(global) {
  "use strict";

  const USER_KEY = "auth_user";
  const PROFILES_KEY = "aws_profiles";
  const ACTIVE_PROFILE_KEY = "active_aws_profile";
  const REGIONS = [
    "ap-south-1",
    "us-east-1",
    "us-west-2",
    "eu-west-1",
    "ap-southeast-1",
  ];

  const state = {
    accountEditing: false,
    passwordOpen: false,
    addProfileOpen: false,
    expandedProfileId: null,
    deleteProfileId: null,
  };

  const icons = {
    chevron: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"></path></svg>',
    edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m4 20 4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z"></path><path d="m13.5 8 3 3"></path></svg>',
    eye: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"></path><circle cx="12" cy="12" r="2.5"></circle></svg>',
    plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg>',
    shield: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 5 6v5c0 4.6 2.8 8 7 10 4.2-2 7-5.4 7-10V6l-7-3Z"></path><path d="m9 12 2 2 4-4"></path></svg>',
    star: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-2.9-5.6 2.9 1.1-6.2L3 9.6l6.2-.9L12 3Z"></path></svg>',
    trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function readJson(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || "null");
      return value ?? fallback;
    } catch {
      return fallback;
    }
  }

  function getUser() {
    const user = readJson(USER_KEY, {}) || {};
    if (!user.joined_at && !user.created_at) {
      user.joined_at = new Date().toISOString();
      localStorage.setItem(USER_KEY, JSON.stringify(user));
    }
    return {
      ...user,
      name: user.name || user.full_name || "AWS User",
      email: user.email || "",
      joinedAt: user.joined_at || user.created_at,
    };
  }

  function activeProfileName() {
    const active = readJson(ACTIVE_PROFILE_KEY, null);
    if (active && typeof active === "object") {
      return active.name || active.profileName || active.profile_name || "";
    }
    return localStorage.getItem(ACTIVE_PROFILE_KEY) || "";
  }

  function normalizeProfile(profile, index) {
    return {
      id: String(profile.id || `profile-${index}`),
      name: profile.name || profile.profileName || profile.profile_name || `Profile ${index + 1}`,
      accessKeyId: profile.accessKeyId || profile.aws_access_key_id || profile.access_key_id || "",
      secretAccessKey: profile.secretAccessKey || profile.aws_secret_access_key || profile.secret_access_key || "",
      region: profile.region || profile.aws_region || "us-east-1",
      isDefault: Boolean(profile.isDefault || profile.is_default),
      createdAt: profile.createdAt || profile.created_at || new Date().toISOString(),
    };
  }

  function getProfiles() {
    const stored = readJson(PROFILES_KEY, []);
    const source = Array.isArray(stored)
      ? stored
      : Object.entries(stored || {}).map(([name, profile]) => ({ name, ...profile }));
    const activeName = activeProfileName();
    return source.map((profile, index) => {
      const normalized = normalizeProfile(profile || {}, index);
      return {
        ...normalized,
        isDefault: normalized.isDefault || Boolean(activeName && normalized.name === activeName),
      };
    });
  }

  function saveProfiles(profiles) {
    localStorage.setItem(PROFILES_KEY, JSON.stringify(profiles));
    const defaultProfile = profiles.find((profile) => profile.isDefault);
    if (defaultProfile) {
      localStorage.setItem(ACTIVE_PROFILE_KEY, JSON.stringify(defaultProfile));
      localStorage.setItem("active_aws_region", defaultProfile.region);
    } else {
      localStorage.removeItem(ACTIVE_PROFILE_KEY);
    }
  }

  function maskAccessKey(value) {
    const key = String(value || "");
    if (!key) return "Not provided";
    if (key.length <= 8) return `${key.slice(0, 4)}...${key.slice(-4).padStart(4, "X")}`;
    return `${key.slice(0, 4)}...${key.slice(-4)}`;
  }

  function maskSecretKey(value) {
    const key = String(value || "");
    if (!key) return "Not provided";
    return `${"\u2022".repeat(Math.min(Math.max(key.length - 4, 8), 20))}${key.slice(-4)}`;
  }

  function formatJoinedDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Date unavailable";
    return date.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  }

  function profileColor(name) {
    const hue = Array.from(String(name || "AWS"))
      .reduce((total, character) => total + character.charCodeAt(0), 0) % 360;
    return `hsl(${hue} 55% 43%)`;
  }

  function accountCard(user) {
    return `
      <article class="profile-settings-card">
        <header class="profile-settings-card__header">
          <div>
            <h2>Account Details</h2>
            <p>Manage your personal information and password.</p>
          </div>
          ${state.accountEditing ? "" : `
            <button class="button button--secondary profile-edit-button" type="button" data-profile-action="edit-account">
              ${icons.edit}<span>Edit</span>
            </button>
          `}
        </header>

        <div class="profile-settings-card__body">
          <form class="account-details-form" id="profile-account-form" novalidate>
            <div class="profile-detail-field">
              <span>Full name</span>
              ${state.accountEditing
                ? `<input class="input" id="profile-name" name="name" type="text" autocomplete="name" value="${escapeHtml(user.name)}">`
                : `<strong>${escapeHtml(user.name)}</strong>`}
              <p class="field-error" data-profile-error="name"></p>
            </div>
            <div class="profile-detail-field">
              <span>Email address</span>
              ${state.accountEditing
                ? `<input class="input" id="profile-email" name="email" type="email" autocomplete="email" value="${escapeHtml(user.email)}">`
                : `<strong>${escapeHtml(user.email || "No email address")}</strong>`}
              <p class="field-error" data-profile-error="email"></p>
            </div>
            <div class="profile-detail-field">
              <span>Joined</span>
              <strong>${escapeHtml(formatJoinedDate(user.joinedAt))}</strong>
            </div>
            ${state.accountEditing ? `
              <div class="profile-form-actions">
                <button class="button button--primary" type="submit">
                  <span class="button__label">Save changes</span>
                </button>
                <button class="button button--secondary" type="button" data-profile-action="cancel-account">Cancel</button>
              </div>
              <p class="form-error" data-profile-form-error></p>
            ` : ""}
          </form>
        </div>

        <section class="password-section${state.passwordOpen ? " password-section--open" : ""}">
          <button class="password-section__toggle" type="button" data-profile-action="toggle-password" aria-expanded="${state.passwordOpen}">
            <span>
              <strong>Change Password</strong>
              <small>Update the password used to sign in.</small>
            </span>
            <span class="password-section__chevron">${icons.chevron}</span>
          </button>
          ${state.passwordOpen ? `
            <form class="password-change-form" id="profile-password-form" novalidate>
              ${passwordInput("current-password", "Current password", "current-password")}
              ${passwordInput("new-password", "New password", "new-password")}
              ${passwordInput("confirm-password", "Confirm new password", "new-password")}
              <div class="profile-form-actions">
                <button class="button button--primary" type="submit">
                  <span class="button__label">Save password</span>
                </button>
              </div>
              <p class="form-error" data-profile-form-error></p>
            </form>
          ` : ""}
        </section>
      </article>
    `;
  }

  function passwordInput(name, label, autocomplete) {
    const id = `profile-${name}`;
    return `
      <div class="field">
        <label class="field__label" for="${id}">${label}</label>
        <input class="input" id="${id}" name="${name}" type="password" autocomplete="${autocomplete}">
        <p class="field-error" data-profile-error="${name}"></p>
      </div>
    `;
  }

  function profileRow(profile) {
    const expanded = state.expandedProfileId === profile.id;
    const confirmingDelete = state.deleteProfileId === profile.id;
    return `
      <article class="credential-profile${expanded ? " credential-profile--expanded" : ""}">
        <div class="credential-profile__row" role="button" tabindex="0"
          data-profile-action="toggle-profile" data-profile-id="${escapeHtml(profile.id)}"
          aria-expanded="${expanded}">
          <span class="credential-profile__avatar" style="--profile-color: ${profileColor(profile.name)}">
            ${escapeHtml(profile.name.charAt(0).toUpperCase())}
          </span>
          <span class="credential-profile__identity">
            <span class="credential-profile__name">
              <strong>${escapeHtml(profile.name)}</strong>
              ${profile.isDefault ? '<span class="badge badge--primary">Default</span>' : ""}
            </span>
            <code>${escapeHtml(maskAccessKey(profile.accessKeyId))}</code>
          </span>
          <span class="credential-profile__actions">
            <button class="icon-button${profile.isDefault ? " credential-action--active" : ""}" type="button"
              data-profile-action="set-default" data-profile-id="${escapeHtml(profile.id)}"
              aria-label="Set ${escapeHtml(profile.name)} as default" title="Set as default"${profile.isDefault ? " disabled" : ""}>
              ${icons.star}
            </button>
            <span class="credential-delete">
              <button class="icon-button credential-action--danger" type="button"
                data-profile-action="request-delete" data-profile-id="${escapeHtml(profile.id)}"
                aria-label="Delete ${escapeHtml(profile.name)}" title="Delete profile">
                ${icons.trash}
              </button>
              ${confirmingDelete ? `
                <span class="delete-confirmation" role="dialog" aria-label="Confirm profile deletion">
                  <strong>Delete this profile?</strong>
                  <span>
                    <button type="button" data-profile-action="confirm-delete" data-profile-id="${escapeHtml(profile.id)}">Delete</button>
                    <button type="button" data-profile-action="cancel-delete">Cancel</button>
                  </span>
                </span>
              ` : ""}
            </span>
          </span>
          <span class="credential-profile__chevron">${icons.chevron}</span>
        </div>
        ${expanded ? `
          <dl class="credential-profile__details">
            <div><dt>Access key ID</dt><dd><code>${escapeHtml(maskAccessKey(profile.accessKeyId))}</code></dd></div>
            <div><dt>Secret access key</dt><dd><code>${escapeHtml(maskSecretKey(profile.secretAccessKey))}</code></dd></div>
            <div><dt>Default region</dt><dd><code>${escapeHtml(profile.region)}</code></dd></div>
          </dl>
        ` : ""}
      </article>
    `;
  }

  function addProfileForm() {
    return `
      <form class="add-profile-form" id="add-profile-form" novalidate>
        <div class="add-profile-form__grid">
          <div class="field">
            <label class="field__label" for="aws-profile-name">Profile Name</label>
            <input class="input" id="aws-profile-name" name="name" type="text" placeholder="Production">
            <p class="field-error" data-profile-error="name"></p>
          </div>
          <div class="field">
            <label class="field__label" for="aws-access-key-id">AWS Access Key ID</label>
            <input class="input resource-value" id="aws-access-key-id" name="accessKeyId" type="text" autocomplete="off" placeholder="AKIA...">
            <p class="field-error" data-profile-error="accessKeyId"></p>
          </div>
          <div class="field">
            <label class="field__label" for="aws-secret-access-key">AWS Secret Access Key</label>
            <div class="password-input">
              <input class="input resource-value" id="aws-secret-access-key" name="secretAccessKey" type="password" autocomplete="off">
              <button class="password-toggle" type="button" data-profile-action="toggle-secret" aria-label="Show secret access key" aria-pressed="false">
                ${icons.eye}
              </button>
            </div>
            <p class="field-error" data-profile-error="secretAccessKey"></p>
          </div>
          <div class="field">
            <label class="field__label" for="aws-profile-region">Default Region</label>
            <select class="select resource-value" id="aws-profile-region" name="region">
              ${REGIONS.map((region) => `<option value="${region}">${region}</option>`).join("")}
            </select>
          </div>
        </div>
        <label class="profile-checkbox">
          <input type="checkbox" name="isDefault">
          <span>Set as default profile</span>
        </label>
        <div class="profile-form-actions">
          <button class="button button--primary" type="submit">
            <span class="button__label">Save profile</span>
          </button>
          <button class="button button--secondary" type="button" data-profile-action="cancel-add-profile">Cancel</button>
        </div>
        <p class="form-error" data-profile-form-error></p>
      </form>
    `;
  }

  function credentialsCard(profiles) {
    return `
      <article class="profile-settings-card credential-profiles-card">
        <header class="profile-settings-card__header">
          <div>
            <h2>AWS Credential Profiles</h2>
            <p>Choose which credentials and region to use for AWS operations.</p>
          </div>
        </header>
        <div class="credential-profile-list">
          ${profiles.length
            ? profiles.map(profileRow).join("")
            : '<div class="credential-profile-empty"><strong>No credential profiles yet</strong><p>Add a profile to start running AWS automations.</p></div>'}
        </div>
        <div class="add-profile-section">
          <button class="button button--secondary add-profile-button" type="button"
            data-profile-action="open-add-profile"${state.addProfileOpen ? " hidden" : ""}>
            ${icons.plus}<span>Add new profile</span>
          </button>
          ${state.addProfileOpen ? addProfileForm() : ""}
        </div>
        <div class="credentials-info">
          <span>${icons.shield}</span>
          <p>Your credentials are stored locally and sent only to your own AWS account. They are never logged or stored on our servers.</p>
        </div>
      </article>
    `;
  }

  function render() {
    const user = getUser();
    const profiles = getProfiles();
    return `
      <div class="view profile-view" data-view="profile">
        <div class="profile-page-heading">
          <div>
            <h2>Profile settings</h2>
            <p>Manage your account and AWS credential profiles.</p>
          </div>
        </div>
        <div class="profile-settings-grid">
          ${accountCard(user)}
          ${credentialsCard(profiles)}
        </div>
      </div>
    `;
  }

  function rerender() {
    if (global.router?.currentView === "profile") {
      global.router.render("profile");
    }
  }

  function setError(form, field, message) {
    const error = form.querySelector(`[data-profile-error="${field}"]`);
    if (error) error.textContent = message;
  }

  function setFormError(form, message) {
    const error = form.querySelector("[data-profile-form-error]");
    if (error) error.textContent = message;
  }

  function setSubmitting(form, submitting, label) {
    const button = form.querySelector('button[type="submit"]');
    const buttonLabel = button?.querySelector(".button__label");
    if (!button || !buttonLabel) return;
    button.disabled = submitting;
    if (submitting) {
      buttonLabel.dataset.originalText = buttonLabel.textContent;
      buttonLabel.textContent = label;
      button.insertAdjacentHTML("afterbegin", global.Components.spinner());
    } else {
      button.querySelector(".spinner")?.remove();
      buttonLabel.textContent = buttonLabel.dataset.originalText || buttonLabel.textContent;
    }
  }

  function validEmail(value) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }

  async function saveAccount(form) {
    const name = form.elements.name.value.trim();
    const email = form.elements.email.value.trim();
    let valid = true;
    if (!name) {
      setError(form, "name", "Enter your full name.");
      valid = false;
    }
    if (!validEmail(email)) {
      setError(form, "email", "Enter a valid email address.");
      valid = false;
    }
    if (!valid) return;

    setSubmitting(form, true, "Saving");
    try {
      const response = await global.api.request("PATCH", "/user/me", { name, email });
      const current = getUser();
      const updated = response?.user || response || {};
      localStorage.setItem(USER_KEY, JSON.stringify({
        ...current,
        ...updated,
        name: updated.name || updated.full_name || name,
        email: updated.email || email,
        joined_at: current.joinedAt,
      }));
      state.accountEditing = false;
      rerender();
      global.Components.toast("Profile updated", "success");
    } catch (error) {
      setFormError(form, error.message || "Unable to update your profile.");
      setSubmitting(form, false, "Saving");
    }
  }

  async function savePassword(form) {
    const currentPassword = form.elements["current-password"].value;
    const newPassword = form.elements["new-password"].value;
    const confirmPassword = form.elements["confirm-password"].value;
    let valid = true;
    if (!currentPassword) {
      setError(form, "current-password", "Enter your current password.");
      valid = false;
    }
    if (newPassword.length < 8) {
      setError(form, "new-password", "New password must be at least 8 characters.");
      valid = false;
    }
    if (confirmPassword !== newPassword) {
      setError(form, "confirm-password", "Passwords do not match.");
      valid = false;
    }
    if (!valid) return;

    setSubmitting(form, true, "Saving");
    try {
      await global.api.request("PATCH", "/user/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      state.passwordOpen = false;
      rerender();
      global.Components.toast("Password updated", "success");
    } catch (error) {
      setFormError(form, error.message || "Unable to update your password.");
      setSubmitting(form, false, "Saving");
    }
  }

  function createProfileId() {
    return global.crypto?.randomUUID?.() || `profile-${Date.now()}`;
  }

  async function saveNewProfile(form) {
    const profile = {
      id: createProfileId(),
      name: form.elements.name.value.trim(),
      accessKeyId: form.elements.accessKeyId.value.trim(),
      secretAccessKey: form.elements.secretAccessKey.value.trim(),
      region: form.elements.region.value,
      isDefault: form.elements.isDefault.checked,
      createdAt: new Date().toISOString(),
    };
    let valid = true;
    if (!profile.name) {
      setError(form, "name", "Enter a profile name.");
      valid = false;
    }
    if (!profile.accessKeyId) {
      setError(form, "accessKeyId", "Enter an AWS access key ID.");
      valid = false;
    }
    if (!profile.secretAccessKey) {
      setError(form, "secretAccessKey", "Enter an AWS secret access key.");
      valid = false;
    }
    if (!valid) return;

    setSubmitting(form, true, "Saving");
    try {
      let response = null;
      try {
        response = await global.api.request("POST", "/aws-profiles", {
          name: profile.name,
          aws_access_key_id: profile.accessKeyId,
          aws_secret_access_key: profile.secretAccessKey,
          region: profile.region,
          is_default: profile.isDefault,
        });
      } catch (error) {
        if (![404, 405].includes(error.status) && !(error instanceof TypeError)) {
          throw error;
        }
      }

      const profiles = getProfiles();
      const saved = normalizeProfile({
        ...profile,
        ...(response?.profile || response || {}),
        accessKeyId: response?.accessKeyId || response?.aws_access_key_id || profile.accessKeyId,
        secretAccessKey: response?.secretAccessKey || response?.aws_secret_access_key || profile.secretAccessKey,
      }, profiles.length);
      saved.id = profile.id;
      saved.isDefault = profile.isDefault || profiles.length === 0;
      const updated = saved.isDefault
        ? profiles.map((item) => ({ ...item, isDefault: false }))
        : profiles;
      saveProfiles([...updated, saved]);
      state.addProfileOpen = false;
      state.expandedProfileId = saved.id;
      rerender();
      global.Components.toast("AWS profile saved", "success");
    } catch (error) {
      setFormError(form, error.message || "Unable to save this AWS profile.");
      setSubmitting(form, false, "Saving");
    }
  }

  function setDefaultProfile(id) {
    const profiles = getProfiles().map((profile) => ({
      ...profile,
      isDefault: profile.id === id,
    }));
    saveProfiles(profiles);
    rerender();
    global.Components.toast("Default profile updated", "success");
  }

  function deleteProfile(id) {
    const profiles = getProfiles();
    const deleted = profiles.find((profile) => profile.id === id);
    let remaining = profiles.filter((profile) => profile.id !== id);
    if (deleted?.isDefault && remaining.length) {
      remaining = remaining.map((profile, index) => ({ ...profile, isDefault: index === 0 }));
    }
    saveProfiles(remaining);
    state.deleteProfileId = null;
    if (state.expandedProfileId === id) state.expandedProfileId = null;
    rerender();
    global.Components.toast("AWS profile deleted", "success");
  }

  function handleAction(action, element) {
    const id = element.dataset.profileId;
    if (action === "edit-account") state.accountEditing = true;
    if (action === "cancel-account") state.accountEditing = false;
    if (action === "toggle-password") state.passwordOpen = !state.passwordOpen;
    if (action === "open-add-profile") state.addProfileOpen = true;
    if (action === "cancel-add-profile") state.addProfileOpen = false;
    if (action === "toggle-profile") {
      state.expandedProfileId = state.expandedProfileId === id ? null : id;
    }
    if (action === "set-default") {
      setDefaultProfile(id);
      return;
    }
    if (action === "request-delete") state.deleteProfileId = id;
    if (action === "cancel-delete") state.deleteProfileId = null;
    if (action === "confirm-delete") {
      deleteProfile(id);
      return;
    }
    if (action === "toggle-secret") {
      const input = document.getElementById("aws-secret-access-key");
      const visible = input?.type === "password";
      if (input) input.type = visible ? "text" : "password";
      element.setAttribute("aria-pressed", String(visible));
      element.setAttribute("aria-label", `${visible ? "Hide" : "Show"} secret access key`);
      return;
    }
    rerender();
  }

  function mount() {
    const root = document.querySelector(".profile-view");
    if (!root) return;

    root.addEventListener("click", (event) => {
      const actionElement = event.target.closest("[data-profile-action]");
      if (!actionElement) return;
      event.preventDefault();
      event.stopPropagation();
      handleAction(actionElement.dataset.profileAction, actionElement);
    });

    root.addEventListener("keydown", (event) => {
      const row = event.target.closest('[data-profile-action="toggle-profile"]');
      if (row && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        handleAction("toggle-profile", row);
      }
    });

    root.addEventListener("input", (event) => {
      const form = event.target.form;
      if (!form) return;
      const fieldError = form.querySelector(`[data-profile-error="${event.target.name}"]`);
      if (fieldError) fieldError.textContent = "";
      setFormError(form, "");
    });

    root.addEventListener("submit", (event) => {
      event.preventDefault();
      if (event.target.id === "profile-account-form") saveAccount(event.target);
      if (event.target.id === "profile-password-form") savePassword(event.target);
      if (event.target.id === "add-profile-form") saveNewProfile(event.target);
    });
  }

  global.Profile = { render, mount };
})(window);

(function initializeChat(global) {
  "use strict";

  const CONVERSATIONS_KEY = "chat_conversations";
  const ACTIVE_CONVERSATION_KEY = "active_chat_conversation";
  const MAX_MESSAGE_LENGTH = 4000;
  const state = {
    conversations: [],
    activeId: null,
    busy: false,
    streamingTimers: [],
  };

  const icons = {
    bot: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="6" width="16" height="14" rx="3"></rect><path d="M12 2v4M8 11h.01M16 11h.01M8 16h8"></path></svg>',
    plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"></path></svg>',
    trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"></path></svg>',
    send: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m22 2-7 20-4-9-9-4 20-7Z"></path><path d="M22 2 11 13"></path></svg>',
    check: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"></path></svg>',
    error: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8v5M12 17h.01"></path><circle cx="12" cy="12" r="9"></circle></svg>',
    clock: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>',
    menu: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16"></path></svg>',
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function readJson(storage, key, fallback) {
    try {
      const value = JSON.parse(storage.getItem(key) || "null");
      return value ?? fallback;
    } catch {
      return fallback;
    }
  }

  function uid() {
    return global.crypto?.randomUUID?.()
      || `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  function normalizeConversation(item) {
    return {
      id: String(item?.id || uid()),
      title: String(item?.title || "New conversation"),
      messages: Array.isArray(item?.messages) ? item.messages : [],
      profile: item?.profile || getProfile().name,
      created_at: item?.created_at || new Date().toISOString(),
      session_id: item?.session_id || null,
    };
  }

  function loadConversations() {
    const stored = readJson(localStorage, CONVERSATIONS_KEY, []);
    state.conversations = Array.isArray(stored)
      ? stored.map(normalizeConversation)
      : [];
    const requestedId = localStorage.getItem(ACTIVE_CONVERSATION_KEY);
    state.activeId = state.conversations.some((item) => item.id === requestedId)
      ? requestedId
      : state.conversations[0]?.id || null;
  }

  function saveConversations() {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(state.conversations));
    if (state.activeId) {
      localStorage.setItem(ACTIVE_CONVERSATION_KEY, state.activeId);
    } else {
      localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    }
  }

  function getProfile() {
    const guest = global.auth?.getGuestCredentials?.();
    if (guest) {
      return {
        name: "Temporary profile",
        aws_access_key_id: guest.aws_access_key_id || "",
        aws_secret_access_key: guest.aws_secret_access_key || "",
        region: guest.region || "us-east-1",
      };
    }

    const activeRaw = localStorage.getItem("active_aws_profile");
    const activeObject = readJson(localStorage, "active_aws_profile", null);
    const profiles = readJson(localStorage, "aws_profiles", null);
    let profile = activeObject && typeof activeObject === "object"
      ? activeObject
      : null;

    if (!profile && activeRaw && profiles) {
      profile = Array.isArray(profiles)
        ? profiles.find((item) => item?.name === activeRaw)
        : profiles[activeRaw];
    }
    profile = profile || {};

    return {
      name: profile.name || profile.profileName || activeRaw || "Default profile",
      aws_access_key_id: profile.aws_access_key_id
        || profile.accessKeyId
        || profile.access_key_id
        || "",
      aws_secret_access_key: profile.aws_secret_access_key
        || profile.secretAccessKey
        || profile.secret_access_key
        || "",
      region: profile.region
        || profile.aws_region
        || localStorage.getItem("active_aws_region")
        || "us-east-1",
    };
  }

  function activeConversation() {
    return state.conversations.find((item) => item.id === state.activeId) || null;
  }

  function createConversation() {
    const conversation = normalizeConversation({
      id: uid(),
      title: "New conversation",
      messages: [],
      profile: getProfile().name,
      created_at: new Date().toISOString(),
    });
    state.conversations.unshift(conversation);
    state.activeId = conversation.id;
    saveConversations();
    renderDynamicSections();
    document.getElementById("chat-input")?.focus();
    closeHistoryOnMobile();
    return conversation;
  }

  function ensureConversation() {
    return activeConversation() || createConversation();
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const today = new Date();
    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    }
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  function messageText(text) {
    return escapeHtml(text).replace(/\n/g, "<br>");
  }

  function riskType(risk) {
    const value = String(risk || "low").toLowerCase();
    if (value === "medium") return "warning";
    if (value === "high" || value === "critical") return "danger";
    return "success";
  }

  function renderHistory() {
    const list = document.getElementById("conversation-list");
    if (!list) return;
    list.innerHTML = state.conversations.length
      ? state.conversations.map((conversation) => `
          <li class="conversation-item${conversation.id === state.activeId ? " active" : ""}">
            <button class="conversation-item__select" type="button"
              data-chat-action="select-conversation" data-conversation-id="${escapeHtml(conversation.id)}"
              ${conversation.id === state.activeId ? 'aria-current="true"' : ""}>
              <strong>${escapeHtml(conversation.title)}</strong>
              <small>${escapeHtml(formatDate(conversation.created_at))}</small>
            </button>
            <button class="conversation-item__delete" type="button"
              data-chat-action="delete-conversation" data-conversation-id="${escapeHtml(conversation.id)}"
              aria-label="Delete ${escapeHtml(conversation.title)}">
              ${icons.trash}
            </button>
          </li>
        `).join("")
      : '<li class="conversation-list__empty">No conversations yet</li>';
  }

  function juryText(verdict) {
    if (verdict?.blocked) {
      return verdict.block_reason || "The jury blocked this plan.";
    }
    const warnings = Array.isArray(verdict?.warnings) ? verdict.warnings : [];
    if (warnings.length) return warnings.join(" ");
    if (verdict?.requires_explicit_approval) {
      return "The jury requires explicit approval before this plan can run.";
    }
    return "The jury found no blocking safety concerns.";
  }

  function renderExecution(result) {
    const output = result.result ?? result.output ?? result.error ?? "No output";
    const status = String(result.status || "success").toLowerCase();
    const isSuccess = ["success", "completed", "done"].includes(status);
    return `
      <li class="execution-row execution-row--${isSuccess ? "success" : "error"}">
        <span class="execution-row__icon">${isSuccess ? icons.check : icons.error}</span>
        <code>${escapeHtml(result.tool || result.tool_name || "AWS tool")}</code>
        <span title="${escapeHtml(typeof output === "string" ? output : JSON.stringify(output))}">
          ${escapeHtml(typeof output === "string" ? output : JSON.stringify(output))}
        </span>
      </li>
    `;
  }

  function renderPlan(message) {
    const plan = Array.isArray(message.plan) ? message.plan : [];
    const verdict = message.jury_verdict || {};
    const verdictRisk = String(verdict.risk_level || "low").toLowerCase();
    const blocked = Boolean(verdict.blocked);
    const results = Array.isArray(message.results) ? message.results : [];
    const isExecuting = message.status === "executing";
    const revisionOpen = Boolean(message.revision_open);
    return `
      <article class="plan-card" data-plan-id="${escapeHtml(message.id)}">
        <header class="plan-card__header">
          <div>
            <span class="plan-card__eyebrow">Safety reviewed</span>
            <h3>Proposed Plan <span>(${plan.length} ${plan.length === 1 ? "step" : "steps"})</span></h3>
          </div>
          <span class="risk-badge risk-badge--${riskType(verdictRisk)}">${escapeHtml(verdictRisk)} risk</span>
        </header>
        <ol class="plan-steps">
          ${plan.map((step, index) => `
            <li class="plan-step">
              <span class="plan-step__number">${Number(step.step_number || index + 1)}</span>
              <div class="plan-step__content">
                <code>${escapeHtml(step.tool_name || "unknown_tool")}</code>
                <p>${escapeHtml(step.reason || step.tool_description || "No reason provided.")}</p>
              </div>
              <span class="risk-badge risk-badge--${riskType(step.risk_level)}">${escapeHtml(step.risk_level || "low")}</span>
            </li>
          `).join("")}
        </ol>
        <div class="jury-banner jury-banner--${blocked ? "danger" : riskType(verdictRisk)}">
          <strong>Jury verdict</strong>
          <span>${escapeHtml(juryText(verdict))}</span>
        </div>
        ${message.status === "awaiting_approval" ? `
          <div class="plan-card__actions">
            <button class="button button--primary" type="button"
              data-chat-action="approve-plan" data-message-id="${escapeHtml(message.id)}"
              data-plan-blocked="${String(blocked)}"
              ${blocked || state.busy ? "disabled" : ""}>
              ${icons.check}<span>Approve &amp; Execute</span>
            </button>
            <button class="button button--secondary" type="button"
              data-chat-action="toggle-revision" data-message-id="${escapeHtml(message.id)}"
              ${state.busy ? "disabled" : ""}>Modify Plan</button>
          </div>
          <form class="plan-revision${revisionOpen ? " plan-revision--open" : ""}"
            data-revision-form="${escapeHtml(message.id)}">
            <label for="revision-${escapeHtml(message.id)}">What should change?</label>
            <textarea id="revision-${escapeHtml(message.id)}" rows="3"
              maxlength="${MAX_MESSAGE_LENGTH}" placeholder="Describe the changes you want..."></textarea>
            <div>
              <button class="button button--secondary" type="button"
                data-chat-action="toggle-revision" data-message-id="${escapeHtml(message.id)}">Cancel</button>
              <button class="button button--primary" type="submit">Send feedback</button>
            </div>
          </form>
        ` : ""}
        ${(isExecuting || results.length) ? `
          <section class="execution-log" aria-live="polite">
            <header>
              <strong>Execution log</strong>
              ${isExecuting ? '<span class="execution-log__live"><i></i> Live</span>' : ""}
            </header>
            <ul>
              ${results.map(renderExecution).join("")}
              ${isExecuting && !results.length ? `
                <li class="execution-row execution-row--pending">
                  <span class="execution-row__icon">${icons.clock}</span>
                  <code>Preparing</code><span>Starting approved plan...</span>
                </li>
              ` : ""}
            </ul>
          </section>
        ` : ""}
      </article>
    `;
  }

  function renderMessage(message) {
    if (message.type === "plan") {
      return `
        <div class="chat-message chat-message--agent">
          <span class="chat-message__avatar">${icons.bot}</span>
          <div class="chat-message__body">${renderPlan(message)}</div>
        </div>
      `;
    }
    if (message.role === "user") {
      return `
        <div class="chat-message chat-message--user">
          <div class="chat-bubble">${messageText(message.content)}</div>
        </div>
      `;
    }
    return `
      <div class="chat-message chat-message--agent">
        <span class="chat-message__avatar">${icons.bot}</span>
        <div class="chat-message__body">
          <div class="agent-response">${messageText(message.content)}</div>
        </div>
      </div>
    `;
  }

  function renderMessages() {
    const container = document.getElementById("chat-messages");
    if (!container) return;
    const conversation = activeConversation();
    if (!conversation?.messages.length) {
      container.innerHTML = `
        <div class="chat-empty">
          <span class="chat-empty__icon">${icons.bot}</span>
          <h2>What should we automate?</h2>
          <p>Describe an AWS task. I’ll propose a reviewed plan before anything runs.</p>
          <div class="chat-prompts">
            <button type="button" data-chat-prompt="List my running EC2 instances">List running EC2 instances</button>
            <button type="button" data-chat-prompt="Review my S3 buckets for public access">Review S3 public access</button>
          </div>
        </div>
      `;
    } else {
      container.innerHTML = conversation.messages.map(renderMessage).join("");
    }
    requestAnimationFrame(() => {
      container.scrollTop = container.scrollHeight;
    });
  }

  function renderProfile() {
    const profile = getProfile();
    document.querySelector("[data-chat-profile-name]")?.replaceChildren(
      document.createTextNode(profile.name),
    );
    document.querySelector("[data-chat-profile-region]")?.replaceChildren(
      document.createTextNode(profile.region),
    );
  }

  function renderDynamicSections() {
    renderHistory();
    renderMessages();
    renderProfile();
  }

  function render() {
    return `
      <div class="view chat-view" data-view="chat">
        <aside class="conversation-sidebar" id="conversation-sidebar" aria-label="Conversation history">
          <div class="conversation-sidebar__header">
            <button class="new-chat-button" type="button" data-chat-action="new-chat">
              ${icons.plus}<span>New chat</span>
            </button>
          </div>
          <p class="conversation-sidebar__label">Conversations</p>
          <ul class="conversation-list" id="conversation-list"></ul>
        </aside>
        <button class="conversation-backdrop" type="button" data-chat-action="close-history"
          aria-label="Close conversation history"></button>

        <section class="chat-panel">
          <header class="chat-profile-bar">
            <button class="chat-history-toggle" type="button" data-chat-action="toggle-history"
              aria-label="Open conversation history">${icons.menu}</button>
            <span class="chat-profile-bar__status" aria-hidden="true"></span>
            <span>Using <strong data-chat-profile-name>Default profile</strong></span>
            <code data-chat-profile-region>us-east-1</code>
            <button type="button" data-action="switch-profile">Change</button>
          </header>
          <div class="chat-messages" id="chat-messages" aria-live="polite"></div>
          <footer class="chat-composer">
            <form id="chat-form">
              <div class="chat-composer__input">
                <label class="sr-only" for="chat-input">Message</label>
                <textarea id="chat-input" name="message" rows="1"
                  maxlength="${MAX_MESSAGE_LENGTH}" placeholder="Ask the agent to automate an AWS task..."
                  aria-describedby="chat-character-count"></textarea>
                <button class="chat-send" type="submit" aria-label="Send message" disabled>${icons.send}</button>
              </div>
              <div class="chat-composer__meta">
                <span>Enter to send, Shift + Enter for a new line</span>
                <span id="chat-character-count">0 / ${MAX_MESSAGE_LENGTH}</span>
              </div>
            </form>
          </footer>
        </section>
      </div>
    `;
  }

  function clearStreamingTimers() {
    state.streamingTimers.forEach(window.clearTimeout);
    state.streamingTimers = [];
  }

  function updateComposer() {
    const input = document.getElementById("chat-input");
    if (!input) return;
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 104)}px`;
    const count = document.getElementById("chat-character-count");
    if (count) count.textContent = `${input.value.length} / ${MAX_MESSAGE_LENGTH}`;
    const send = document.querySelector(".chat-send");
    if (send) send.disabled = state.busy || !input.value.trim();
  }

  function setBusy(busy) {
    state.busy = busy;
    document.querySelector(".chat-view")?.classList.toggle("chat-view--busy", busy);
    document.querySelectorAll("[data-chat-action='approve-plan'], [data-chat-action='toggle-revision']")
      .forEach((button) => {
        button.disabled = busy || button.dataset.planBlocked === "true";
      });
    updateComposer();
  }

  function credentialsPayload() {
    const profile = getProfile();
    if (!profile.aws_access_key_id || !profile.aws_secret_access_key) {
      throw new Error("The active profile does not include AWS credentials. Switch to a configured profile.");
    }
    return profile;
  }

  function appendPlan(conversation, data) {
    conversation.session_id = data.session_id || conversation.session_id;
    conversation.messages.push({
      id: uid(),
      role: "agent",
      type: "plan",
      plan: data.plan || [],
      jury_verdict: data.jury_verdict || {},
      formatted_plan: data.formatted_plan || "",
      status: "awaiting_approval",
      created_at: new Date().toISOString(),
    });
  }

  async function sendMessage(text) {
    if (state.busy || !text.trim()) return;
    const conversation = ensureConversation();
    const content = text.trim();
    if (!conversation.messages.some((item) => item.role === "user")) {
      conversation.title = content.slice(0, 40);
    }
    conversation.messages.push({
      id: uid(),
      role: "user",
      type: "text",
      content,
      created_at: new Date().toISOString(),
    });
    conversation.profile = getProfile().name;
    saveConversations();
    renderDynamicSections();
    setBusy(true);

    try {
      const credentials = credentialsPayload();
      const data = await global.api.request("POST", "/chat", {
        session_id: conversation.session_id,
        message: content,
        aws_access_key_id: credentials.aws_access_key_id,
        aws_secret_access_key: credentials.aws_secret_access_key,
        region: credentials.region,
      });
      appendPlan(conversation, data);
    } catch (error) {
      conversation.messages.push({
        id: uid(),
        role: "agent",
        type: "text",
        content: error.message || "I could not prepare the plan.",
        created_at: new Date().toISOString(),
      });
    } finally {
      setBusy(false);
      saveConversations();
      renderDynamicSections();
    }
  }

  function findPlan(messageId) {
    const conversation = activeConversation();
    const message = conversation?.messages.find((item) => item.id === messageId);
    return { conversation, message };
  }

  function storeExecutionAction(result, conversation) {
    const actions = readJson(localStorage, "agent_executions", []);
    const next = Array.isArray(actions) ? actions : [];
    next.unshift({
      id: uid(),
      summary: result.summary || `Executed ${result.results?.length || 0} AWS plan steps`,
      status: result.phase === "done" ? "completed" : "error",
      timestamp: new Date().toISOString(),
      conversation_id: conversation.id,
    });
    localStorage.setItem("agent_executions", JSON.stringify(next.slice(0, 50)));
  }

  function streamResults(message, results, summary, conversation) {
    clearStreamingTimers();
    message.results = [];
    results.forEach((result, index) => {
      const timer = window.setTimeout(() => {
        message.results.push(result);
        saveConversations();
        renderMessages();
        if (index === results.length - 1) {
          message.status = "completed";
          if (summary) {
            conversation.messages.push({
              id: uid(),
              role: "agent",
              type: "text",
              content: summary,
              created_at: new Date().toISOString(),
            });
          }
          saveConversations();
          renderMessages();
        }
      }, 280 * (index + 1));
      state.streamingTimers.push(timer);
    });
    if (!results.length) {
      message.status = "completed";
      if (summary) {
        conversation.messages.push({
          id: uid(),
          role: "agent",
          type: "text",
          content: summary,
          created_at: new Date().toISOString(),
        });
      }
      saveConversations();
      renderMessages();
    }
  }

  async function approvePlan(messageId) {
    if (state.busy) return;
    const { conversation, message } = findPlan(messageId);
    if (!conversation || !message || !conversation.session_id) return;
    message.status = "executing";
    message.results = [];
    saveConversations();
    renderMessages();
    setBusy(true);
    try {
      const data = await global.api.request("POST", "/approve", {
        session_id: conversation.session_id,
        approved: true,
      });
      storeExecutionAction(data, conversation);
      streamResults(message, data.results || [], data.summary || "", conversation);
    } catch (error) {
      message.status = "completed";
      message.results = [{
        tool: "Execution",
        status: "error",
        error: error.message || "Execution failed.",
      }];
      saveConversations();
      renderMessages();
    } finally {
      setBusy(false);
    }
  }

  async function revisePlan(messageId, feedback) {
    if (state.busy || !feedback.trim()) return;
    const { conversation, message } = findPlan(messageId);
    if (!conversation || !message || !conversation.session_id) return;
    message.status = "revised";
    conversation.messages.push({
      id: uid(),
      role: "user",
      type: "text",
      content: feedback.trim(),
      created_at: new Date().toISOString(),
    });
    saveConversations();
    renderMessages();
    setBusy(true);
    try {
      const data = await global.api.request("POST", "/approve", {
        session_id: conversation.session_id,
        approved: false,
        refinement_message: feedback.trim(),
      });
      appendPlan(conversation, data);
    } catch (error) {
      message.status = "awaiting_approval";
      conversation.messages.push({
        id: uid(),
        role: "agent",
        type: "text",
        content: error.message || "I could not revise the plan.",
        created_at: new Date().toISOString(),
      });
    } finally {
      setBusy(false);
      saveConversations();
      renderMessages();
    }
  }

  function deleteConversation(id) {
    const conversation = state.conversations.find((item) => item.id === id);
    state.conversations = state.conversations.filter((item) => item.id !== id);
    if (state.activeId === id) {
      state.activeId = state.conversations[0]?.id || null;
    }
    saveConversations();
    renderDynamicSections();
    if (conversation?.session_id) {
      global.api.request("DELETE", `/session/${encodeURIComponent(conversation.session_id)}`)
        .catch(() => {});
    }
  }

  function closeHistoryOnMobile() {
    document.querySelector(".chat-view")?.classList.remove("chat-view--history-open");
  }

  function handleClick(event) {
    if (global.router?.currentView !== "chat") return;
    const prompt = event.target.closest("[data-chat-prompt]");
    if (prompt) {
      const input = document.getElementById("chat-input");
      if (input) {
        input.value = prompt.dataset.chatPrompt;
        updateComposer();
        input.focus();
      }
      return;
    }

    const target = event.target.closest("[data-chat-action]");
    if (!target) return;
    const action = target.dataset.chatAction;
    const conversationId = target.dataset.conversationId;
    const messageId = target.dataset.messageId;

    if (action === "new-chat") {
      createConversation();
    } else if (action === "select-conversation") {
      state.activeId = conversationId;
      saveConversations();
      renderDynamicSections();
      closeHistoryOnMobile();
    } else if (action === "delete-conversation") {
      deleteConversation(conversationId);
    } else if (action === "approve-plan") {
      approvePlan(messageId);
    } else if (action === "toggle-revision") {
      const { message } = findPlan(messageId);
      if (message) {
        message.revision_open = !message.revision_open;
        saveConversations();
        renderMessages();
        if (message.revision_open) {
          document.getElementById(`revision-${messageId}`)?.focus();
        }
      }
    } else if (action === "toggle-history") {
      document.querySelector(".chat-view")?.classList.toggle("chat-view--history-open");
    } else if (action === "close-history") {
      closeHistoryOnMobile();
    }
  }

  function handleInput(event) {
    if (event.target.id === "chat-input") updateComposer();
  }

  function handleKeydown(event) {
    if (event.target.id === "chat-input" && event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.target.form?.requestSubmit();
    }
  }

  function handleSubmit(event) {
    if (global.router?.currentView !== "chat") return;
    if (event.target.id === "chat-form") {
      event.preventDefault();
      const input = document.getElementById("chat-input");
      const text = input?.value || "";
      if (input && text.trim() && !state.busy) {
        input.value = "";
        updateComposer();
        sendMessage(text);
      }
      return;
    }
    const messageId = event.target.dataset.revisionForm;
    if (messageId) {
      event.preventDefault();
      const feedback = event.target.querySelector("textarea")?.value || "";
      revisePlan(messageId, feedback);
    }
  }

  function mount() {
    clearStreamingTimers();
    loadConversations();
    renderDynamicSections();
    updateComposer();
  }

  document.addEventListener("click", handleClick);
  document.addEventListener("input", handleInput);
  document.addEventListener("keydown", handleKeydown);
  document.addEventListener("submit", handleSubmit);

  global.Chat = { render, mount };
})(window);

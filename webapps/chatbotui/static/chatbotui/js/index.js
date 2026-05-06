(function () {
  const DEBUG_MODE = document.body.dataset.debugMode === "1";
  const DEFAULT_MODEL_TYPE = document.body.dataset.modelType || "OPENAI";

  const elements = {
    conversationList: document.getElementById("conversationList"),
    messageLog: document.getElementById("messageLog"),
    messageInput: document.getElementById("messageInput"),
    sendBtn: document.getElementById("sendBtn"),
    newChatBtn: document.getElementById("newChatBtn"),
    clearChatBtn: document.getElementById("clearChatBtn"),
    chatTitle: document.getElementById("chatTitle"),
    modelBadge: document.getElementById("modelBadge"),
    debugPanel: document.getElementById("debugPanel"),
    debugLog: document.getElementById("debugLog"),
    clearDebugBtn: document.getElementById("clearDebugBtn")
  };

  const state = {
    conversations: [],
    activeId: "",
    debugLines: []
  };

  function url(path) {
    if (window.apiurl) return window.apiurl(path);
    const base = document.body.dataset.baseUrl || "";
    return `${base}${path}`;
  }

  function pushDebug(line) {
    if (!DEBUG_MODE) return;
    state.debugLines.push(line);
    state.debugLines = state.debugLines.slice(-30);
    elements.debugPanel.classList.remove("hidden");
    elements.debugLog.textContent = state.debugLines.join("\n");
  }

  function activeConversation() {
    return state.conversations.find((item) => item.id === state.activeId) || null;
  }

  async function apiFetch(path, options) {
    const response = await fetch(url(path), options);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  async function loadConversations() {
    const data = await apiFetch("/chatbotui/conversations/", { method: "GET" });
    state.conversations = (data.conversations || []).map(function (item) {
      return {
        id: item.id,
        title: item.title || "New Chat",
        model_type: item.model_type || DEFAULT_MODEL_TYPE,
        preview: item.preview || "",
        messages: []
      };
    });
    if (!state.activeId && state.conversations.length > 0) {
      state.activeId = state.conversations[0].id;
    }
  }

  async function loadConversationDetail(conversationId) {
    const data = await apiFetch(`/chatbotui/conversations/${conversationId}/`, { method: "GET" });
    const detail = data.conversation;
    const target = state.conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.title = detail.title || "New Chat";
    target.model_type = detail.model_type || DEFAULT_MODEL_TYPE;
    target.messages = Array.isArray(detail.messages) ? detail.messages : [];
    target.preview = target.messages.length ? target.messages[target.messages.length - 1].content.slice(0, 80) : "";
  }

  async function createConversation() {
    const data = await apiFetch("/chatbotui/conversations/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New Chat", model_type: DEFAULT_MODEL_TYPE })
    });
    const conversation = data.conversation;
    state.conversations.unshift({
      id: conversation.id,
      title: conversation.title || "New Chat",
      model_type: conversation.model_type || DEFAULT_MODEL_TYPE,
      preview: "",
      messages: Array.isArray(conversation.messages) ? conversation.messages : []
    });
    state.activeId = conversation.id;
    render();
    elements.messageInput.focus();
  }

  async function removeConversation() {
    const current = activeConversation();
    if (!current) return;
    await apiFetch(`/chatbotui/conversations/${current.id}/`, { method: "DELETE" });
    state.conversations = state.conversations.filter((item) => item.id !== current.id);
    state.activeId = state.conversations.length ? state.conversations[0].id : "";
    if (state.activeId) {
      await loadConversationDetail(state.activeId);
    } else {
      await createConversation();
    }
    render();
  }

  async function clearMessages() {
    const current = activeConversation();
    if (!current) return;
    await apiFetch(`/chatbotui/conversations/${current.id}/clear/`, { method: "POST" });
    current.messages = [];
    current.title = "New Chat";
    current.preview = "";
    render();
  }

  async function setActiveConversation(id) {
    state.activeId = id;
    const current = activeConversation();
    if (current && current.messages.length === 0) {
      await loadConversationDetail(id);
    }
    render();
  }

  function renderConversationList() {
    elements.conversationList.innerHTML = "";
    state.conversations.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `conversation-item${item.id === state.activeId ? " active" : ""}`;
      button.innerHTML = "<span class=\"conversation-title\"></span><span class=\"conversation-preview\"></span>";
      button.querySelector(".conversation-title").textContent = item.title || "New Chat";
      button.querySelector(".conversation-preview").textContent = item.preview || "No messages yet";
      button.addEventListener("click", function () {
        setActiveConversation(item.id).catch(handleUiError);
      });
      elements.conversationList.appendChild(button);
    });
  }

  function renderMessages() {
    const current = activeConversation();
    elements.messageLog.innerHTML = "";
    if (!current || current.messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "開始新的對話，像 Open WebUI 一樣在這裡持續累積聊天脈絡。你可以問知識、整理想法、產生草稿或請它協助寫程式。";
      elements.messageLog.appendChild(empty);
      return;
    }
    current.messages.forEach((message) => {
      const block = document.createElement("div");
      block.className = `message ${message.role}`;
      const role = document.createElement("span");
      role.className = "message-role";
      role.textContent = message.role === "user" ? "You" : "Assistant";
      const body = document.createElement("div");
      body.textContent = message.content;
      block.appendChild(role);
      block.appendChild(body);
      elements.messageLog.appendChild(block);
    });
    elements.messageLog.scrollTop = elements.messageLog.scrollHeight;
  }

  function render() {
    const current = activeConversation();
    elements.chatTitle.textContent = current ? current.title : "New Chat";
    elements.modelBadge.textContent = current ? (current.model_type || DEFAULT_MODEL_TYPE) : DEFAULT_MODEL_TYPE;
    renderConversationList();
    renderMessages();
  }

  async function sendMessage() {
    const current = activeConversation();
    if (!current) return;

    const text = elements.messageInput.value.trim();
    if (!text) return;

    current.messages.push({ role: "user", content: text, model_type: current.model_type || DEFAULT_MODEL_TYPE });
    current.preview = text.slice(0, 80);
    elements.messageInput.value = "";
    render();

    elements.sendBtn.disabled = true;
    pushDebug(`[request] conversation=${current.id} model=${current.model_type || DEFAULT_MODEL_TYPE} chars=${text.length}`);

    try {
      const data = await apiFetch("/chatbotui/chat/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: current.id,
          model_type: current.model_type || DEFAULT_MODEL_TYPE,
          message: text
        })
      });
      current.title = data.conversation_title || current.title || "New Chat";
      current.model_type = data.meta && data.meta.model_type ? data.meta.model_type : (current.model_type || DEFAULT_MODEL_TYPE);
      current.messages.push({ role: "assistant", content: data.reply, model_type: current.model_type });
      current.preview = data.reply.slice(0, 80);
      render();
      pushDebug(`[response] ok model=${current.model_type} latency_ms=${data.meta && data.meta.latency_ms ? data.meta.latency_ms : 0}`);
    } catch (error) {
      current.messages.push({ role: "assistant", content: `系統錯誤：${error.message}`, model_type: current.model_type || DEFAULT_MODEL_TYPE });
      render();
      pushDebug(`[error] ${error.message}`);
    } finally {
      elements.sendBtn.disabled = false;
    }
  }

  function handleUiError(error) {
    pushDebug(`[ui-error] ${error.message}`);
    window.alert(`ChatbotUI error: ${error.message}`);
  }

  elements.sendBtn.addEventListener("click", function () {
    sendMessage().catch(handleUiError);
  });
  elements.newChatBtn.addEventListener("click", function () {
    createConversation().catch(handleUiError);
  });
  elements.clearChatBtn.addEventListener("click", function () {
    removeConversation().catch(handleUiError);
  });
  elements.messageInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage().catch(handleUiError);
    }
  });

  if (elements.clearDebugBtn) {
    elements.clearDebugBtn.addEventListener("click", function () {
      state.debugLines = [];
      elements.debugLog.textContent = "";
    });
  }

  async function bootstrap() {
    await loadConversations();
    if (state.conversations.length === 0) {
      await createConversation();
      return;
    }
    await loadConversationDetail(state.activeId);
    render();
  }

  bootstrap().catch(handleUiError);
  elements.clearChatBtn.textContent = "Delete";
})();

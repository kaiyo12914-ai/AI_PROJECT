(function () {
  const DEBUG_MODE = document.body.dataset.debugMode === "1";
  const DEFAULT_MODEL_TYPE = document.body.dataset.modelType || "OPENAI";
  const DEFAULT_MODEL_NAME = document.body.dataset.modelName || "";
  const DEFAULT_TEMPERATURE = Number(document.body.dataset.defaultTemperature || "0.3");
  const DEFAULT_TIMEOUT_SEC = Number(document.body.dataset.defaultTimeoutSec || "120");
  const EMPTY_HINT = "開始新的對話，像 Open WebUI 一樣持續累積聊天脈絡。";
  const AUTOSAVE_DELAY_MS = 900;
  const CONFIG_COLLAPSE_KEY = "chatbotui_config_collapsed";
  const renderer = window.ChatbotMarkdownRenderer || { renderMarkdown: (text) => `<p>${String(text || "")}</p>` };

  const elements = {
    conversationList: document.getElementById("conversationList"),
    messageLog: document.getElementById("messageLog"),
    messageInput: document.getElementById("messageInput"),
    sendBtn: document.getElementById("sendBtn"),
    newChatBtn: document.getElementById("newChatBtn"),
    conversationSearchInput: document.getElementById("conversationSearchInput"),
    clearChatBtn: document.getElementById("clearChatBtn"),
    regenBtn: document.getElementById("regenBtn"),
    modelTypeSelect: document.getElementById("modelTypeSelect"),
    modelNameSelect: document.getElementById("modelNameSelect"),
    chatTitle: document.getElementById("chatTitle"),
    modelBadge: document.getElementById("modelBadge"),
    debugPanel: document.getElementById("debugPanel"),
    debugLog: document.getElementById("debugLog"),
    clearDebugBtn: document.getElementById("clearDebugBtn"),
    contextMenu: document.getElementById("conversationContextMenu"),
    attachmentInput: document.getElementById("attachmentInput"),
    attachmentUploadBtn: document.getElementById("attachmentUploadBtn"),
    attachmentStatus: document.getElementById("attachmentStatus"),
    attachmentList: document.getElementById("attachmentList"),
    conversationConfig: document.getElementById("conversationConfig"),
    configBody: document.getElementById("configBody"),
    toggleConfigBtn: document.getElementById("toggleConfigBtn"),
    temperatureInput: document.getElementById("temperatureInput"),
    timeoutInput: document.getElementById("timeoutInput"),
    systemPromptInput: document.getElementById("systemPromptInput"),
    chatModeSelect: document.getElementById("chatModeSelect"),
    ragSourceSelect: document.getElementById("ragSourceSelect"),
    saveConfigBtn: document.getElementById("saveConfigBtn"),
    resetProfileConfigBtn: document.getElementById("resetProfileConfigBtn"),
    configSaveStatus: document.getElementById("configSaveStatus"),
    refreshPromptHistoryBtn: document.getElementById("refreshPromptHistoryBtn"),
    promptHistoryList: document.getElementById("promptHistoryList"),
    toggleDebugBtn: document.getElementById("toggleDebugBtn"),
  };

  const state = {
    conversations: [],
    activeId: "",
    debugLines: [],
    sending: false,
    contextConversationId: "",
    conversationSearch: "",
    autosaveTimer: null,
    configCollapsed: false,
  };

  function url(path) {
    if (window.apiurl) return window.apiurl(path);
    const base = document.body.dataset.baseUrl || "";
    return `${base}${path}`;
  }

  function pushDebug(line) {
    if (!DEBUG_MODE) return;
    state.debugLines.push(line);
    state.debugLines = state.debugLines.slice(-40);
    elements.debugPanel.classList.remove("hidden");
    elements.debugLog.textContent = state.debugLines.join("\n");
  }

  function activeConversation() {
    return state.conversations.find((item) => item.id === state.activeId) || null;
  }

  function messageId(message) {
    const n = Number(message && message.id ? message.id : 0);
    return Number.isFinite(n) ? n : 0;
  }

  function normalizeTemperature(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return DEFAULT_TEMPERATURE;
    if (n < 0) return 0;
    if (n > 2) return 2;
    return Math.round(n * 100) / 100;
  }

  function normalizeTimeout(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return DEFAULT_TIMEOUT_SEC;
    if (n < 10) return 10;
    if (n > 600) return 600;
    return Math.round(n);
  }

  function normalizePrompt(value) {
    return String(value || "").trim();
  }

  function displayTitle(value) {
    const text = String(value || "").trim();
    if (!text) return "新對話";
    if (text.toLowerCase() === "new chat") return "新對話";
    return text;
  }

  function getConfigPayloadFromInputs() {
    return {
      temperature: normalizeTemperature(elements.temperatureInput && elements.temperatureInput.value),
      timeout_sec: normalizeTimeout(elements.timeoutInput && elements.timeoutInput.value),
      system_prompt: normalizePrompt(elements.systemPromptInput && elements.systemPromptInput.value),
      chat_mode: elements.chatModeSelect ? elements.chatModeSelect.value : "GENERAL",
      rag_source: elements.ragSourceSelect ? elements.ragSourceSelect.value : "",
    };
  }

  function setConfigStatus(text, isError) {
    if (!elements.configSaveStatus) return;
    elements.configSaveStatus.textContent = text || "";
    elements.configSaveStatus.style.color = isError ? "#ff9c9c" : "#9fb3cb";
  }

  function setAttachmentStatus(text, isError) {
    if (!elements.attachmentStatus) return;
    elements.attachmentStatus.textContent = text || "";
    elements.attachmentStatus.style.color = isError ? "#ff9c9c" : "#9fb3cb";
  }

  function clearAutosaveTimer() {
    if (state.autosaveTimer) {
      window.clearTimeout(state.autosaveTimer);
      state.autosaveTimer = null;
    }
  }

  function scheduleConfigAutosave() {
    const current = activeConversation();
    if (!current || state.sending) return;
    clearAutosaveTimer();
    setConfigStatus("偵測到變更，等待自動儲存...", false);
    state.autosaveTimer = window.setTimeout(function () {
      saveConversationConfig({ manual: false }).catch(handleUiError);
    }, AUTOSAVE_DELAY_MS);
  }

  function setConfigCollapsed(collapsed) {
    state.configCollapsed = Boolean(collapsed);
    if (elements.conversationConfig) {
      elements.conversationConfig.classList.toggle("is-collapsed", state.configCollapsed);
    }
    if (elements.toggleConfigBtn) {
      elements.toggleConfigBtn.setAttribute("aria-expanded", state.configCollapsed ? "false" : "true");
      elements.toggleConfigBtn.setAttribute("title", state.configCollapsed ? "Open settings" : "Close settings");
    }
    try {
      localStorage.setItem(CONFIG_COLLAPSE_KEY, state.configCollapsed ? "1" : "0");
    } catch (_err) {
      // ignore localStorage errors
    }
  }

  async function apiFetch(path, options) {
    const response = await fetch(url(path), options);
    const contentType = String(response.headers.get("content-type") || "").toLowerCase();
    const rawText = await response.text();
    const isJson = contentType.includes("application/json");
    let data = null;

    if (isJson) {
      try {
        data = rawText ? JSON.parse(rawText) : {};
      } catch (_err) {
        throw new Error(`API JSON 解析失敗（HTTP ${response.status}）`);
      }
    } else {
      const snippet = String(rawText || "").trim().slice(0, 120).replace(/\s+/g, " ");
      throw new Error(`API 返回非 JSON（HTTP ${response.status}，content-type=${contentType || "unknown"}）：${snippet}`);
    }

    if (!response.ok || !data.ok) {
      throw new Error(data.detail || data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(String(text || ""));
      if (button) {
        const original = button.textContent;
        button.textContent = "已複製";
        window.setTimeout(function () {
          button.textContent = original;
        }, 1200);
      }
    } catch (error) {
      pushDebug(`[複製失敗] ${error.message}`);
    }
  }

  function resolveModelName(modelType) {
    const t = String(modelType || "").toUpperCase();
    if (t === "GOOGLE") return document.body.dataset.modelGoogle || "";
    if (t === "OPENAI") return document.body.dataset.modelOpenai || "";
    if (t === "LM_STUDIO") return document.body.dataset.modelLmstudio || "";
    if (t === "OLLAMA") return document.body.dataset.modelOllama || "";
    return "";
  }

  async function loadConversations() {
    const data = await apiFetch("/chatbotui/conversations/", { method: "GET" });
    state.conversations = (data.conversations || []).map(function (item) {
      return {
        id: item.id,
        title: displayTitle(item.title),
        model_type: item.model_type || DEFAULT_MODEL_TYPE,
        model_name: "",
        temperature: normalizeTemperature(item.temperature),
        timeout_sec: normalizeTimeout(item.timeout_sec),
        system_prompt: normalizePrompt(item.system_prompt),
        prompt_history: [],
        attachments: [],
        message_count: Number(item.message_count || 0),
        preview: item.preview || "",
        messages: [],
      };
    });
    if (!state.activeId && state.conversations.length > 0) {
      state.activeId = state.conversations[0].id;
    }
  }

  async function loadConversationDetail(conversationId) {
    const data = await apiFetch(`/chatbotui/conversations/${conversationId}/`, { method: "GET" });
    const detail = data.conversation || {};
    const target = state.conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.title = displayTitle(detail.title);
    target.model_type = detail.model_type || DEFAULT_MODEL_TYPE;
    target.model_name = detail.model_name || "";
    target.temperature = normalizeTemperature(detail.temperature);
    target.timeout_sec = normalizeTimeout(detail.timeout_sec);
    target.system_prompt = normalizePrompt(detail.system_prompt);
    target.messages = Array.isArray(detail.messages) ? detail.messages : [];
    target.attachments = Array.isArray(detail.attachments) ? detail.attachments : [];
    target.message_count = target.messages.length;
    if (target.message_count === 0) {
      target.model_type = DEFAULT_MODEL_TYPE;
      target.model_name = DEFAULT_MODEL_NAME || "";
      target.temperature = DEFAULT_TEMPERATURE;
      target.timeout_sec = DEFAULT_TIMEOUT_SEC;
      target.system_prompt = "";
      target.chat_mode = "GENERAL";
      target.rag_source = "";
    }
    target.preview = target.messages.length ? String(target.messages[target.messages.length - 1].content || "").slice(0, 80) : "";
  }

  async function loadPromptHistory(conversationId) {
    const data = await apiFetch(`/chatbotui/conversations/${conversationId}/prompt-history/?limit=20`, { method: "GET" });
    const target = state.conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.prompt_history = Array.isArray(data.history) ? data.history : [];
  }

  async function loadConversationAttachments(conversationId) {
    const data = await apiFetch(`/chatbotui/conversations/${conversationId}/attachments/?limit=20`, { method: "GET" });
    const target = state.conversations.find((item) => item.id === conversationId);
    if (!target) return;
    target.attachments = Array.isArray(data.attachments) ? data.attachments : [];
  }

  async function restorePromptHistory(historyId) {
    const current = activeConversation();
    if (!current || state.sending) return;
    const data = await apiFetch(`/chatbotui/conversations/${current.id}/prompt-history/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history_id: historyId }),
    });
    const updated = data.conversation || {};
    current.model_type = updated.model_type || current.model_type || DEFAULT_MODEL_TYPE;
    current.model_name = updated.model_name || current.model_name || "";
    current.temperature = normalizeTemperature(updated.temperature);
    current.timeout_sec = normalizeTimeout(updated.timeout_sec);
    current.system_prompt = normalizePrompt(updated.system_prompt);
    await loadPromptHistory(current.id);
    setConfigStatus("已從歷史版本還原", false);
    render();
  }

  async function createConversation() {
    const data = await apiFetch("/chatbotui/conversations/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "新對話", model_type: DEFAULT_MODEL_TYPE }),
    });
    const conversation = data.conversation || {};
    state.conversations.unshift({
      id: conversation.id,
      title: displayTitle(conversation.title),
      model_type: conversation.model_type || DEFAULT_MODEL_TYPE,
      model_name: conversation.model_name || "",
      temperature: normalizeTemperature(conversation.temperature),
      timeout_sec: normalizeTimeout(conversation.timeout_sec),
      system_prompt: normalizePrompt(conversation.system_prompt),
      chat_mode: conversation.chat_mode || "GENERAL",
      rag_source: conversation.rag_source || "",
      prompt_history: [],
      attachments: [],
      preview: "",
      messages: Array.isArray(conversation.messages) ? conversation.messages : [],
    });
    state.activeId = conversation.id;
    render();
    elements.messageInput.focus();
  }

  async function removeConversation(conversationId) {
    const id = conversationId || (activeConversation() && activeConversation().id) || "";
    if (!id) return;
    const target = state.conversations.find((item) => item.id === id) || null;
    const title = target ? displayTitle(target.title) : "目前對話";
    if (!window.confirm(`確定刪除「${title}」？對話紀錄與 RAG 索引會同步刪除。`)) return;
    await apiFetch(`/chatbotui/conversations/${id}/`, { method: "DELETE" });
    state.conversations = state.conversations.filter((item) => item.id !== id);
    if (state.activeId === id) {
      state.activeId = state.conversations.length ? state.conversations[0].id : "";
    }
    if (state.activeId) {
      await loadConversationDetail(state.activeId);
      await loadPromptHistory(state.activeId);
      await loadConversationAttachments(state.activeId);
    } else {
      await createConversation();
    }
    render();
  }

  async function renameConversationById(conversationId) {
    const target = state.conversations.find((item) => item.id === conversationId);
    if (!target) return;
    const nextTitle = window.prompt("請輸入新的對話名稱", displayTitle(target.title));
    if (nextTitle === null) return;
    const title = String(nextTitle || "").trim();
    if (!title) return;
    const data = await apiFetch(`/chatbotui/conversations/${conversationId}/rename/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title }),
    });
    target.title = (data.conversation && data.conversation.title) || title;
    render();
  }

  async function changeConversationModel(newType, newName) {
    const current = activeConversation();
    if (!current) return;
    const nextModelType = newType || (elements.modelTypeSelect ? elements.modelTypeSelect.value : DEFAULT_MODEL_TYPE);
    const nextModelName = newName || (elements.modelNameSelect ? elements.modelNameSelect.value : "");
    const data = await apiFetch(`/chatbotui/conversations/${current.id}/model/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model_type: nextModelType, model_name: nextModelName }),
    });
    const updated = data.conversation || {};
    current.model_type = updated.model_type || current.model_type || DEFAULT_MODEL_TYPE;
    current.model_name = updated.model_name || current.model_name || "";
    render();
  }

  let ollamaModels = [];
  let lmStudioModels = [];
  const googleModels = String(document.body.dataset.modelGoogleOptions || "")
    .split("|")
    .map((x) => String(x || "").trim())
    .filter(Boolean);
  const openaiModels = String(document.body.dataset.modelOpenaiOptions || "")
    .split("|")
    .map((x) => String(x || "").trim())
    .filter(Boolean);

  function supportsModelNameSelection(modelType) {
    const t = String(modelType || "").toUpperCase();
    return t === "OLLAMA" || t === "LM_STUDIO" || t === "GOOGLE" || t === "OPENAI";
  }

  function hasModelTypeOption(modelType) {
    const t = String(modelType || "").toUpperCase();
    if (!elements.modelTypeSelect) return false;
    return Array.from(elements.modelTypeSelect.options || []).some((opt) => String(opt.value || "").toUpperCase() === t);
  }

  function fillModelNameSelect(models, selectedValue) {
    if (!elements.modelNameSelect) return;
    const list = Array.isArray(models) ? models.filter(Boolean) : [];
    elements.modelNameSelect.innerHTML = "";
    list.forEach(function (m) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      elements.modelNameSelect.appendChild(opt);
    });
    if (list.includes(selectedValue)) {
      elements.modelNameSelect.value = selectedValue;
    } else if (list.length > 0) {
      elements.modelNameSelect.value = list[0];
    } else {
      elements.modelNameSelect.value = "";
    }
  }

  async function loadOllamaModels() {
    try {
      const data = await apiFetch(`/chatbotui/ollama/tags/`, { method: "GET" });
      if (data && data.models) {
        ollamaModels = data.models;
      }
    } catch (e) {
      console.warn("Failed to load OLLAMA models", e);
    }
  }

  async function loadLmStudioModels() {
    try {
      const data = await apiFetch(`/chatbotui/lmstudio/models/`, { method: "GET" });
      if (data && data.models) {
        lmStudioModels = data.models;
      }
    } catch (e) {
      console.warn("Failed to load LM_STUDIO models", e);
    }
  }

  async function ensureModelOptionsForType(modelType) {
    const t = String(modelType || "").toUpperCase();
    const fallback = resolveModelName(t);
    if (t === "GOOGLE") {
      return googleModels.length ? googleModels : (fallback ? [fallback] : []);
    }
    if (t === "OPENAI") {
      return openaiModels.length ? openaiModels : (fallback ? [fallback] : []);
    }
    if (t === "OLLAMA") {
      if (!ollamaModels.length) await loadOllamaModels();
      return ollamaModels.length ? ollamaModels : (fallback ? [fallback] : []);
    }
    if (t === "LM_STUDIO") {
      if (!lmStudioModels.length) await loadLmStudioModels();
      return lmStudioModels.length ? lmStudioModels : (fallback ? [fallback] : []);
    }
    return [];
  }

  async function saveConversationConfig(options) {
    const current = activeConversation();
    if (!current || state.sending) return;
    const opts = options || {};
    const payload = getConfigPayloadFromInputs();
    const selectedModelType = elements.modelTypeSelect ? String(elements.modelTypeSelect.value || "") : "";
    const selectedModelName = elements.modelNameSelect ? String(elements.modelNameSelect.value || "") : "";
    const currentModelType = String(current.model_type || DEFAULT_MODEL_TYPE || "");
    const currentModelName = String(current.model_name || "");
    const modelChanged = (
      selectedModelType &&
      (selectedModelType !== currentModelType || (selectedModelName && selectedModelName !== currentModelName))
    );
    const noChange = (
      payload.temperature === normalizeTemperature(current.temperature) &&
      payload.timeout_sec === normalizeTimeout(current.timeout_sec) &&
      payload.system_prompt === normalizePrompt(current.system_prompt)
    );
    if (modelChanged) {
      await changeConversationModel(selectedModelType, selectedModelName);
    }
    if (noChange) {
      if (opts.manual) setConfigStatus(modelChanged ? "Model setting saved" : "沒有可儲存的變更", false);
      return;
    }

    clearAutosaveTimer();
    setConfigStatus("儲存中...", false);
    const data = await apiFetch(`/chatbotui/conversations/${current.id}/config/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const updated = data.conversation || {};
    current.model_type = updated.model_type || current.model_type || DEFAULT_MODEL_TYPE;
    current.model_name = updated.model_name || current.model_name || "";
    current.temperature = normalizeTemperature(updated.temperature);
    current.timeout_sec = normalizeTimeout(updated.timeout_sec);
    current.system_prompt = normalizePrompt(updated.system_prompt);
    current.chat_mode = updated.chat_mode || "GENERAL";
    current.rag_source = updated.rag_source || "";
    await loadPromptHistory(current.id);
    setConfigStatus("已儲存", false);
    pushDebug(`[設定已儲存] 對話=${current.id} 溫度=${current.temperature} 逾時=${current.timeout_sec}`);
    render();
  }

  async function resetConversationConfigToProfile() {
    const current = activeConversation();
    if (!current || state.sending) return;
    setConfigStatus("正在恢復個人預設...", false);
    const data = await apiFetch(`/chatbotui/conversations/${current.id}/config/reset-profile/`, {
      method: "POST",
    });
    const updated = data.conversation || {};
    current.model_type = updated.model_type || current.model_type || DEFAULT_MODEL_TYPE;
    current.model_name = updated.model_name || current.model_name || "";
    current.temperature = normalizeTemperature(updated.temperature);
    current.timeout_sec = normalizeTimeout(updated.timeout_sec);
    current.system_prompt = normalizePrompt(updated.system_prompt);
    current.chat_mode = updated.chat_mode || "GENERAL";
    current.rag_source = updated.rag_source || "";
    await loadPromptHistory(current.id);
    setConfigStatus("已恢復環境預設", false);
    render();
  }

  async function uploadAttachment(file) {
    const current = activeConversation();
    if (!current || !file) return;
    const formData = new FormData();
    formData.append("file", file);
    setAttachmentStatus("上傳中...", false);
    const data = await apiFetch(`/chatbotui/conversations/${current.id}/attachments/`, {
      method: "POST",
      body: formData,
    });
    const item = data.attachment || null;
    if (item) {
      current.attachments = [item].concat(Array.isArray(current.attachments) ? current.attachments : []);
    }
    await loadConversationAttachments(current.id);
    setAttachmentStatus("附件已上傳", false);
    render();
  }

  async function removeAttachment(attachmentId) {
    const current = activeConversation();
    if (!current || state.sending) return;
    try {
      await apiFetch(`/chatbotui/conversations/${current.id}/attachments/?attachment_id=${attachmentId}`, {
        method: "DELETE",
      });
      await loadConversationAttachments(current.id);
      setAttachmentStatus("附件已刪除", false);
      render();
    } catch (error) {
      handleUiError(error);
    }
  }

  function openContextMenu(conversationId, x, y) {
    if (!elements.contextMenu) return;
    state.contextConversationId = conversationId;
    elements.contextMenu.classList.remove("hidden");
    elements.contextMenu.style.left = `${x}px`;
    elements.contextMenu.style.top = `${y}px`;
  }

  function closeContextMenu() {
    if (!elements.contextMenu) return;
    elements.contextMenu.classList.add("hidden");
    state.contextConversationId = "";
  }

  async function setActiveConversation(id) {
    clearAutosaveTimer();
    state.activeId = id;
    const current = activeConversation();
    if (current) {
      if (current.messages.length === 0) {
        await loadConversationDetail(id);
      }
      await loadPromptHistory(id);
      await loadConversationAttachments(id);
    }
    setConfigStatus("", false);
    setAttachmentStatus("", false);
    render();
  }

  function renderConversationList() {
    elements.conversationList.innerHTML = "";
    const query = String(state.conversationSearch || "").trim().toLowerCase();
    const rows = state.conversations.filter(function (item) {
      if (!query) return true;
      const title = displayTitle(item.title).toLowerCase();
      const preview = String(item.preview || "").toLowerCase();
      return title.includes(query) || preview.includes(query);
    });
    if (rows.length === 0) {
      const empty = document.createElement("div");
      empty.className = "conversation-empty";
      empty.textContent = query ? "找不到符合的對話" : "尚無對話";
      elements.conversationList.appendChild(empty);
      return;
    }
    rows.forEach((item) => {
      const row = document.createElement("div");
      row.className = "conversation-row";

      const button = document.createElement("button");
      button.type = "button";
      button.className = `conversation-item${item.id === state.activeId ? " active" : ""}`;
      button.innerHTML = "<span class=\"conversation-title\"></span><span class=\"conversation-preview\"></span>";
      button.querySelector(".conversation-title").textContent = displayTitle(item.title);
      button.querySelector(".conversation-preview").textContent = item.preview || "尚無訊息";
      button.addEventListener("click", function () {
        setActiveConversation(item.id).catch(handleUiError);
      });

      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "conversation-rename-btn";
      renameBtn.title = "重新命名";
      renameBtn.textContent = "改";
      renameBtn.addEventListener("click", function (event) {
        event.stopPropagation();
        renameConversationById(item.id).catch(handleUiError);
      });

      row.addEventListener("contextmenu", function (event) {
        event.preventDefault();
        openContextMenu(item.id, event.clientX, event.clientY);
      });

      row.appendChild(button);
      row.appendChild(renameBtn);
      elements.conversationList.appendChild(row);
    });
  }

  function buildMetaText(message) {
    const parts = [];
    if (message.model_type) parts.push(message.model_type);
    if (message.model_name) parts.push(message.model_name);
    if (message.latency_ms) parts.push(`${message.latency_ms} ms`);
    if (Number(message.prompt_chars || 0) > 0) parts.push(`prompt ${Number(message.prompt_chars || 0)} chars`);
    if (message.attachment_used || Number(message.attachment_count || 0) > 0) parts.push(`附件 ${Number(message.attachment_count || 0)}`);
    if (message.rag_used) parts.push(`RAG 引用 ${Number(message.citation_count || 0)}`);
    else if (String(message.rag_reason || "") === "rag_error") parts.push("RAG 錯誤");
    return parts.join(" | ");
  }

  function applyUsageMetaToLatestAssistant(conversation, meta) {
    if (!conversation || !Array.isArray(conversation.messages) || !meta) return;
    for (let i = conversation.messages.length - 1; i >= 0; i -= 1) {
      const msg = conversation.messages[i];
      if (String(msg.role || "").toLowerCase() !== "assistant") continue;
      msg.attachment_used = Boolean(meta.attachment_used);
      msg.attachment_count = Number(meta.attachment_count || 0);
      msg.rag_used = Boolean(meta.rag_used);
      msg.citation_count = Number(meta.citation_count || 0);
      msg.rag_reason = String(meta.rag_reason || "");
      msg.prompt_chars = Number(meta.prompt_chars || 0);
      msg.citations = Array.isArray(meta.citations) ? meta.citations : [];
      break;
    }
  }

  function renderCitationList(message) {
    const citations = Array.isArray(message.citations) ? message.citations : [];
    if (!citations.length) return null;
    const wrap = document.createElement("div");
    wrap.className = "message-citations";
    const title = document.createElement("div");
    title.className = "message-citations-title";
    title.textContent = "引用來源";
    wrap.appendChild(title);
    citations.forEach(function (c, idx) {
      const row = document.createElement("div");
      row.className = "message-citation-item";
      const ref = String(c.ref || `C${idx + 1}`);
      const sourceTitle = String(c.source_title || "來源");
      const confidence = Number(c.confidence || 0);
      const score = confidence > 0 ? ` (${Math.round(confidence * 100)}%)` : "";
      const url = String(c.source_url || "").trim();
      if (url) {
        const link = document.createElement("a");
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = `${ref} ${sourceTitle}${score}`;
        row.appendChild(link);
      } else {
        row.textContent = `${ref} ${sourceTitle}${score}`;
      }
      wrap.appendChild(row);
    });
    return wrap;
  }

  function renderMessages() {
    const current = activeConversation();
    elements.messageLog.innerHTML = "";
    if (!current || current.messages.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = EMPTY_HINT;
      elements.messageLog.appendChild(empty);
      return;
    }

    current.messages.forEach((message) => {
      const block = document.createElement("article");
      block.className = `message ${message.role}${message.pending ? " pending" : ""}`;

      const header = document.createElement("div");
      header.className = "message-head";

      const role = document.createElement("span");
      role.className = "message-role";
      role.textContent = message.role === "user" ? "你" : "助理";

      const right = document.createElement("span");
      right.className = "message-head-right";
      const meta = document.createElement("span");
      meta.className = "message-meta";
      meta.textContent = message.pending ? "思考中..." : buildMetaText(message);
      right.appendChild(meta);

      if (message.role === "user" && messageId(message) > 0 && !state.sending) {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "message-action-btn";
        editBtn.textContent = "編輯後重送";
        editBtn.dataset.messageId = String(messageId(message));
        editBtn.dataset.action = "resend";
        right.appendChild(editBtn);
      }
      if (message.role === "assistant" && !message.pending) {
        const copyBtn = document.createElement("button");
        copyBtn.type = "button";
        copyBtn.className = "message-action-btn";
        copyBtn.textContent = "複製回答";
        copyBtn.addEventListener("click", function () {
          const text = String(message.content || "");
          navigator.clipboard.writeText(text).then(function () {
            copyBtn.textContent = "已複製 ✓";
            setTimeout(function () { copyBtn.textContent = "複製回答"; }, 1500);
          }).catch(function () {
            window.alert("複製失敗，請手動選取文字。");
          });
        });
        right.appendChild(copyBtn);
      }
      if (messageId(message) > 0 && !state.sending) {
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "message-action-btn danger";
        deleteBtn.textContent = message.role === "user" ? "刪除此輪" : "刪除回答";
        deleteBtn.dataset.messageId = String(messageId(message));
        deleteBtn.dataset.action = message.role === "user" ? "delete-turn" : "delete-answer";
        right.appendChild(deleteBtn);
      }

      header.appendChild(role);
      header.appendChild(right);

      const body = document.createElement("div");
      body.className = "message-body";
      body.innerHTML = renderer.renderMarkdown(message.content || "");

      block.appendChild(header);
      block.appendChild(body);
      const citationsNode = renderCitationList(message);
      if (citationsNode) block.appendChild(citationsNode);
      elements.messageLog.appendChild(block);
    });

    elements.messageLog.scrollTop = elements.messageLog.scrollHeight;
  }

  function renderPromptHistory() {
    if (!elements.promptHistoryList) return;
    const current = activeConversation();
    elements.promptHistoryList.innerHTML = "";
    if (!current || !Array.isArray(current.prompt_history) || current.prompt_history.length === 0) {
      const empty = document.createElement("div");
      empty.className = "prompt-history-meta";
      empty.textContent = "尚無提示詞歷史。";
      elements.promptHistoryList.appendChild(empty);
      return;
    }

    current.prompt_history.forEach(function (item) {
      const row = document.createElement("div");
      row.className = "prompt-history-item";

      const left = document.createElement("div");
      const text = document.createElement("div");
      text.className = "prompt-history-text";
      text.textContent = String(item.prompt_text || "").slice(0, 280) || "（空白）";
      const meta = document.createElement("div");
      meta.className = "prompt-history-meta";
      meta.textContent = String(item.created_at || "");
      left.appendChild(text);
      left.appendChild(meta);

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "prompt-restore-btn";
      btn.textContent = "還原";
      btn.dataset.historyId = String(item.id || 0);

      row.appendChild(left);
      row.appendChild(btn);
      elements.promptHistoryList.appendChild(row);
    });
  }

  function renderAttachmentList() {
    if (!elements.attachmentList) return;
    const current = activeConversation();
    elements.attachmentList.innerHTML = "";
    if (!current || !Array.isArray(current.attachments) || current.attachments.length === 0) {
      return;
    }
    current.attachments.forEach(function (item) {
      const tag = document.createElement("div");
      tag.className = "attachment-item";
      
      const textSpan = document.createElement("span");
      const name = String(item.filename || "attachment");
      const size = Number(item.size_bytes || 0);
      textSpan.textContent = `${name} (${size} bytes)`;
      
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "attachment-del-btn";
      delBtn.textContent = "✖";
      delBtn.onclick = () => removeAttachment(item.id);
      
      tag.appendChild(textSpan);
      tag.appendChild(delBtn);
      elements.attachmentList.appendChild(tag);
    });
  }

  function render() {
    const current = activeConversation();
    elements.chatTitle.textContent = current ? displayTitle(current.title) : "新對話";
    if (elements.modelBadge) {
      elements.modelBadge.textContent = `目前 ${current ? current.model_type || "UNKNOWN" : "UNKNOWN"}${current && current.model_name ? ' | ' + current.model_name : ''}`;
    }

    if (elements.modelTypeSelect && current) {
      elements.modelTypeSelect.value = current.model_type || DEFAULT_MODEL_TYPE;
      elements.modelTypeSelect.disabled = state.sending;
    }
    if (elements.modelNameSelect) {
      if (current && supportsModelNameSelection(current.model_type)) {
        elements.modelNameSelect.style.display = "inline-block";
        const mt = String(current.model_type).toUpperCase();
        const sourceModels = mt === "LM_STUDIO"
          ? lmStudioModels
          : mt === "OLLAMA"
            ? ollamaModels
            : mt === "GOOGLE"
              ? googleModels
              : openaiModels;
        fillModelNameSelect(sourceModels, current.model_name || resolveModelName(current.model_type));
      } else {
        elements.modelNameSelect.style.display = "none";
      }
    }
    
    if (elements.temperatureInput) {
      const value = current ? normalizeTemperature(current.temperature) : DEFAULT_TEMPERATURE;
      elements.temperatureInput.value = String(value);
      elements.temperatureInput.disabled = state.sending || !current;
    }
    if (elements.timeoutInput) {
      const value = current ? normalizeTimeout(current.timeout_sec) : DEFAULT_TIMEOUT_SEC;
      elements.timeoutInput.value = String(value);
      elements.timeoutInput.disabled = state.sending || !current;
    }
    if (elements.systemPromptInput) {
      const value = current ? normalizePrompt(current.system_prompt) : "";
      elements.systemPromptInput.value = value;
      elements.systemPromptInput.disabled = state.sending || !current;
    }
    if (elements.chatModeSelect) {
      const value = current ? (current.chat_mode || "GENERAL") : "GENERAL";
      elements.chatModeSelect.value = value;
      elements.chatModeSelect.disabled = state.sending || !current;
    }
    if (elements.ragSourceSelect) {
      const value = current ? (current.rag_source || "") : "";
      elements.ragSourceSelect.value = value;
      elements.ragSourceSelect.disabled = state.sending || !current;
    }
    
    const initialSelects = [elements.chatModeSelect, elements.ragSourceSelect, elements.modelTypeSelect, elements.modelNameSelect];
    initialSelects.forEach(el => { if(el) el.disabled = state.sending || !current; });

    if (elements.saveConfigBtn) {
      elements.saveConfigBtn.disabled = state.sending || !current;
    }
    if (elements.resetProfileConfigBtn) {
      elements.resetProfileConfigBtn.disabled = state.sending || !current;
    }
    if (elements.refreshPromptHistoryBtn) {
      elements.refreshPromptHistoryBtn.disabled = state.sending || !current;
    }
    if (elements.attachmentUploadBtn) {
      elements.attachmentUploadBtn.disabled = state.sending || !current;
    }
    if (elements.attachmentInput) {
      elements.attachmentInput.disabled = state.sending || !current;
    }

    elements.sendBtn.disabled = state.sending;
    elements.regenBtn.disabled = state.sending;
    elements.messageInput.disabled = state.sending;

    renderConversationList();
    renderMessages();
    renderPromptHistory();
    renderAttachmentList();
  }

  async function sendMessage() {
    const current = activeConversation();
    if (!current || state.sending) return;

    const text = elements.messageInput.value.trim();
    if (!text) return;

    state.sending = true;
    current.messages.push({ id: `temp-user-${Date.now()}`, role: "user", content: text, model_type: current.model_type || DEFAULT_MODEL_TYPE, latency_ms: 0 });
    current.messages.push({
      id: `temp-assistant-${Date.now()}`,
      role: "assistant",
      content: "產生回覆中...",
      model_type: current.model_type || DEFAULT_MODEL_TYPE,
      model_name: current.model_name || "",
      latency_ms: 0,
      pending: true,
    });
    current.preview = text.slice(0, 80);
    elements.messageInput.value = "";
    render();

    pushDebug(`[送出請求] 對話=${current.id} 模型=${current.model_type || DEFAULT_MODEL_TYPE} 字數=${text.length}`);
    try {
      const data = await apiFetch("/chatbotui/chat/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: current.id,
          model_type: current.model_type || DEFAULT_MODEL_TYPE,
          model_name: current.model_name || DEFAULT_MODEL_NAME || "",
          message: text,
        }),
      });
      current.title = displayTitle(data.conversation_title || current.title);
      current.model_type = data.meta && data.meta.model_type ? data.meta.model_type : (current.model_type || DEFAULT_MODEL_TYPE);
      current.model_name = data.meta && data.meta.model_name ? data.meta.model_name : current.model_name;
      current.temperature = normalizeTemperature(data.meta && data.meta.temperature);
      current.timeout_sec = normalizeTimeout(data.meta && data.meta.timeout_sec);
      await loadConversationDetail(current.id);
      applyUsageMetaToLatestAssistant(current, data.meta || {});
      render();
      pushDebug(`[回應成功] 模型=${current.model_type} 延遲毫秒=${data.meta && data.meta.latency_ms ? data.meta.latency_ms : 0}`);
    } catch (error) {
      current.messages = current.messages.filter((m) => !String(m.id || "").startsWith("temp-"));
      current.messages.push({
        id: `temp-error-${Date.now()}`,
        role: "assistant",
        content: `系統錯誤：${error.message}`,
        model_type: current.model_type || DEFAULT_MODEL_TYPE,
        latency_ms: 0,
      });
      render();
      pushDebug(`[錯誤] ${error.message}`);
    } finally {
      state.sending = false;
      render();
      elements.messageInput.focus();
    }
  }

  async function regenerateReply() {
    const current = activeConversation();
    if (!current || state.sending) return;
    state.sending = true;
    render();
    pushDebug(`[重新生成請求] 對話=${current.id} 模型=${current.model_type || DEFAULT_MODEL_TYPE}`);
    try {
      const data = await apiFetch("/chatbotui/chat/regenerate/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: current.id,
          model_type: current.model_type || DEFAULT_MODEL_TYPE,
        }),
      });
      current.title = displayTitle(data.conversation_title || current.title);
      current.model_type = data.meta && data.meta.model_type ? data.meta.model_type : (current.model_type || DEFAULT_MODEL_TYPE);
      current.model_name = data.meta && data.meta.model_name ? data.meta.model_name : current.model_name;
      current.temperature = normalizeTemperature(data.meta && data.meta.temperature);
      current.timeout_sec = normalizeTimeout(data.meta && data.meta.timeout_sec);
      await loadConversationDetail(current.id);
      applyUsageMetaToLatestAssistant(current, data.meta || {});
      render();
      pushDebug(`[重新生成成功] 模型=${current.model_type} 延遲毫秒=${data.meta && data.meta.latency_ms ? data.meta.latency_ms : 0}`);
    } catch (error) {
      pushDebug(`[重新生成失敗] ${error.message}`);
      handleUiError(error);
    } finally {
      state.sending = false;
      render();
    }
  }

  async function resendFromMessage(messageIdValue) {
    const current = activeConversation();
    if (!current || state.sending) return;
    const message = current.messages.find((m) => messageId(m) === messageIdValue && String(m.role).toLowerCase() === "user");
    if (!message) {
      handleUiError(new Error("找不到要重送的使用者訊息"));
      return;
    }
    const edited = window.prompt("請先編輯訊息再重送", String(message.content || ""));
    if (edited === null) return;
    const text = String(edited || "").trim();
    if (!text) return;

    state.sending = true;
    render();
    pushDebug(`[重送請求] 對話=${current.id} 目標訊息=${messageIdValue}`);
    try {
      const data = await apiFetch("/chatbotui/chat/resend/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: current.id,
          target_message_id: messageIdValue,
          model_type: current.model_type || DEFAULT_MODEL_TYPE,
          message: text,
        }),
      });
      current.title = displayTitle(data.conversation_title || current.title);
      current.model_type = data.meta && data.meta.model_type ? data.meta.model_type : (current.model_type || DEFAULT_MODEL_TYPE);
      current.model_name = data.meta && data.meta.model_name ? data.meta.model_name : current.model_name;
      current.temperature = normalizeTemperature(data.meta && data.meta.temperature);
      current.timeout_sec = normalizeTimeout(data.meta && data.meta.timeout_sec);
      await loadConversationDetail(current.id);
      applyUsageMetaToLatestAssistant(current, data.meta || {});
      render();
      pushDebug(`[重送成功] 模型=${current.model_type} 延遲毫秒=${data.meta && data.meta.latency_ms ? data.meta.latency_ms : 0}`);
    } catch (error) {
      pushDebug(`[重送失敗] ${error.message}`);
      handleUiError(error);
    } finally {
      state.sending = false;
      render();
    }
  }

  function handleUiError(error) {
    const rawMessage = String((error && error.message) || error || "");
    const lower = rawMessage.toLowerCase();
    const isTimeout = lower.includes("request timed out") || lower.includes("timed out") || lower.includes("timeout") || lower.includes("deadline exceeded");
    const userMessage = isTimeout
      ? "系統逾時，請另開新對話後再試。"
      : `系統錯誤：${rawMessage}`;
    setConfigStatus(isTimeout ? "系統逾時，建議另開新對話。" : `儲存失敗：${rawMessage}`, true);
    setAttachmentStatus(isTimeout ? "系統逾時，建議另開新對話。" : `附件操作失敗：${rawMessage}`, true);
    pushDebug(`[介面錯誤] ${rawMessage}`);
    window.alert(userMessage);
  }

  async function deleteMessageUnit(messageIdValue, scope) {
    const current = activeConversation();
    if (!current || state.sending) return;
    const target = current.messages.find((m) => messageId(m) === messageIdValue);
    if (!target) {
      handleUiError(new Error("找不到要刪除的訊息"));
      return;
    }
    const label = scope === "answer" ? "這則回答" : "這一輪對話與回答";
    if (!window.confirm(`確定刪除${label}？相關 RAG 索引會同步刪除。`)) return;

    state.sending = true;
    render();
    pushDebug(`[刪除訊息] 對話=${current.id} 訊息=${messageIdValue} scope=${scope}`);
    try {
      await apiFetch(`/chatbotui/conversations/${current.id}/messages/delete/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message_id: messageIdValue,
          scope: scope,
        }),
      });
      await loadConversationDetail(current.id);
      render();
    } catch (error) {
      pushDebug(`[刪除訊息失敗] ${error.message}`);
      handleUiError(error);
    } finally {
      state.sending = false;
      render();
    }
  }

  elements.sendBtn.addEventListener("click", function () {
    sendMessage().catch(handleUiError);
  });
  elements.newChatBtn.addEventListener("click", function () {
    createConversation().catch(handleUiError);
  });
  if (elements.conversationSearchInput) {
    elements.conversationSearchInput.addEventListener("input", function () {
      state.conversationSearch = elements.conversationSearchInput.value || "";
      renderConversationList();
    });
  }
  elements.regenBtn.addEventListener("click", function () {
    regenerateReply().catch(handleUiError);
  });
  if (elements.modelTypeSelect) {
    elements.modelTypeSelect.addEventListener("change", async function () {
      const selectedType = elements.modelTypeSelect.value;
      if (supportsModelNameSelection(selectedType)) {
        const options = await ensureModelOptionsForType(selectedType);
        elements.modelNameSelect.style.display = "inline-block";
        fillModelNameSelect(options, resolveModelName(selectedType));
      } else {
        elements.modelNameSelect.style.display = "none";
      }
      setConfigStatus("模型設定已變更，請按「儲存設定」", false);
    });
  }
  if (elements.modelNameSelect) {
    elements.modelNameSelect.addEventListener("change", function () {
      setConfigStatus("模型設定已變更，請按「儲存設定」", false);
    });
  }
  if (elements.saveConfigBtn) {
    elements.saveConfigBtn.addEventListener("click", function () {
      saveConversationConfig({ manual: true }).catch(handleUiError);
    });
  }
  if (elements.resetProfileConfigBtn) {
    elements.resetProfileConfigBtn.addEventListener("click", function () {
      resetConversationConfigToProfile().catch(handleUiError);
    });
  }
  if (elements.toggleConfigBtn) {
    elements.toggleConfigBtn.addEventListener("click", function () {
      setConfigCollapsed(!state.configCollapsed);
    });
  }
  if (elements.refreshPromptHistoryBtn) {
    elements.refreshPromptHistoryBtn.addEventListener("click", function () {
      const current = activeConversation();
      if (!current) return;
      loadPromptHistory(current.id).then(render).catch(handleUiError);
    });
  }
  if (elements.attachmentUploadBtn && elements.attachmentInput) {
    elements.attachmentUploadBtn.addEventListener("click", function () {
      elements.attachmentInput.click();
    });
    elements.attachmentInput.addEventListener("change", function (event) {
      const files = event.target && event.target.files ? event.target.files : null;
      const file = files && files.length > 0 ? files[0] : null;
      if (!file) return;
      uploadAttachment(file).catch(handleUiError).finally(function () {
        elements.attachmentInput.value = "";
      });
    });
  }
  if (elements.temperatureInput) {
    elements.temperatureInput.addEventListener("input", scheduleConfigAutosave);
  }
  if (elements.timeoutInput) {
    elements.timeoutInput.addEventListener("input", scheduleConfigAutosave);
  }
  if (elements.systemPromptInput) {
    elements.systemPromptInput.addEventListener("input", scheduleConfigAutosave);
  }
  if (elements.chatModeSelect) {
    elements.chatModeSelect.addEventListener("change", scheduleConfigAutosave);
  }
  if (elements.ragSourceSelect) {
    elements.ragSourceSelect.addEventListener("change", scheduleConfigAutosave);
  }
  if (elements.promptHistoryList) {
    elements.promptHistoryList.addEventListener("click", function (event) {
      const btn = event.target.closest(".prompt-restore-btn");
      if (!btn) return;
      const historyId = Number(btn.dataset.historyId || 0);
      if (historyId > 0) {
        restorePromptHistory(historyId).catch(handleUiError);
      }
    });
  }
  elements.clearChatBtn.addEventListener("click", function () {
    removeConversation().catch(handleUiError);
  });
  elements.messageInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage().catch(handleUiError);
    }
  });
  elements.messageLog.addEventListener("click", function (event) {
    const copyTarget = event.target.closest(".copy-code-btn");
    if (copyTarget) {
      copyText(copyTarget.dataset.copy || "", copyTarget).catch(handleUiError);
      return;
    }

    const actionBtn = event.target.closest(".message-action-btn");
    if (actionBtn) {
      const id = Number(actionBtn.dataset.messageId || 0);
      const action = String(actionBtn.dataset.action || "");
      if (id > 0 && action === "resend") {
        resendFromMessage(id).catch(handleUiError);
      } else if (id > 0 && action === "delete-turn") {
        deleteMessageUnit(id, "turn").catch(handleUiError);
      } else if (id > 0 && action === "delete-answer") {
        deleteMessageUnit(id, "answer").catch(handleUiError);
      }
    }
  });

  if (elements.contextMenu) {
    elements.contextMenu.addEventListener("click", function (event) {
      const actionBtn = event.target.closest("button[data-action]");
      if (!actionBtn) return;
      const action = actionBtn.dataset.action;
      const conversationId = state.contextConversationId;
      closeContextMenu();
      if (!conversationId) return;
      if (action === "rename") {
        renameConversationById(conversationId).catch(handleUiError);
      } else if (action === "delete") {
        removeConversation(conversationId).catch(handleUiError);
      }
    });
    document.addEventListener("click", function () {
      closeContextMenu();
    });
    document.addEventListener("contextmenu", function (event) {
      if (!event.target.closest(".conversation-row")) {
        closeContextMenu();
      }
    });
  }

  if (elements.clearDebugBtn) {
    elements.clearDebugBtn.addEventListener("click", function () {
      state.debugLines = [];
      elements.debugLog.textContent = "";
    });
  }
  if (elements.toggleDebugBtn) {
    elements.toggleDebugBtn.addEventListener("click", function () {
      if (elements.debugLog.style.display === "none") {
        elements.debugLog.style.display = "block";
        elements.debugPanel.classList.remove("is-collapsed");
        elements.toggleDebugBtn.textContent = "收合";
      } else {
        elements.debugLog.style.display = "none";
        elements.debugPanel.classList.add("is-collapsed");
        elements.toggleDebugBtn.textContent = "展開";
      }
    });
  }

  async function bootstrap() {
    try {
      const stored = localStorage.getItem(CONFIG_COLLAPSE_KEY);
      state.configCollapsed = stored === null ? true : stored === "1";
    } catch (_err) {
      state.configCollapsed = true;
    }
    setConfigCollapsed(state.configCollapsed);

    await loadConversations();
    if (state.conversations.length === 0) {
      await createConversation();
      return;
    }
    await loadConversationDetail(state.activeId);
    await loadPromptHistory(state.activeId);
    await loadConversationAttachments(state.activeId);
    await loadOllamaModels();
    if (hasModelTypeOption("LM_STUDIO")) {
      await loadLmStudioModels();
    }
    render();
  }

  bootstrap().catch(handleUiError);
  elements.clearChatBtn.textContent = "刪除";
})();

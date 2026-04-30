(function () {
  "use strict";

  const state = {
    projectId: 0,
    conversationId: 0,
    busy: false,
    pendingAiNode: null,
    canManageProjects: false,
    isManagePage: document.body.dataset.page === "manage",
    conversations: [],
  };

  const els = {
    projectName: document.getElementById("projectName"),
    createProjectBtn: document.getElementById("createProjectBtn"),
    projectSelect: document.getElementById("projectSelect"),
    refreshBtn: document.getElementById("refreshBtn"),
    overviewText: document.getElementById("overviewText"),
    overviewMeta: document.getElementById("overviewMeta"),

    sourceTitle: document.getElementById("sourceTitle"),
    sourceFile: document.getElementById("sourceFile"),
    uploadSourceBtn: document.getElementById("uploadSourceBtn"),
    sourceList: document.getElementById("sourceList"),
    versionMode: document.getElementById("versionMode"),

    chatStatus: document.getElementById("chatStatus"),
    confidencePanel: document.getElementById("confidencePanel"),
    conversationList: document.getElementById("conversationList"),
    newChatBtn: document.getElementById("newChatBtn"),

    chatLog: document.getElementById("chatLog"),
    questionInput: document.getElementById("questionInput"),
    askBtn: document.getElementById("askBtn"),

    citationPanel: document.getElementById("citationPanel"),
    llmPromptPanel: document.getElementById("llmPromptPanel"),
    chunkLogPanel: document.getElementById("chunkLogPanel"),
    auditLogPanel: document.getElementById("auditLogPanel"),
  };

  function bindCollapsibleCards() {
    document.querySelectorAll(".collapsible-header").forEach((header) => {
      if (header.dataset.boundCollapsible === "1") return;
      header.dataset.boundCollapsible = "1";
      header.addEventListener("click", () => {
        const card = header.closest(".collapsible-card");
        if (card) card.classList.toggle("is-collapsed");
      });
    });
  }

  function url(path) {
    if (typeof window.apiurl === "function") return window.apiurl(path);
    return path;
  }

  function escapeHtml(v) {
    return String(v || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setStatus(text, isError) {
    if (!els.chatStatus) return;
    els.chatStatus.textContent = text || "";
    els.chatStatus.style.color = isError ? "#b91c1c" : "#0f766e";
  }

  function setConfidence(_v) {
    if (!els.confidencePanel) return;
    els.confidencePanel.hidden = true;
    els.confidencePanel.textContent = "";
  }

  function setBusy(flag) {
    state.busy = !!flag;
    [
      els.createProjectBtn,
      els.refreshBtn,
      els.uploadSourceBtn,
      els.askBtn,
    ].forEach((btn) => {
      if (btn) btn.disabled = state.busy;
    });
  }


  async function postCitationClick(citationMeta) {
    const meta = citationMeta || {};
    const sourceId = Number(meta.source_id || 0);
    if (!state.projectId || !sourceId) return;
    try {
      await fetch(url("/projectnotes/citation_click/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: state.projectId,
          conversation_id: state.conversationId || 0,
          source_id: sourceId,
          chunk_index: Number(meta.chunk_index || 0),
          ref: String(meta.ref || ""),
          excerpt: String(meta.excerpt || ""),
        }),
      });
    } catch (_e) {
      // Best-effort analytics only.
    }
  }


  function appendPendingAi() {
    removePendingAi();
    if (!els.chatLog) return;
    const row = document.createElement("div");
    row.className = "msg ai pending";
    row.innerHTML = [
      '<span class="spinner-inline" aria-hidden="true">',
      '  <svg class="spinner-svg" viewBox="0 0 24 24" focusable="false">',
      '    <circle class="spinner-track" cx="12" cy="12" r="9"></circle>',
      '    <circle class="spinner-path" cx="12" cy="12" r="9"></circle>',
      "  </svg>",
      "</span>",
      '<span class="pending-text">LLM 思考中...</span>',
    ].join("\n");
    els.chatLog.appendChild(row);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
    state.pendingAiNode = row;
  }

  function removePendingAi() {
    if (state.pendingAiNode && state.pendingAiNode.parentNode) {
      state.pendingAiNode.parentNode.removeChild(state.pendingAiNode);
    }
    state.pendingAiNode = null;
  }

  async function parseJsonSafe(resp) {
    try {
      return await resp.json();
    } catch (_e) {
      return { ok: false, error: `HTTP ${resp.status}` };
    }
  }

  function getCheckedSourceIds() {
    const selected = [];
    document.querySelectorAll(".source-check").forEach((el) => {
      if (el.checked) selected.push(Number(el.value));
    });
    return selected.filter((x) => Number.isFinite(x) && x > 0);
  }

  function setLLMPrompt(text) {
    if (!els.llmPromptPanel) return;
    const v = (text || "").trim();
    els.llmPromptPanel.textContent = v || "No LLM prompt yet.";
  }

  function clearChunkLog() {
    if (!els.chunkLogPanel) return;
    els.chunkLogPanel.textContent = "No CHUNK query log yet.";
  }

  function addRetrievalMsg(citations) {
    if (!els.chunkLogPanel) return;
    // Keep only the latest retrieval record for current turn.
    els.chunkLogPanel.innerHTML = "";

    const row = document.createElement("div");
    row.className = "retrieval-log-row";

    if (!Array.isArray(citations) || citations.length === 0) {
      row.textContent = "No CHUNK query log available.";
      els.chunkLogPanel.appendChild(row);
      els.chunkLogPanel.scrollTop = els.chunkLogPanel.scrollHeight;
      return;
    }

    citations.forEach((c) => {
      const item = document.createElement("div");
      item.className = "retrieval-item";

      const cconf = Number(c.confidence);
      const cconfTxt = Number.isFinite(cconf) ? cconf.toFixed(2) : "--";
      const sourceTitle = c.source_title || "";
      const chunkNo = c.chunk_index;

      const head = document.createElement("div");
      head.className = "retrieval-head";

      const tag = document.createElement("span");
      tag.className = "retrieval-tag";
      tag.textContent = `${c.ref || "C"}(${cconfTxt})#${chunkNo}`;

      const meta = document.createElement("span");
      meta.className = "retrieval-meta";
      meta.textContent = ` ${sourceTitle}#${chunkNo}`;

      head.appendChild(tag);
      head.appendChild(meta);

      const line2 = document.createElement("div");
      line2.className = "retrieval-line2";
      line2.textContent = `${sourceTitle} #${chunkNo}`;

      const excerpt = document.createElement("div");
      excerpt.className = "retrieval-excerpt";
      excerpt.textContent = String(c.excerpt || "");

      item.appendChild(head);
      item.appendChild(line2);
      item.appendChild(excerpt);
      row.appendChild(item);
    });

    els.chunkLogPanel.appendChild(row);
    els.chunkLogPanel.scrollTop = els.chunkLogPanel.scrollHeight;
  }

  function addMsg(role, text, citations, citationTailText) {
    if (!els.chatLog) return;

    const row = document.createElement("div");
    row.className = `msg ${role}`;

    const label = document.createElement("div");
    label.className = "msg-label";
    label.textContent = role === "user" ? "使用者" : "助理";

    const body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = text || "";

    row.appendChild(label);
    row.appendChild(body);
    if (role === "ai") {
      const refs = Array.isArray(citations) ? citations : [];
      const fallbackTail = String(citationTailText || "").trim();
      if (refs.length > 0 || fallbackTail) {
        const tailWrap = document.createElement("div");
        tailWrap.className = "citation-tail";

        const tailTitle = document.createElement("div");
        tailTitle.className = "citation-tail-title";
        tailTitle.textContent = "引用來源詳情";
        tailWrap.appendChild(tailTitle);

        if (refs.length > 0) {
          refs.forEach((c) => {
            const ref = String(c.ref || "C");
            const conf = Number(c.confidence);
            const confText = Number.isFinite(conf) ? conf.toFixed(2) : "--";
            const chunkNo = Number(c.chunk_index);
            const chunkText = Number.isFinite(chunkNo) ? String(chunkNo) : "0";
            const sourceTitle = String(c.source_title || "來源未知");
            const line = document.createElement("div");
            line.className = "citation-bubble-row";
            const bubble = document.createElement("span");
            bubble.className = "citation-bubble";
            bubble.textContent = `${ref}(${confText})#${chunkText} 來自 ${sourceTitle}`;
            bubble.style.cursor = "pointer";
            bubble.title = "Preview citation source";
            bubble.addEventListener("click", () => {
              previewSourceContent(c.source_id, chunkNo, c).catch(() => {});
            });
            line.appendChild(bubble);
            tailWrap.appendChild(line);
          });
        } else {
          const raw = fallbackTail;
          const parts = raw ? [raw] : [];
          parts.forEach((part) => {
            const line = document.createElement("div");
            line.className = "citation-bubble-row";
            const bubble = document.createElement("span");
            bubble.className = "citation-bubble";
            bubble.textContent = part;
            line.appendChild(bubble);
            tailWrap.appendChild(line);
          });
        }
        row.appendChild(tailWrap);
      }
    }

    els.chatLog.appendChild(row);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }

  async function deleteConversation(conversationId) {
    const cid = Number(conversationId || 0);
    if (!cid) return;
    const current = state.conversations.find((row) => Number(row.id) === cid);
    const title = current && current.title ? current.title : `#${cid}`;
    const ok = window.confirm(`Delete conversation ${title}?`);
    if (!ok) return;

    const resp = await fetch(url("/projectnotes/conversations/"), {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: cid,
      }),
    });
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      setStatus(data.error || "Delete failed", true);
      return;
    }

    state.conversations = state.conversations.filter((row) => Number(row.id) !== cid);
    if (Number(state.conversationId) === cid) {
      const next = state.conversations[0];
      if (next) {
        state.conversationId = Number(next.id || 0);
        renderConversationList();
        await loadConversationMessages(state.conversationId);
      } else {
        resetConversationUi();
      }
    } else {
      renderConversationList();
    }
    setStatus("", false);
  }

  async function renameConversation(conversationId) {
    const cid = Number(conversationId || 0);
    if (!cid) return;
    const current = state.conversations.find((row) => Number(row.id) === cid);
    const nextTitle = window.prompt("Rename conversation", current && current.title ? current.title : "");
    if (nextTitle === null) return;

    const title = String(nextTitle || "").trim();
    if (!title) {
      setStatus("Title is required", true);
      return;
    }

    const resp = await fetch(url("/projectnotes/conversations/"), {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: cid,
        title,
      }),
    });
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      setStatus(data.error || "Rename failed", true);
      return;
    }

    const target = state.conversations.find((row) => Number(row.id) === cid);
    if (target) target.title = String((data.conversation && data.conversation.title) || title);
    renderConversationList();
    setStatus("", false);
  }

  function renderConversationList() {
    if (!els.conversationList) return;
    els.conversationList.innerHTML = "";

    const rows = Array.isArray(state.conversations) ? state.conversations : [];
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "conversation-meta";
      empty.textContent = "No conversations yet.";
      els.conversationList.appendChild(empty);
      return;
    }

    rows.forEach((conv) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "conversation-item" + (Number(conv.id) === Number(state.conversationId) ? " active" : "");

      const head = document.createElement("div");
      head.className = "conversation-item-head";

      const title = document.createElement("div");
      title.className = "conversation-title";
      title.textContent = String(conv.title || `Conversation ${conv.id}`);

      const actions = document.createElement("div");

      const renameBtn = document.createElement("button");
      renameBtn.type = "button";
      renameBtn.className = "conversation-rename";
      renameBtn.textContent = "Edit";
      renameBtn.title = "Rename conversation";
      renameBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        renameConversation(conv.id).catch(() => setStatus("Rename failed", true));
      });

      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "conversation-delete";
      deleteBtn.textContent = "Delete";
      deleteBtn.title = "Delete conversation";
      deleteBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        deleteConversation(conv.id).catch(() => setStatus("Delete failed", true));
      });

      actions.appendChild(renameBtn);
      actions.appendChild(deleteBtn);

      head.appendChild(title);
      head.appendChild(actions);

      const meta = document.createElement("div");
      meta.className = "conversation-meta";
      meta.textContent = `${Number(conv.turn_count || 0)} turns`;

      item.appendChild(head);
      item.appendChild(meta);
      item.addEventListener("click", () => {
        loadConversationMessages(conv.id).catch(() => setStatus("Failed to load conversation", true));
      });
      els.conversationList.appendChild(item);
    });
  }

  async function loadConversations(preferredConversationId) {
    if (!state.projectId) {
      state.conversations = [];
      renderConversationList();
      return;
    }

    const resp = await fetch(url(`/projectnotes/conversations/?project_id=${state.projectId}`));
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      state.conversations = [];
      renderConversationList();
      return;
    }

    state.conversations = Array.isArray(data.conversations) ? data.conversations : [];
    const preferredId = Number(preferredConversationId || state.conversationId || 0);
    if (!state.conversations.length) {
      resetConversationUi();
      renderConversationList();
      return;
    }

    const selected = state.conversations.find((row) => Number(row.id) === preferredId) || state.conversations[0];
    state.conversationId = Number(selected.id || 0);
    renderConversationList();
    await loadConversationMessages(state.conversationId);
  }

  async function loadConversationMessages(conversationId) {
    const cid = Number(conversationId || 0);
    if (!cid || !els.chatLog) return;

    const resp = await fetch(url(`/projectnotes/messages/?conversation_id=${cid}`));
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      setStatus(data.error || "Failed to load conversation", true);
      return;
    }

    state.conversationId = Number((data.conversation && data.conversation.id) || cid);
    renderConversationList();
    els.chatLog.innerHTML = "";
    removePendingAi();
    clearChunkLog();
    setLLMPrompt("");
    setConfidence(null);

    const messages = Array.isArray(data.messages) ? data.messages : [];
    messages.forEach((msg) => {
      const role = String(msg.sender_type || "") === "user" ? "user" : "ai";
      addMsg(role, msg.content || "", msg.citations || [], "");
    });
  }

  async function loadLatestConversation() {
    await loadConversations(0);
  }

  function markSourcePreviewing(sourceId) {
    document.querySelectorAll(".source-item").forEach((row) => {
      row.classList.toggle("active-preview", Number(row.dataset.sourceId || 0) === Number(sourceId || 0));
    });
  }

    async function loadAuditLogs() {
    if (!state.isManagePage || !els.auditLogPanel) return;
    const resp = await fetch(url("/projectnotes/audit_logs/"));
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      els.auditLogPanel.textContent = "無法讀取日誌。";
      return;
    }
    const rows = Array.isArray(data.rows) ? data.rows : [];
    if (!rows.length) {
      els.auditLogPanel.textContent = "尚無操作日誌。";
      return;
    }
    els.auditLogPanel.innerHTML = rows.map(r => {
      const dt = r.created_at ? r.created_at.replace("T", " ").split(".")[0] : "-";
      return `<div style="border-bottom:1px solid #eee; padding:4px 0; font-size:12px;">` +
             `[${dt}] <b>${r.user_id}</b>: ${r.action} (${r.target_type}#${r.target_id || ""}) - ${r.status}</div>`;
    }).join("");
  }

  async function loadProjects() {
    const resp = await fetch(url("/projectnotes/projects/"));
    const data = await parseJsonSafe(resp);
    state.canManageProjects = !!data.can_manage_projects;
    if (!data.ok) {
      setStatus(data.error || "讀取專案清單失敗。請稍後再試", true);
      return;
    }

    if (!els.projectSelect) return;
    els.projectSelect.innerHTML = "";

    const visibleProjects = (data.projects || []).filter((p) => state.isManagePage || p.source_count > 0);
    visibleProjects.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.name} (${p.source_count})`;
      els.projectSelect.appendChild(opt);
    });

    if (visibleProjects.length > 0) {
      state.projectId = Number(els.projectSelect.value || visibleProjects[0].id || 0);
      await loadSources();
      await loadOverview();
      await loadConversations(state.conversationId);
      setStatus("讀取專案清單成功", false);
      if (state.isManagePage) loadAuditLogs();
    } else {
      state.projectId = 0;
      await loadSources();
      await loadOverview();
      resetConversationUi();
      setStatus("尚無可用專案", false);
    }
  }

  async function createProject() {
    if (!state.isManagePage || !state.canManageProjects) return;
    if (!els.projectName) return;
    const name = (els.projectName.value || "").trim();
    if (!name) return;

    const resp = await fetch(url("/projectnotes/projects/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      setStatus(data.error || "建立專案失敗", true);
      return;
    }

    els.projectName.value = "";
    await loadProjects();

    if (els.projectSelect) {
      els.projectSelect.value = String(data.project.id);
      state.projectId = Number(data.project.id);
    }

    await loadSources();
    await loadOverview();
    await loadConversations(0);
    setStatus("建立專案成功", false);
  }

  async function loadSources() {
    if (!els.projectSelect || !els.sourceList) return;
    state.projectId = Number(els.projectSelect.value || 0);
    if (!state.projectId) {
      els.sourceList.innerHTML = "";
      return;
    }

    const resp = await fetch(url(`/projectnotes/sources/?project_id=${state.projectId}`));
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      setStatus(data.error || "讀取來源清單失敗", true);
      return;
    }

    const rows = Array.isArray(data.sources) ? data.sources : [];
    els.sourceList.innerHTML = "";

    rows.forEach((s) => {
      const row = document.createElement("div");
      row.className = "source-item";
      row.dataset.sourceId = String(s.id);

      const left = document.createElement("div");

      const title = document.createElement("div");
      title.className = "source-title";
      title.textContent = `${s.title} (${s.source_version})`;
      title.title = "點擊預覽來源內容";
      title.addEventListener("click", () => previewSourceContent(s.id));

      const meta = document.createElement("div");
      meta.className = "source-meta";
      meta.textContent = `${s.source_type} / chunks=${s.chunk_count} / #${s.id}`;
      meta.title = "點擊預覽來源內容";
      meta.addEventListener("click", () => previewSourceContent(s.id));

      left.appendChild(title);
      left.appendChild(meta);

      if (s.reference_url) {
        const ref = document.createElement("div");
        ref.className = "source-meta";
        ref.textContent = `reference: ${s.reference_url}`;
        left.appendChild(ref);
      }

      const right = document.createElement("div");

      const previewBtn = document.createElement("button");
      previewBtn.type = "button";
      previewBtn.className = "mini-btn";
      previewBtn.textContent = "預覽";
      previewBtn.title = "預覽來源內容";
      previewBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        previewSourceContent(s.id).catch(() => {});
      });

      let deleteBtn = null;
      if (state.isManagePage && state.canManageProjects) {
        deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "mini-btn mini-btn-danger";
        deleteBtn.textContent = "刪除";
        deleteBtn.title = "刪除此來源";
        deleteBtn.addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          await deleteSource(s.id, s.title || "");
        });
      }

      const check = document.createElement("input");
      check.type = "checkbox";
      check.className = "source-check";
      check.value = String(s.id);
      check.checked = true;

      right.appendChild(previewBtn);
      if (deleteBtn) right.appendChild(deleteBtn);
      right.appendChild(check);
      row.appendChild(left);
      row.appendChild(right);

      row.addEventListener("click", (e) => {
        if (e.target && e.target.classList && e.target.classList.contains("source-check")) return;
        previewSourceContent(s.id).catch(() => {});
      });

      els.sourceList.appendChild(row);
    });
  }

  async function deleteSource(sourceId, sourceTitle) {
    if (!state.isManagePage || !state.canManageProjects) return;
    const sid = Number(sourceId || 0);
    if (!sid || state.busy) return;

    const title = (sourceTitle || "").trim();
    const ok = window.confirm(`Delete source ${title || ("#" + sid)}? This will remove related RAG chunks.`);
    if (!ok) return;

    setBusy(true);
    const resp = await fetch(url(`/projectnotes/sources/${sid}/`), { method: "DELETE" });
    const data = await parseJsonSafe(resp);
    setBusy(false);

    if (!data.ok) {
      setStatus(data.error || "刪除發生錯誤", true);
      return;
    }

    markSourcePreviewing(0);
    if (els.citationPanel) els.citationPanel.textContent = "Select a source to preview.";
    await loadSources();
    await loadOverview();
    await loadConversations(state.conversationId);
    setStatus("Source deleted.", false);
  }

  async function uploadSource() {
    if (!state.isManagePage || !state.canManageProjects) return;
    if (!state.projectId || state.busy || !els.sourceFile || !els.sourceTitle) return;

    const file = els.sourceFile.files[0];
    if (!file) {
      setStatus("沒有選擇檔案", true);
      return;
    }

    const title = (els.sourceTitle.value || "").trim() || file.name;
    setBusy(true);

    const fd = new FormData();
    fd.append("project_id", String(state.projectId));
    fd.append("title", title);
    fd.append("file", file);

    setStatus("上傳中...", false);
    const resp = await fetch(url("/projectnotes/sources/"), { method: "POST", body: fd });
    const data = await parseJsonSafe(resp);

    if (!data.ok) {
      setBusy(false);
      setStatus(data.error || "Upload failed.", true);
      return;
    }

    els.sourceFile.value = "";
    els.sourceTitle.value = "";

    if (data.job_id) {
      pollJobStatus(data.job_id);
    } else {
      setBusy(false);
      await loadSources();
      await loadOverview();
      await loadConversations(state.conversationId);
      setStatus("Upload complete.", false);
    }
  }

  async function pollJobStatus(jobId) {
    if (!jobId) return;
    try {
      const resp = await fetch(url(`/projectnotes/jobs/${jobId}/`));
      const data = await parseJsonSafe(resp);
      
      if (!data.ok) {
        setBusy(false);
        setStatus(data.error || "Failed to get job status.", true);
        return;
      }
      
      if (data.status === "failed") {
        setBusy(false);
        setStatus("背景處理失敗: " + data.error_message, true);
        return;
      }
      
      if (data.status === "completed") {
        setBusy(false);
        setStatus("處理完成！", false);
        await loadSources();
        await loadOverview();
        await loadConversations(state.conversationId);
        return;
      }
      
      // Still processing
      setStatus("處理中: " + data.progress_info, false);
      setTimeout(() => pollJobStatus(jobId), 1500);
      
    } catch (e) {
      setBusy(false);
      setStatus("Polling error: " + e, true);
    }
  }

  async function loadOverview() {
    if (!els.overviewText || !els.overviewMeta) return;
    if (!state.projectId) {
      els.overviewText.textContent = "";
      els.overviewMeta.textContent = "";
      return;
    }

    const resp = await fetch(url(`/projectnotes/overview/?project_id=${state.projectId}`));
    const data = await parseJsonSafe(resp);
    if (!data.ok) return;

    const ov = data.overview || {};
    const faq = Array.isArray(ov.faq) ? ov.faq : [];
    const keywords = Array.isArray(ov.keywords) ? ov.keywords : [];
    const decisions = Array.isArray(ov.decisions) ? ov.decisions : [];

    els.overviewText.textContent = ov.summary || "";
    els.overviewMeta.textContent =
      `FAQ: ${faq.join(" | ")}\n` +
      `Keywords: ${keywords.join(" | ")}\n` +
      `Decisions: ${decisions.join(" | ")}`;
  }

  async function newChat() {
    if (!state.projectId || state.busy) return;

    const selected = getCheckedSourceIds();
    if (document.querySelectorAll(".source-check").length > 0 && selected.length === 0) {
      setStatus("Please select at least one source.", true);
      return;
    }

    setBusy(true);

    const resp = await fetch(url("/projectnotes/conversations/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_id: state.projectId,
        title: "New Chat",
        selected_source_ids: selected,
      }),
    });

    const data = await parseJsonSafe(resp);
    setBusy(false);

    if (!data.ok) {
      setStatus(data.error || "發生錯誤", true);
      return;
    }

    state.conversationId = Number(data.conversation.id || 0);
    await loadConversations(state.conversationId);
    if (els.chatLog) els.chatLog.innerHTML = "";
    removePendingAi();
    clearChunkLog();
    setConfidence(null);
    setLLMPrompt("");
    setStatus("", false);
  }

  async function ask() {
    if (!els.questionInput) return;

    const question = (els.questionInput.value || "").trim();
    if (!question || !state.projectId || state.busy) return;

    const selected = getCheckedSourceIds();
    if (document.querySelectorAll(".source-check").length > 0 && selected.length === 0) {
      setStatus("Please select at least one source.", true);
      return;
    }

    if (!state.conversationId) {
      await newChat();
      if (!state.conversationId) return;
    }

    addMsg("user", question);
    els.questionInput.value = "";

    appendPendingAi();
    setBusy(true);

    try {
      const resp = await fetch(url("/projectnotes/chat/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: state.projectId,
          conversation_id: state.conversationId,
          question,
          selected_source_ids: selected,
          version_mode: (els.versionMode && els.versionMode.value) || "latest_only",
          llm_synthesis: true,
        }),
      });

      const data = await parseJsonSafe(resp);
      removePendingAi();

      if (!data.ok) {
        const err = data.error || "建立錯誤";
        addMsg("ai", err);
        setStatus(err, true);
        return;
      }

      state.conversationId = Number(data.conversation_id || 0);
      setConfidence(Number(data.confidence || 0));
      setStatus("", false);

      addRetrievalMsg(data.citations || []);
      setLLMPrompt(data.llm_prompt_preview || "");

      let answer = (data.llm_answer || data.answer || "無法取得對話").trim();
      const citationTail = (data.citation_tail || "").trim();
      const warns = Array.isArray(data.citation_warnings) ? data.citation_warnings.filter(Boolean) : [];
      if (warns.length > 0) {
        answer = `${answer}\n\n警告：\n- ${warns.join("\n- ")}`;
      }
      addMsg("ai", answer, data.citations || [], citationTail);
      const activeConv = state.conversations.find((row) => Number(row.id) === Number(state.conversationId));
      if (activeConv && data.conversation_title) {
        activeConv.title = String(data.conversation_title);
      }
      if (activeConv) {
        activeConv.turn_count = Number(activeConv.turn_count || 0) + 1;
        renderConversationList();
      }
    } catch (_e) {
      removePendingAi();
      const err = "網路錯誤或超時";
      addMsg("ai", err);
      setStatus(err, true);
    } finally {
      setBusy(false);
    }
  }

  async function previewSourceContent(sourceId, focusChunkIndex, citationMeta) {
    if (citationMeta && citationMeta.source_id) {
      postCitationClick(citationMeta);
    }
    const resp = await fetch(url(`/projectnotes/sources/${sourceId}/content/`));
    const data = await parseJsonSafe(resp);

    if (!data.ok) {
      setStatus(data.error || "讀取錯誤", true);
      return;
    }

    if (!els.citationPanel) return;

    markSourcePreviewing(sourceId);

    const s = data.source || {};
    const header = [
      '<div class="cp-title">來源預覽</div>',
      `<div>標題: ${escapeHtml(s.title || "")} (#${escapeHtml(s.id || "")})</div>`,
      s.document_title ? `<div>文件標題: ${escapeHtml(s.document_title)}</div>` : "",
      s.version ? `<div>版本: ${escapeHtml(s.version)}</div>` : "",
      s.path ? `<div>路徑: ${escapeHtml(s.path)}</div>` : "",
    ].join("");

    const chunks = Array.isArray(data.chunks) ? data.chunks : [];
    const focusIndex = Number(focusChunkIndex);

    const citeBlock = (citationMeta && citationMeta.excerpt)
      ? `<div class="cp-cite"><div class="cp-cite-label">引用段落</div><div>${escapeHtml(citationMeta.excerpt)}</div></div>`
      : "";

    if (!chunks.length) {
      els.citationPanel.innerHTML = `${header}${citeBlock}<div class="cp-empty">(無 chunk 內容)</div>`;
      return;
    }

    const chunkHtml = chunks.map((x) => {
      const idx = Number(x.chunk_index);
      const isFocus = Number.isFinite(focusIndex) && idx === focusIndex;
      return (
        `<div class="cp-chunk ${isFocus ? "focus" : ""}" data-chunk-index="${idx}">` +
        `<div class="cp-chunk-head">[chunk ${idx}]</div>` +
        `<div>${escapeHtml(x.content || "")}</div>` +
        "</div>"
      );
    }).join("");

    els.citationPanel.innerHTML = `${header}${citeBlock}${chunkHtml}`;

    if (Number.isFinite(focusIndex)) {
      const target = els.citationPanel.querySelector(`.cp-chunk[data-chunk-index="${focusIndex}"]`);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function resetConversationUi() {
    state.conversationId = 0;
    state.conversations = [];
    renderConversationList();
    if (els.chatLog) els.chatLog.innerHTML = "";
    removePendingAi();
    clearChunkLog();
    setLLMPrompt("");
    setConfidence(null);
    setStatus("", false);
  }

  bindCollapsibleCards();
  clearChunkLog();
  setLLMPrompt("");
  setConfidence(null);

  if (els.createProjectBtn) {
    els.createProjectBtn.addEventListener("click", () => createProject().catch(() => setStatus("建立失敗", true)));
  }
  if (els.newChatBtn) {
    els.newChatBtn.addEventListener("click", () => newChat().catch(() => setStatus("無法建立新對話", true)));
  }
  if (els.refreshBtn) {
    els.refreshBtn.addEventListener("click", () => loadProjects().catch(() => setStatus("重新取得失敗", true)));
  }
  if (els.projectSelect) {
    els.projectSelect.addEventListener("change", () => {
      state.projectId = Number(els.projectSelect.value || 0);
      resetConversationUi();
      loadSources().catch(() => setStatus("資料讀取發生錯誤", true));
      loadOverview().catch(() => {});
      loadLatestConversation().catch(() => {});
    });
  }
  if (els.uploadSourceBtn) {
    els.uploadSourceBtn.addEventListener("click", () => uploadSource().catch(() => setStatus("上傳發生錯誤", true)));
  }
  if (els.askBtn) {
    els.askBtn.addEventListener("click", () => ask().catch(() => setStatus("網路錯誤", true)));
  }
  if (els.questionInput) {
    els.questionInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        ask().catch(() => setStatus("網路錯誤", true));
      }
    });
  }

  loadProjects().catch(() => setStatus("讀取專案清單出現異常", true));
})();

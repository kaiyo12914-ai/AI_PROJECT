// webapps/vanna/static/vanna/js/index.js

// 1. 唯一合法 API URL 產生器
function apiurl(path) {
  const base = document.body.dataset.baseUrl || "";
  let cleanPath = path;
  if (!cleanPath.startsWith("/")) {
    cleanPath = "/" + cleanPath;
  }
  return base + cleanPath;
}

// 2. 日誌記錄器
function addLog(message, type = "info") {
  const consoleEl = document.getElementById("consoleLogs");
  if (!consoleEl) return;

  const timeStr = new Date().toLocaleTimeString();
  const logDiv = document.createElement("div");
  logDiv.className = `log-entry ${type}`;
  logDiv.innerText = `[${timeStr}] ${message}`;
  
  consoleEl.appendChild(logDiv);
  consoleEl.scrollTop = consoleEl.scrollHeight;
}

// 3. 通用的 CSRF Token 取得器 (Django)
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + "=")) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// 4. 同步與管理 API 觸發
function triggerSchemaSync() {
  const btn = document.getElementById("btnSchemaSync");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 同步中...`;
  addLog("開始執行資料庫結構同步 (Schema Sync)...", "info");

  fetch(apiurl("/nl2sql/api/schema/sync/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: "legacy_vanna_chroma",
      db_type: "oracle",
      schema: "LEGACY"
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      const r = data.result;
      addLog(`Schema 同步成功！發現 ${r.discovered} 個對象, 新增 ${r.created}, 更新 ${r.updated}`, "success");
    } else {
      addLog(`Schema 同步失敗: ${data.error}`, "error");
    }
  })
  .catch(err => {
    addLog(`連線錯誤: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

function triggerVannaSync() {
  const btn = document.getElementById("btnVannaSync");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 同步中...`;
  addLog("開始將本地 Schema/DDL/Examples 同步至 Vanna...", "info");

  fetch(apiurl("/nl2sql/api/vanna/sync-training/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: "legacy_vanna_chroma"
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      const r = data.result;
      addLog(`Vanna 同步成功！DDL: ${r.ddl_synced}, Doc: ${r.documentation_synced}, Examples: ${r.examples_synced}`, "success");
    } else {
      addLog(`Vanna 同步失敗: ${data.error}`, "error");
    }
  })
  .catch(err => {
    addLog(`連線錯誤: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

// 5. 對話工作區
function appendUserMessage(text) {
  const chatMessages = document.getElementById("chatMessages");
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `<div class="msg-bubble">${escapeHtml(text)}</div>`;
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function createAssistantBubblePlaceholder() {
  const chatMessages = document.getElementById("chatMessages");
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> AI 思考與產生 SQL 中...</div>`;
  
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

function sendQuestion() {
  const inputEl = document.getElementById("questionInput");
  const question = inputEl.value.trim();
  if (!question) return;

  inputEl.value = "";
  appendUserMessage(question);
  addLog(`提問: "${question}"`, "info");

  const bubble = createAssistantBubblePlaceholder();

  fetch(apiurl("/nl2sql/api/generate/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: "legacy_vanna_chroma",
      question: question
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      const r = data.result;
      addLog("SQL 候選生成成功，啟動安全審查...", "success");
      renderSqlResponse(bubble, r);
    } else {
      bubble.innerHTML = `<div style="color:#ef4444;">錯誤: ${escapeHtml(data.error)}</div>`;
      addLog(`生成失敗: ${data.error}`, "error");
    }
  })
  .catch(err => {
    bubble.innerHTML = `<div style="color:#ef4444;">連線失敗: ${escapeHtml(err.message)}</div>`;
    addLog(`連線失敗: ${err.message}`, "error");
  });
}

function renderSqlResponse(bubbleEl, result) {
  const sql = result.sql || "";
  const queryLogId = result.query_log_id;
  const latency = result.latency_ms;
  const guardStatus = result.context_summary.guard_status;
  const guardMessage = result.context_summary.guard_message;

  let guardHtml = "";
  let runButtonHtml = "";

  if (guardStatus === "passed") {
    guardHtml = `<div class="guard-banner passed">🛡️ SQL Guard: 安全審查通過 (AST Passed)</div>`;
    runButtonHtml = `
      <div class="run-btn-row">
        <button class="btn btn-primary" onclick="runQuery(${queryLogId}, this)">
          ▶ 唯讀執行此查詢
        </button>
      </div>
    `;
  } else {
    guardHtml = `
      <div class="guard-banner blocked">
        ⚠️ SQL Guard: 阻擋執行 (AST Blocked)<br>
        <small>${escapeHtml(guardMessage)}</small>
      </div>
    `;
    addLog(`SQL 被 SQL Guard 安全阻擋: ${guardMessage}`, "error");
  }

  bubbleEl.innerHTML = `
    <div><strong>產生的 SQL 候選：</strong> (耗時 ${latency}ms)</div>
    <div class="sql-container">
      <div class="sql-header">
        <span>SQL Query</span>
        <button class="btn btn-secondary" style="padding: 4px 8px; font-size:11px;" onclick="navigator.clipboard.writeText(\`${escapeJs(sql)}\`); addLog('SQL 已複製到剪貼簿', 'success');">複製</button>
      </div>
      <pre><code>${escapeHtml(sql)}</code></pre>
    </div>
    ${guardHtml}
    ${runButtonHtml}
    <div id="results-container-${queryLogId}" class="result-section" style="display:none;"></div>
  `;
}

// 6. 唯讀執行查詢
function runQuery(queryLogId, btn) {
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 執行中...`;
  addLog(`開始執行查詢 (Log ID: ${queryLogId})...`, "info");

  const resultsContainer = document.getElementById(`results-container-${queryLogId}`);
  resultsContainer.style.display = "block";
  resultsContainer.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 正在連接資料庫取得數據...</div>`;

  fetch(apiurl("/nl2sql/api/execute/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      query_log_id: queryLogId
    })
  })
  .then(res => res.json())
  .then(data => {
    if (data.ok) {
      addLog(`查詢成功！取得 ${data.rows.length} 筆資料 (耗時 ${data.latency_ms}ms)`, "success");
      renderResultTable(resultsContainer, data);
    } else {
      resultsContainer.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>執行失敗:</strong><br>${escapeHtml(data.error)}</div>`;
      addLog(`執行失敗: ${data.error}`, "error");
    }
  })
  .catch(err => {
    resultsContainer.innerHTML = `<div style="color:#ef4444;">執行失敗: ${escapeHtml(err.message)}</div>`;
    addLog(`連線錯誤: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

function renderResultTable(containerEl, data) {
  const columns = data.columns || [];
  const rows = data.rows || [];
  const isMock = data.is_mock;
  const latency = data.latency_ms;

  let mockBadgeHtml = isMock ? `<span style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.3); color:#f59e0b; padding:2px 6px; border-radius:4px; font-size:11px;">MOCK DATA</span>` : "";

  if (rows.length === 0) {
    containerEl.innerHTML = `
      <div class="result-header">
        <span>執行耗時: ${latency}ms ${mockBadgeHtml}</span>
      </div>
      <div style="color:#94a3b8; font-style:italic;">查詢成功，但無符合的結果。</div>
    `;
    return;
  }

  // 建立表頭
  let thsHtml = columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
  
  // 建立表身
  let trsHtml = rows.map(row => {
    let tds = row.map(cell => {
      let displayVal = cell;
      if (cell === null || cell === undefined) {
        displayVal = "NULL";
      } else if (typeof cell === "object") {
        displayVal = JSON.stringify(cell);
      }
      return `<td>${escapeHtml(String(displayVal))}</td>`;
    }).join("");
    return `<tr>${tds}</tr>`;
  }).join("");

  containerEl.innerHTML = `
    <div class="result-header">
      <span>查詢結果：共 ${rows.length} 筆資料 (耗時 ${latency}ms) ${mockBadgeHtml}</span>
    </div>
    <div class="table-wrapper">
      <table class="result-table">
        <thead>
          <tr>${thsHtml}</tr>
        </thead>
        <tbody>
          ${trsHtml}
        </tbody>
      </table>
    </div>
  `;
}

// 7. 工具函式
function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeJs(str) {
  if (!str) return "";
  return str
    .replace(/\\/g, "\\\\")
    .replace(/`/g, "\\`")
    .replace(/\$/g, "\\$");
}

// 8. 快捷提問
function askPreset(presetText) {
  const inputEl = document.getElementById("questionInput");
  if (inputEl) {
    inputEl.value = presetText;
    sendQuestion();
  }
}

// 9. 綁定按鈕監聽 (等 DOMContentLoaded)
document.addEventListener("DOMContentLoaded", () => {
  addLog("Vanna 2.0 整合對話工作區已載入。", "success");

  // 監聽輸入框 Enter 送出
  const inputEl = document.getElementById("questionInput");
  if (inputEl) {
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        sendQuestion();
      }
    });
  }
});

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

function responseTextOrJson(res) {
  return res.text().then(text => {
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch (err) {
      data = null;
    }
    if (res.ok && data) {
      return data;
    }
    const error = new Error(data && data.error ? data.error : (text || res.statusText || "Request failed"));
    error.status = res.status;
    error.url = res.url;
    error.payload = data;
    throw error;
  });
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

function selectedDataSourceCode() {
  const selectEl = document.getElementById("dataSourceSelect");
  return selectEl ? selectEl.value : "legacy_vanna_chroma";
}

function openTrainingDatasetManager() {
  const chatMessages = document.getElementById("chatMessages");
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble training-manager";
  bubble.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 載入 Vanna 訓練資料集...</div>`;
  row.appendChild(bubble);
  chatMessages.appendChild(row);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  loadTrainingDataset(bubble);
}

function loadTrainingDataset(bubbleEl) {
  const code = encodeURIComponent(selectedDataSourceCode());
  fetch(apiurl(`/nl2sql/api/vanna/training-dataset/?code=${code}`), {
    method: "GET",
    headers: {
      "X-CSRFToken": getCookie("csrftoken")
    }
  })
  .then(res => res.json())
  .then(data => {
    if (!data.ok) {
      bubbleEl.innerHTML = `<div style="color:#ef4444;">載入失敗: ${escapeHtml(data.error)}</div>`;
      addLog(`訓練資料集載入失敗: ${data.error}`, "error");
      return;
    }
    renderTrainingDatasetManager(bubbleEl, data.result);
    addLog("Vanna 訓練資料集已載入。", "success");
  })
  .catch(err => {
    bubbleEl.innerHTML = `<div style="color:#ef4444;">載入失敗: ${escapeHtml(err.message)}</div>`;
    addLog(`訓練資料集載入失敗: ${err.message}`, "error");
  });
}

function renderTrainingDatasetManager(bubbleEl, result) {
  const summary = result.summary || {};
  const ds = result.data_source || {};
  const schemaRows = (result.schema_objects || []).map(item => `
    <tr>
      <td>${escapeHtml(item.schema)}.${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.type)}</td>
      <td>${escapeHtml(String(item.columns || 0))}</td>
      <td>${item.enabled ? "啟用" : "停用"}</td>
    </tr>
  `).join("");
  const documentationRows = (result.documentation_items || []).map(item => `
    <tr>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml((item.documentation || "").slice(0, 160))}</td>
    </tr>
  `).join("");
  const exampleRows = (result.training_examples || []).map(item => `
    <tr>
      <td>${escapeHtml(item.question)}</td>
      <td><code>${escapeHtml(item.status)}</code></td>
      <td>${escapeHtml(item.created_by || "")}</td>
    </tr>
  `).join("");
  const syncRows = (result.vanna_sync_records || []).map(item => `
    <tr>
      <td>${escapeHtml(item.type)}</td>
      <td><code>${escapeHtml(item.status)}</code></td>
      <td>${escapeHtml(item.training_id || "")}</td>
    </tr>
  `).join("");

  bubbleEl.innerHTML = `
    <div class="training-head">
      <div>
        <strong>Vanna 2.0 訓練資料集維護</strong>
        <div class="muted-text">資料源：${escapeHtml(ds.name || ds.code || "")}｜DB：${escapeHtml(ds.db_type || "")}｜Schema：${escapeHtml(ds.schema || "")}</div>
      </div>
      <button class="btn btn-secondary mini-btn" onclick="loadTrainingDataset(this.closest('.msg-bubble'))">重新整理</button>
    </div>
    <div class="metric-grid">
      <div class="metric-card"><span>Schema</span><strong>${summary.schema_objects || 0}</strong></div>
      <div class="metric-card"><span>DDL</span><strong>${summary.ddl_items || 0}</strong></div>
      <div class="metric-card"><span>Documentation</span><strong>${summary.documentation_items || 0}</strong></div>
      <div class="metric-card"><span>SQL Examples</span><strong>${summary.approved_examples || 0}</strong></div>
      <div class="metric-card"><span>Vanna Synced</span><strong>${summary.synced_records || 0}</strong></div>
      <div class="metric-card"><span>Failed</span><strong>${summary.failed_records || 0}</strong></div>
    </div>

    <div class="training-form">
      <div class="form-title">新增訓練資料</div>
      <div class="training-type-tabs" role="tablist" aria-label="訓練資料分類">
        <button class="training-type-tab active" type="button" data-training-type="ddl" onclick="selectTrainingType(this)">DDL</button>
        <button class="training-type-tab" type="button" data-training-type="documentation" onclick="selectTrainingType(this)">Documentation</button>
        <button class="training-type-tab" type="button" data-training-type="sql" onclick="selectTrainingType(this)">SQL</button>
      </div>

      <div class="training-fields" data-training-fields="ddl">
        <div class="muted-text">放資料表或 View 結構。系統會解析 CREATE TABLE / CREATE VIEW 並寫入 Schema metadata。</div>
        <textarea id="trainingDdlInput" placeholder="CREATE TABLE LEGACY.CT_EMPLOYEE (
  EMPNO VARCHAR2(20) PRIMARY KEY,
  EMPNAME NVARCHAR2(100),
  DEPTNO VARCHAR2(20)
);"></textarea>
      </div>

      <div class="training-fields hidden" data-training-fields="documentation">
        <div class="muted-text">放業務語意、欄位含義、代碼規則。不要放 SQL。</div>
        <input id="trainingDocTitleInput" type="text" placeholder="文件標題，例如：人事在職狀態代碼說明">
        <textarea id="trainingDocInput" placeholder="status = 'ACTIVE' 代表在職員工。
status = 'RESIGNED' 代表離職員工。
查詢目前在職人數時，應只統計 ACTIVE。"></textarea>
      </div>

      <div class="training-fields hidden" data-training-fields="sql">
        <div class="muted-text">放已驗證的自然語言問題與唯讀 SQL。只允許 SELECT / WITH SELECT。</div>
        <input id="trainingQuestionInput" type="text" placeholder="自然語言問題，例如：[人事]205廠 查詢各單位目前在職人員數量">
        <textarea id="trainingSqlInput" placeholder="SELECT d.DEPT_NAME, COUNT(*) AS CNT
FROM CT_EMPLOYEE e
JOIN CT_DEPARTMENT d ON d.DEPTNO = e.DEPTNO
WHERE e.STATUS = 'ACTIVE'
GROUP BY d.DEPT_NAME;"></textarea>
      </div>

      <button class="btn btn-primary" onclick="submitTrainingData(this)">新增到訓練資料集</button>
    </div>

    <div class="training-form sql-test-form">
      <div class="form-title">執行 SQL 語法測試</div>
      <div class="muted-text">僅系統管理員可用；仍會經過 SQL Guard，只允許 SELECT / WITH SELECT。ENV=EXT 時 Oracle 只回傳 SQL ONLY，不連線執行。</div>
      <textarea id="adminSqlInput" placeholder="SELECT *
FROM CT_EMPLOYEE
WHERE ROWNUM <= 10;"></textarea>
      <div class="sql-test-actions">
        <input id="adminSqlMaxRowsInput" type="number" min="1" max="1000" value="100" aria-label="最多回傳筆數">
        <button class="btn btn-primary" onclick="executeAdminSqlTest(this)">執行 SQL 測試</button>
      </div>
      <div class="result-section sql-test-result" style="display:none;"></div>
    </div>

    <div class="training-section">
      <h3>DDL / Schema metadata</h3>
      <div class="table-wrapper training-table-wrap">
        <table class="result-table">
          <thead><tr><th>Table/View</th><th>Type</th><th>Columns</th><th>Status</th></tr></thead>
          <tbody>${schemaRows || `<tr><td colspan="4">尚無 schema metadata</td></tr>`}</tbody>
        </table>
      </div>
    </div>
    <div class="training-section">
      <h3>Documentation</h3>
      <div class="table-wrapper training-table-wrap">
        <table class="result-table">
          <thead><tr><th>Name</th><th>Content</th></tr></thead>
          <tbody>${documentationRows || `<tr><td colspan="2">尚無 documentation</td></tr>`}</tbody>
        </table>
      </div>
    </div>
    <div class="training-section">
      <h3>SQL approved examples</h3>
      <div class="table-wrapper training-table-wrap">
        <table class="result-table">
          <thead><tr><th>Question</th><th>Status</th><th>Created by</th></tr></thead>
          <tbody>${exampleRows || `<tr><td colspan="3">尚無 approved examples</td></tr>`}</tbody>
        </table>
      </div>
    </div>
    <div class="training-section">
      <h3>Vanna sync records</h3>
      <div class="table-wrapper training-table-wrap">
        <table class="result-table">
          <thead><tr><th>Type</th><th>Status</th><th>Training ID</th></tr></thead>
          <tbody>${syncRows || `<tr><td colspan="3">尚無 sync records</td></tr>`}</tbody>
        </table>
      </div>
    </div>
  `;
}

function selectTrainingType(tabEl) {
  const formEl = tabEl.closest(".training-form");
  const trainingType = tabEl.dataset.trainingType;
  formEl.querySelectorAll(".training-type-tab").forEach(el => {
    el.classList.toggle("active", el === tabEl);
  });
  formEl.querySelectorAll(".training-fields").forEach(el => {
    el.classList.toggle("hidden", el.dataset.trainingFields !== trainingType);
  });
}

function activeTrainingType(formEl) {
  const activeTab = formEl.querySelector(".training-type-tab.active");
  return activeTab ? activeTab.dataset.trainingType : "ddl";
}

function trainingPayload(formEl, trainingType) {
  if (trainingType === "ddl") {
    const ddl = formEl.querySelector("#trainingDdlInput").value.trim();
    if (!ddl) {
      throw new Error("請輸入 DDL 後再新增。");
    }
    return { training_type: "ddl", ddl };
  }

  if (trainingType === "documentation") {
    const title = formEl.querySelector("#trainingDocTitleInput").value.trim();
    const documentation = formEl.querySelector("#trainingDocInput").value.trim();
    if (!documentation) {
      throw new Error("請輸入 Documentation 後再新增。");
    }
    return { training_type: "documentation", title, documentation };
  }

  const question = formEl.querySelector("#trainingQuestionInput").value.trim();
  const sql = formEl.querySelector("#trainingSqlInput").value.trim();
  if (!question || !sql) {
    throw new Error("請輸入 question 與 SQL 後再新增訓練範例。");
  }
  return { training_type: "sql", question, sql };
}

function submitTrainingData(btn) {
  const bubbleEl = btn.closest(".msg-bubble");
  const formEl = btn.closest(".training-form");
  const trainingType = activeTrainingType(formEl);
  let payload;
  try {
    payload = trainingPayload(formEl, trainingType);
  } catch (err) {
    addLog(err.message, "error");
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 新增中...`;
  fetch(apiurl("/nl2sql/api/vanna/training-dataset/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: selectedDataSourceCode(),
      ...payload
    })
  })
  .then(res => res.json())
  .then(data => {
    if (!data.ok) {
      addLog(`新增訓練範例失敗: ${data.error}`, "error");
      return;
    }
    addLog(`已新增 ${trainingType} 訓練資料，請執行 Vanna Sync 使資料生效。`, "success");
    loadTrainingDataset(bubbleEl);
  })
  .catch(err => {
    addLog(`新增訓練範例失敗: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

function executeAdminSqlTest(btn) {
  const formEl = btn.closest(".sql-test-form");
  const sqlEl = formEl.querySelector("#adminSqlInput");
  const maxRowsEl = formEl.querySelector("#adminSqlMaxRowsInput");
  const resultEl = formEl.querySelector(".sql-test-result");
  const sql = sqlEl.value.trim();
  const maxRows = parseInt(maxRowsEl.value || "100", 10);

  if (!sql) {
    addLog("請輸入 SQL 後再執行測試。", "error");
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 執行中...`;
  resultEl.style.display = "block";
  resultEl.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 正在執行 SQL 測試...</div>`;
  addLog("管理員 SQL 測試開始執行。", "info");

  const endpoint = apiurl("/nl2sql/api/vanna/admin-sql-execute/");
  fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: selectedDataSourceCode(),
      sql: sql,
      max_rows: Number.isFinite(maxRows) ? maxRows : 100
    })
  })
  .then(res => responseTextOrJson(res))
  .then(data => {
    if (!data.ok) {
      resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>執行失敗:</strong><br>${escapeHtml(data.error)}</div>`;
      addLog(`管理員 SQL 測試失敗: ${data.error}`, "error");
      return;
    }
    addLog(`管理員 SQL 測試成功，取得 ${(data.rows || []).length} 筆資料。`, "success");
    renderResultTable(resultEl, data);
  })
  .catch(err => {
    const statusText = err.status ? `HTTP ${err.status}` : "連線錯誤";
    const urlText = err.url || endpoint;
    resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>執行失敗 (${escapeHtml(statusText)}):</strong><br>${escapeHtml(err.message)}<br><small>URL: ${escapeHtml(urlText)}</small></div>`;
    addLog(`管理員 SQL 測試失敗: ${statusText} ${urlText}`, "error");
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
  const executionPolicy = result.execution_policy || {};
  const canExecute = executionPolicy.can_execute === true;
  const policyMessage = executionPolicy.message || "";

  let guardHtml = "";
  let runButtonHtml = "";
  let policyHtml = "";

  if (policyMessage) {
    const policyClass = canExecute ? "passed" : "blocked";
    policyHtml = `<div class="guard-banner ${policyClass}">${escapeHtml(policyMessage)}</div>`;
  }

  if (guardStatus === "passed") {
    guardHtml = `<div class="guard-banner passed">SQL Guard: passed</div>`;
    if (canExecute) {
      runButtonHtml = `
        <div class="run-btn-row">
          <button class="btn btn-primary" onclick="runQuery(${queryLogId}, this)">
            Execute Oracle Query
          </button>
        </div>
      `;
    }
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
    ${policyHtml}
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
  const isSqlOnly = data.sql_only === true;
  const latency = data.latency_ms;

  let mockBadgeHtml = isSqlOnly ? `<span style="background:rgba(245,158,11,0.15); border:1px solid rgba(245,158,11,0.3); color:#f59e0b; padding:2px 6px; border-radius:4px; font-size:11px;">SQL ONLY</span>` : "";

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

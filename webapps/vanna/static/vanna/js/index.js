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

function stripDisplayPrefix(value, prefix) {
  const raw = String(value || "");
  if (!prefix) return raw;
  return raw.toUpperCase().startsWith(prefix.toUpperCase()) ? raw.slice(prefix.length) : raw;
}

function formatSchemaObjectLabel(item) {
  const schemaName = String(item && item.schema ? item.schema : "");
  const rawName = String(item && item.name ? item.name : "");
  const schemaPrefix = schemaName ? `${schemaName}.` : "";
  const withoutSchemaPrefix = stripDisplayPrefix(rawName, schemaPrefix);
  return stripDisplayPrefix(withoutSchemaPrefix, "LEGACY.");
}

function formatDocumentationName(name) {
  return stripDisplayPrefix(name, "VANNA_LEGACY_");
}

function normalizePresetUnit(unit) {
  const raw = String(unit || "").trim().toUpperCase();
  if (!raw) return "MPC";
  if (raw === "PC") return "MPC";
  if (["MPC", "202", "205", "209", "401"].includes(raw)) return raw;
  const compact = raw.replace(/[^A-Z0-9]+/g, "");
  if (compact === "PC") return "MPC";
  if (["MPC", "202", "205", "209", "401"].includes(compact)) return compact;
  if (compact === "MNDQ") return "205";
  if (compact === "MNDV") return "209";
  if (compact === "MNDI") return "401";
  const match = compact.match(/(202|205|209|401)/);
  if (match) return match[1];
  if (compact.includes("MPC")) return "MPC";
  return "MPC";
}

function getCurrentLoginOrg() {
  return normalizePresetUnit(document.body.dataset.loginUserOrg || "");
}

function replaceQuestionUnit(question, unit) {
  const resolvedUnit = normalizePresetUnit(unit);
  const raw = String(question || "").trim();
  const match = raw.match(/^(\s*\[[^\]]+\]\s*)([^\s]+)(.*)$/);
  if (!match) return raw;
  return `${match[1]}${resolvedUnit}${match[3]}`;
}

function normalizeQuestionForCurrentOrg(question) {
  return replaceQuestionUnit(question, getCurrentLoginOrg());
}

const BASE_PRESET_QUESTIONS = [
  "[人事]MPC 查詢目前在職人員數量",
  "[人事]202廠 列出前10筆員工姓名、工號與所屬單位",
  "[人事]205廠 查詢各單位目前在職人員數量",
  "[採購]209廠 查詢物料採購未交量前20筆",
  "[物料]401廠 查詢低於安全庫存的前20筆料號",
  "[人事]MPC 查詢各職稱目前在職人員數量",
  "[人事]205廠 查詢目前離職人員數量",
  "[採購]209廠 查詢逾期未交物料前20筆",
  "[物料]401廠 查詢目前零庫存的前20筆料號",
  "[主計]202廠 查詢各分類統計"
];

function buildDefaultPresetQuestions() {
  const unit = getCurrentLoginOrg();
  return BASE_PRESET_QUESTIONS.map(question => replaceQuestionUnit(question, unit)).slice(0, 10);
}

function parseQuestionContext(question) {
  const raw = String(question || "").trim();
  if (!raw) return null;
  const match = raw.match(/^\s*\[([^\]]+)\]\s*([^\s]+)\s*(.*)$/);
  if (!match) {
    return {
      raw,
      business: "",
      unit: "",
      intent: raw
    };
  }
  return {
    raw,
    business: String(match[1] || "").trim(),
    unit: String(match[2] || "").trim(),
    intent: String(match[3] || "").trim()
  };
}

function classifyIntent(intent) {
  const text = String(intent || "");
  if (!text) return "generic";
  if (/(未交|待交|逾期|欠料|未到貨)/.test(text)) return "pending";
  if (/(安全庫存|低於庫存|庫存不足|庫存|料號)/.test(text)) return "inventory";
  if (/(前\d+筆|列出|明細|名單|姓名|工號|清單)/.test(text)) return "detail";
  if (/(單位|部門|各課|各組)/.test(text) && /(人數|數量|統計|筆數)/.test(text)) return "group_count";
  if (/(人數|數量|統計|筆數|總數)/.test(text)) return "count";
  return "generic";
}

function questionLabel(question) {
  return `💬 ${question}`;
}

function normalizeForDedupe(str) {
  return String(str || "")
    .trim()
    .toUpperCase()
    .replace(/[\s\[\]\-\,\，\.\。]/g, "")
    .replace(/(人員數量|人數|數量|筆數|總數|在職數|在職人員數量)/g, "數")
    .replace(/(員工姓名、工號與所屬單位|員工姓名、工號及所屬單位|前10筆員工姓名、工號與所屬單位)/g, "員工明細")
    .replace(/(物料採購未交量前20筆|物料採購未交量)/g, "物料未交")
    .replace(/(低於安全庫存的前20筆料號|低於安全庫存)/g, "低於安全庫存");
}

function dedupeQuestions(questions, currentQuestion) {
  const current = normalizeForDedupe(currentQuestion);
  const seen = new Set();
  const result = [];
  questions.forEach(item => {
    const value = String(item || "").trim();
    if (!value) return;
    const normalizedVal = normalizeForDedupe(value);
    if (normalizedVal === current) return;
    const key = normalizedVal.toUpperCase();
    if (seen.has(key)) return;
    seen.add(key);
    result.push(value);
  });
  return result;
}

function buildRelatedQuestions(question) {
  const context = parseQuestionContext(question);
  if (!context || !context.business || !context.unit) {
    return buildDefaultPresetQuestions();
  }

  const prefix = `[${context.business}]${context.unit}`;
  const intentType = classifyIntent(context.intent);
  let candidates = [];

  if (context.business.includes("人事")) {
    candidates = [
      `${prefix} 查詢目前在職人員數量`,
      `${prefix} 查詢各單位目前在職人員數量`,
      `${prefix} 列出前10筆員工姓名、工號與所屬單位`,
      `${prefix} 查詢目前離職人員數量`,
      `${prefix} 查詢各職稱目前在職人員數量`
    ];
    if (intentType === "detail") {
      candidates.unshift(
        `${prefix} 查詢目前在職人員數量`,
        `${prefix} 查詢各單位目前在職人員數量`
      );
    }
  } else if (context.business.includes("採購")) {
    candidates = [
      `${prefix} 查詢物料採購未交量前20筆`,
      `${prefix} 查詢未交採購單前20筆`,
      `${prefix} 查詢各供應商未交金額前10筆`,
      `${prefix} 查詢逾期未交物料前20筆`,
      `${prefix} 查詢各料號未交數量前20筆`
    ];
  } else if (context.business.includes("物料")) {
    candidates = [
      `${prefix} 查詢低於安全庫存的前20筆料號`,
      `${prefix} 查詢目前零庫存的前20筆料號`,
      `${prefix} 查詢各倉別低於安全庫存筆數`,
      `${prefix} 查詢庫存最高的前20筆料號`,
      `${prefix} 查詢近30日無異動的前20筆料號`
    ];
  } else {
    candidates = [
      `${prefix} 查詢目前筆數`,
      `${prefix} 查詢各分類統計`,
      `${prefix} 列出前10筆明細`,
      `${prefix} 查詢最近異動前10筆`,
      `${prefix} 查詢各單位統計`
    ];
  }

  if (intentType === "count") {
    candidates.unshift(
      `${prefix} 查詢各單位目前筆數`,
      `${prefix} 列出前10筆明細`
    );
  } else if (intentType === "group_count") {
    candidates.unshift(
      `${prefix} 查詢目前總數`,
      `${prefix} 列出前10筆明細`
    );
  } else if (intentType === "pending") {
    candidates.unshift(
      `${prefix} 查詢逾期未處理前20筆`,
      `${prefix} 查詢各供應商未結案件數`
    );
  } else if (intentType === "inventory") {
    candidates.unshift(
      `${prefix} 查詢低於安全庫存的前20筆料號`,
      `${prefix} 查詢目前零庫存的前20筆料號`
    );
  }

  return dedupeQuestions(candidates, context.raw).slice(0, 10);
}

function renderPresetQuestions(questions) {
  const container = document.getElementById("presetQuestionList");
  if (!container) return;
  const items = (questions && questions.length ? questions : buildDefaultPresetQuestions()).slice(0, 10);
  container.innerHTML = items.map(question => `
    <button class="btn btn-secondary" style="font-size:12.5px; text-align:left; justify-content:flex-start;" onclick="askPreset('${escapeJs(question)}')">
      ${escapeHtml(questionLabel(question))}
    </button>
  `).join("");
}

function updatePresetQuestionsByQuery(question) {
  const normalizedQuestion = normalizeQuestionForCurrentOrg(question);
  const questions = buildRelatedQuestions(normalizedQuestion);
  renderPresetQuestions(questions);
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

const TRAINING_DATASET_CODE = "__nl2sql_training_catalog__";

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

function loadTrainingDataset(bubbleEl, allItems = false) {
  const code = encodeURIComponent(TRAINING_DATASET_CODE);
  const allQuery = allItems ? "&all=true" : "";
  bubbleEl.dataset.allItems = allItems ? "true" : "false";
  fetch(apiurl(`/nl2sql/api/vanna/training-dataset/?code=${code}${allQuery}`), {
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
    renderTrainingDatasetManager(bubbleEl, data.result, allItems);
    addLog("Vanna 訓練資料集已載入。", "success");
  })
  .catch(err => {
    bubbleEl.innerHTML = `<div style="color:#ef4444;">載入失敗: ${escapeHtml(err.message)}</div>`;
    addLog(`訓練資料集載入失敗: ${err.message}`, "error");
  });
}

function findTrainingItemById(result, type, id) {
  if (!result) return null;
  const collections = {
    ddl: result.schema_objects || [],
    documentation: result.documentation_items || [],
    sql: result.training_examples || [],
    failed: result.failed_queries || []
  };
  const items = collections[type] || [];
  return items.find(item => item.id === id) || null;
}

function renderTrainingDatasetManager(bubbleEl, result, allItems = false) {
  bubbleEl.trainingDatasetResult = result;
  const summary = result.summary || {};
  const ds = result.data_source || {};
  const schemaRows = (result.schema_objects || []).map(item => `
    <tr>
      <td>${escapeHtml(formatSchemaObjectLabel(item))}</td>
      <td>${escapeHtml(item.type)}</td>
      <td>${escapeHtml(String(item.columns || 0))}</td>
      <td>${item.enabled ? "啟用" : "停用"}</td>
      <td>
        <button class="btn btn-secondary mini-btn btn-edit-item" onclick="editTrainingItem(this, 'ddl', ${item.id})">編輯</button>
        <button class="btn btn-danger mini-btn btn-delete-item" onclick="deleteTrainingItem(this, 'ddl', ${item.id})">刪除</button>
      </td>
    </tr>
  `).join("");
  const documentationRows = (result.documentation_items || []).map(item => `
    <tr>
      <td>${escapeHtml(formatDocumentationName(item.name))}</td>
      <td>${escapeHtml((item.documentation || "").slice(0, 160))}</td>
      <td>
        <button class="btn btn-secondary mini-btn btn-edit-item" onclick="editTrainingItem(this, 'documentation', ${item.id})">編輯</button>
        <button class="btn btn-danger mini-btn btn-delete-item" onclick="deleteTrainingItem(this, 'documentation', ${item.id})">刪除</button>
      </td>
    </tr>
  `).join("");
  const exampleRows = (result.training_examples || []).map(item => `
    <tr>
      <td>${escapeHtml(item.question)}</td>
      <td><code>${escapeHtml(item.status)}</code></td>
      <td>${escapeHtml(item.created_by || "")}</td>
      <td>
        <button class="btn btn-secondary mini-btn btn-edit-item" onclick="editTrainingItem(this, 'sql', ${item.id})">編輯</button>
        <button class="btn btn-danger mini-btn btn-delete-item" onclick="deleteTrainingItem(this, 'sql', ${item.id})">刪除</button>
      </td>
    </tr>
  `).join("");
  const refreshBtn = `<button class="btn btn-secondary mini-btn" onclick="loadTrainingDataset(this.closest('.msg-bubble'), ${allItems})">重新整理</button>`;
  const viewAllBtn = allItems ? "" : `<button class="btn btn-secondary mini-btn" onclick="loadTrainingDataset(this.closest('.msg-bubble'), true)">檢視全部</button>`;

  bubbleEl.innerHTML = `
    <div class="training-head">
      <div>
        <strong>Vanna 2.0 訓練資料集維護</strong>
        <div class="muted-text">資料源：${escapeHtml(ds.name || ds.code || "")}｜DB：${escapeHtml(ds.db_type || "")}｜Schema：${escapeHtml(ds.schema || "")}</div>
      </div>
      <div style="display:flex;gap:6px;">
        ${refreshBtn}
        ${viewAllBtn}
      </div>
    </div>

    <div class="training-form rag-debugger-form">
      <div class="form-title">🔍 RAG 檢索與 LLM 提示詞除錯器</div>
      <div class="muted-text">輸入提問，可查詢 SchemaEmbedding (DDL/Doc) 與 ExampleEmbedding (SQL 範例) 的相似度分數與 RAG 內容，以及最終組裝的 LLM 提示詞。</div>
      <div class="rag-debug-input-row">
        <input id="ragDebugQuestionInput" class="rag-debug-question-input" type="text" placeholder="輸入要測試的提問，例如：[人事]205廠 查詢在職人數">
        <button class="btn btn-primary rag-debug-submit-btn" onclick="debugRagPrompt(this)">檢索並分析</button>
      </div>
      <div class="rag-debug-result" style="display:none;"></div>
    </div>

    <div class="metric-grid">
      <div class="metric-card"><span>Schema</span><strong>${summary.schema_objects || 0}</strong></div>
      <div class="metric-card"><span>DDL</span><strong>${summary.ddl_items || 0}</strong></div>
      <div class="metric-card"><span>Documentation</span><strong>${summary.documentation_items || 0}</strong></div>
      <div class="metric-card"><span>SQL Examples</span><strong>${summary.approved_examples || 0}</strong></div>
      <div class="metric-card"><span>Vanna Synced</span><strong>${summary.synced_records || 0}</strong></div>
      <div class="metric-card"><span>Failed</span><strong>${summary.failed_records || 0}</strong></div>
    </div>

    <div class="training-form training-data-form">
      <div class="form-title">新增與編輯訓練資料</div>
      <div class="training-type-tabs" role="tablist" aria-label="訓練資料分類">
        <button class="training-type-tab active" type="button" data-training-type="ddl" onclick="selectTrainingType(this)">DDL</button>
        <button class="training-type-tab" type="button" data-training-type="documentation" onclick="selectTrainingType(this)">Documentation</button>
        <button class="training-type-tab" type="button" data-training-type="sql" onclick="selectTrainingType(this)">SQL</button>
        <button class="training-type-tab" type="button" data-training-type="failed" onclick="selectTrainingType(this)">Failed Query</button>
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
        <div class="current-sql-test-row" style="display:flex; align-items:center; gap:8px; margin-top:8px;">
          <button type="button" class="btn btn-secondary mini-btn" onclick="testCurrentSql(this)">測試此 SQL 語法</button>
          <span class="muted-text" style="margin-left:8px;">最多回傳:</span>
          <input id="currentSqlMaxRowsInput" type="number" min="1" max="1000" value="10" style="width: 70px; padding: 4px 8px; font-size:12px; height:28px;" aria-label="最多回傳筆數">
        </div>
        <div class="current-sql-test-result" style="display:none; margin-top:10px;"></div>
      </div>
      <div class="training-fields hidden" data-training-fields="failed">
        <div class="muted-text">維護並優化內網執行失敗的自然語言 SQL 語法與精進措施。</div>
        <input id="failedQuestionInput" type="text" placeholder="自然語言提問">
        <textarea id="failedSqlInput" placeholder="失敗之 SQL" style="min-height: 150px;"></textarea>
        <textarea id="failedErrorInput" placeholder="錯誤訊息 (唯讀)" style="min-height: 100px;" readonly></textarea>
        <textarea id="failedAnalysisInput" placeholder="失敗根因剖析，例如：RAG 未正確檢索到特定欄位或資料表" style="min-height: 120px;"></textarea>
        <textarea id="failedActionInput" placeholder="採取的精進措施，例如：新增 DDL 表結構或 documentation 說明" style="min-height: 120px;"></textarea>
        <div style="display:flex; align-items:center; gap:8px; margin-top:8px;">
          <span style="font-size:13px; color:#cbd5e1;">處理狀態：</span>
          <select id="failedStatusSelect" style="width: auto; padding: 4px 8px; font-size:12px; height:28px;">
            <option value="pending">待處理</option>
            <option value="optimized">已完成優化</option>
            <option value="ignored">忽略/不處理</option>
          </select>
        </div>
      </div>

      <button class="btn btn-primary" onclick="submitTrainingData(this)">新增/更新訓練資料</button>
    </div>

    <div class="training-form sql-test-form disabled-form">
      <div class="form-title">執行 SQL 語法測試</div>
      <div class="muted-text">僅系統管理員可用；仍會經過 SQL Guard，只允許 SELECT / WITH SELECT。ENV=EXT 時 Oracle 只回傳 SQL ONLY，不連線執行。</div>
      <textarea id="adminSqlInput" placeholder="SELECT *
FROM CT_EMPLOYEE
WHERE ROWNUM <= 10;" disabled></textarea>
      <div class="sql-test-actions">
        <input id="adminSqlMaxRowsInput" type="number" min="1" max="1000" value="100" aria-label="最多回傳筆數" disabled>
        <button class="btn btn-primary" onclick="executeAdminSqlTest(this)" disabled>執行 SQL 測試</button>
      </div>
      <div class="result-section sql-test-result" style="display:none;"></div>
    </div>

    <div class="training-section-nav" aria-label="區段導覽">
      <button type="button" class="section-chip" onclick="document.getElementById('ddlTrainingSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' })">DDL</button>
      <button type="button" class="section-chip" onclick="document.getElementById('documentationTrainingSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' })">Documentation</button>
      <button type="button" class="section-chip" onclick="document.getElementById('sqlTrainingSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' })">SQL Examples</button>
      <button type="button" class="section-chip" onclick="document.getElementById('failedTrainingSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' })">Failed Queries</button>
    </div>

    <div class="training-section-grid">
      <div class="training-section training-section-card" id="ddlTrainingSection">
        <h3>DDL / Schema metadata</h3>
        <div class="table-wrapper training-table-wrap">
          <table class="result-table">
            <thead><tr><th>Table/View</th><th>Type</th><th>Columns</th><th>Status</th><th>操作</th></tr></thead>
            <tbody>${schemaRows || `<tr><td colspan="5">無 schema metadata</td></tr>`}</tbody>
          </table>
        </div>
      </div>
      <div class="training-section training-section-card" id="documentationTrainingSection">
        <h3>Documentation</h3>
        <div class="table-wrapper training-table-wrap">
          <table class="result-table">
            <thead><tr><th>Name</th><th>Content</th><th>???</th></tr></thead>
            <tbody>${documentationRows || `<tr><td colspan="3">??? documentation</td></tr>`}</tbody>
          </table>
        </div>
      </div>
      <div class="training-section training-section-card" id="sqlTrainingSection">
        <h3>SQL approved examples</h3>
        <div class="table-wrapper training-table-wrap">
          <table class="result-table">
            <thead><tr><th>Question</th><th>Status</th><th>Created by</th><th>???</th></tr></thead>
            <tbody>${exampleRows || `<tr><td colspan="4">??? approved examples</td></tr>`}</tbody>
          </table>
        </div>
      </div>
      <div class="training-section training-section-card" id="failedTrainingSection">
        <h3>Failed queries (??????????)</h3>
        <div class="table-wrapper training-table-wrap">
          <table class="result-table">
            <thead><tr><th>Question</th><th>Error Message</th><th>Status</th><th>???</th></tr></thead>
            <tbody>${(result.failed_queries || []).map(item => `
              <tr>
                <td>${escapeHtml(item.question)}</td>
                <td title="${escapeHtml(item.error_message)}">${escapeHtml((item.error_message || "").slice(0, 120))}</td>
                <td><code>${escapeHtml(item.status)}</code></td>
                <td>
                  <button class="btn btn-secondary mini-btn btn-edit-item" onclick="editTrainingItem(this, 'failed', ${item.id})">???</button>
                  <button class="btn btn-danger mini-btn btn-delete-item" onclick="deleteTrainingItem(this, 'failed', ${item.id})">???</button>
                </td>
              </tr>
            `).join("") || `<tr><td colspan="4">?????????</td></tr>`}</tbody>
          </table>
        </div>
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

  const bubbleEl = tabEl.closest(".msg-bubble");
  const testForm = bubbleEl ? bubbleEl.querySelector(".sql-test-form") : null;
  if (testForm) {
    const textarea = testForm.querySelector("#adminSqlInput");
    const input = testForm.querySelector("#adminSqlMaxRowsInput");
    const btn = testForm.querySelector("button");
    if (trainingType === "sql") {
      testForm.classList.remove("disabled-form");
      if (textarea) textarea.disabled = false;
      if (input) input.disabled = false;
      if (btn) btn.disabled = false;
    } else {
      testForm.classList.add("disabled-form");
      if (textarea) textarea.disabled = true;
      if (input) input.disabled = true;
      if (btn) btn.disabled = true;
    }
  }
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

  if (trainingType === "failed") {
    const question = formEl.querySelector("#failedQuestionInput").value.trim();
    const sql = formEl.querySelector("#failedSqlInput").value.trim();
    const analysis = formEl.querySelector("#failedAnalysisInput").value.trim();
    const action_taken = formEl.querySelector("#failedActionInput").value.trim();
    const status = formEl.querySelector("#failedStatusSelect").value;
    if (!question || !sql) {
      throw new Error("問題與 SQL 欄位不可為空。");
    }
    return { training_type: "failed", question, sql, analysis, action_taken, status };
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

  const editingId = formEl.dataset.editingId;
  const isEditing = !!editingId;
  const method = isEditing ? "PUT" : "POST";
  if (isEditing) {
    payload.id = parseInt(editingId, 10);
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = isEditing ? `<div class="spinner"></div> 更新中...` : `<div class="spinner"></div> 新增中...`;
  fetch(apiurl("/nl2sql/api/vanna/training-dataset/"), {
    method: method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: formEl.dataset.dataSourceCode || bubbleEl.trainingDatasetResult?.primary_data_source_code || TRAINING_DATASET_CODE,
      ...payload
    })
  })
  .then(res => res.json())
  .then(data => {
    if (!data.ok) {
      addLog(`${isEditing ? "更新" : "新增"}訓練資料失敗: ${data.error}`, "error");
      return;
    }
    addLog(`已${isEditing ? "更新" : "新增"} ${trainingType} 訓練資料，請執行 Vanna Sync 使資料生效。`, "success");
    resetTrainingForm(formEl);
    const allItems = bubbleEl.dataset.allItems === "true";
    loadTrainingDataset(bubbleEl, allItems);
  })
  .catch(err => {
    addLog(`${isEditing ? "更新" : "新增"}訓練資料失敗: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

function editTrainingItem(btn, type, id) {
  const bubbleEl = btn.closest(".msg-bubble");
  const result = bubbleEl.trainingDatasetResult;
  if (!result) return;

  const formEl = bubbleEl.querySelector(".training-form.training-data-form") || bubbleEl.querySelector(".training-form");
  const tabBtn = formEl.querySelector(`.training-type-tab[data-training-type="${type}"]`);
  if (tabBtn) {
    selectTrainingType(tabBtn);
  }

  formEl.dataset.editingId = id;
  formEl.dataset.editingType = type;

  const submitBtn = formEl.querySelector("button.btn-primary, button.btn-update-action");
  if (submitBtn) {
    submitBtn.innerText = "更新訓練資料";
    submitBtn.className = "btn btn-primary btn-update-action";
  }
  
  let cancelBtn = formEl.querySelector(".btn-cancel-edit");
  if (!cancelBtn) {
    cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary btn-cancel-edit";
    cancelBtn.innerText = "取消編輯";
    cancelBtn.style.marginLeft = "10px";
    cancelBtn.onclick = () => resetTrainingForm(formEl);
    submitBtn.parentNode.appendChild(cancelBtn);
  }

  if (type === "ddl") {
    const item = findTrainingItemById(result, type, id);
    if (item) {
      formEl.querySelector("#trainingDdlInput").value = item.ddl || "";
      formEl.dataset.dataSourceCode = item.data_source_code || result.primary_data_source_code || "";
    }
  } else if (type === "documentation") {
    const item = findTrainingItemById(result, type, id);
    if (item) {
      const lines = (item.documentation || "").split("\n");
      let title = "";
      let documentation = item.documentation || "";
      if (lines.length > 1 && lines[0].trim().length < 80) {
        title = lines[0];
        documentation = lines.slice(1).join("\n");
      }
      formEl.querySelector("#trainingDocTitleInput").value = title;
      formEl.querySelector("#trainingDocInput").value = documentation;
      formEl.dataset.dataSourceCode = item.data_source_code || result.primary_data_source_code || "";
    }
  } else if (type === "sql") {
    const item = findTrainingItemById(result, type, id);
    if (item) {
      formEl.querySelector("#trainingQuestionInput").value = item.question || "";
      formEl.querySelector("#trainingSqlInput").value = item.sql || "";
      formEl.dataset.dataSourceCode = item.data_source_code || result.primary_data_source_code || "";
    }
  } else if (type === "failed") {
    const item = findTrainingItemById(result, type, id);
    if (item) {
      formEl.querySelector("#failedQuestionInput").value = item.question || "";
      formEl.querySelector("#failedSqlInput").value = item.failed_sql || "";
      formEl.querySelector("#failedErrorInput").value = item.error_message || "";
      formEl.querySelector("#failedAnalysisInput").value = item.analysis || "";
      formEl.querySelector("#failedActionInput").value = item.action_taken || "";
      formEl.querySelector("#failedStatusSelect").value = item.status || "pending";
      formEl.dataset.dataSourceCode = item.data_source_code || result.primary_data_source_code || "";
    }
  }

  formEl.scrollIntoView({ behavior: "smooth" });
}

function resetTrainingForm(formEl) {
  delete formEl.dataset.editingId;
  delete formEl.dataset.editingType;
  delete formEl.dataset.dataSourceCode;
  
  const submitBtn = formEl.querySelector(".btn-update-action, button.btn-primary");
  if (submitBtn) {
    submitBtn.innerText = "新增到訓練資料集";
    submitBtn.className = "btn btn-primary";
  }

  const cancelBtn = formEl.querySelector(".btn-cancel-edit");
  if (cancelBtn) {
    cancelBtn.remove();
  }

  formEl.querySelector("#trainingDdlInput").value = "";
  formEl.querySelector("#trainingDocTitleInput").value = "";
  formEl.querySelector("#trainingDocInput").value = "";
  formEl.querySelector("#trainingQuestionInput").value = "";
  formEl.querySelector("#trainingSqlInput").value = "";
  formEl.querySelector("#failedQuestionInput").value = "";
  formEl.querySelector("#failedSqlInput").value = "";
  formEl.querySelector("#failedErrorInput").value = "";
  formEl.querySelector("#failedAnalysisInput").value = "";
  formEl.querySelector("#failedActionInput").value = "";
  formEl.querySelector("#failedStatusSelect").value = "pending";
}

function deleteTrainingItem(btn, type, id) {
  if (!confirm("確定要刪除此筆訓練資料嗎？此動作將同時清除相關的 Vanna 同步與 Embedding 記錄，且無法復原。")) {
    return;
  }

  const bubbleEl = btn.closest(".msg-bubble");
  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = "...";

  fetch(apiurl("/nl2sql/api/vanna/training-dataset/"), {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: bubbleEl.trainingDatasetResult?.primary_data_source_code || TRAINING_DATASET_CODE,
      data_source_code: (findTrainingItemById(bubbleEl.trainingDatasetResult, type, id) || {}).data_source_code || "",
      training_type: type,
      id: id
    })
  })
  .then(res => res.json())
  .then(data => {
    if (!data.ok) {
      addLog(`刪除訓練資料失敗: ${data.error}`, "error");
      btn.disabled = false;
      btn.innerHTML = originalText;
      return;
    }
    addLog(`已刪除該筆 ${type} 訓練資料，請執行 Vanna Sync 使資料生效。`, "success");
    const allItems = bubbleEl.dataset.allItems === "true";
    loadTrainingDataset(bubbleEl, allItems);
  })
  .catch(err => {
    addLog(`刪除訓練資料失敗: ${err.message}`, "error");
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
      if (r.context_summary && r.context_summary.related_questions && r.context_summary.related_questions.length > 0) {
        const related = dedupeQuestions(r.context_summary.related_questions, question);
        const dynamicPart = related.slice(0, 3);
        const defaultQs = buildDefaultPresetQuestions();
        const finalQuestions = [...dynamicPart];
        for (let i = 0; i < defaultQs.length; i++) {
          if (finalQuestions.length >= 10) break;
          const q = defaultQs[i];
          const normQ = normalizeForDedupe(q);
          const isDuplicate = finalQuestions.some(existing => normalizeForDedupe(existing) === normQ);
          if (!isDuplicate) {
            finalQuestions.push(q);
          }
        }
        renderPresetQuestions(finalQuestions);
      }
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
  const canViewSqlCommand = result.can_view_sql_command === true;
  const shouldAutoExecute = guardStatus === "passed" && executionPolicy.mode === "oracle_execute" && Boolean(queryLogId);

  let guardHtml = "";
  let policyHtml = "";
  let sqlHtml = "";
  let resultsHtml = queryLogId ? `<div id="results-container-${queryLogId}" class="result-section" style="display:none;"></div>` : "";

  if (policyMessage) {
    const policyClass = canExecute ? "passed" : "blocked";
    policyHtml = `<div class="guard-banner ${policyClass}">${escapeHtml(policyMessage)}</div>`;
  }

  if (guardStatus === "passed") {
    guardHtml = `<div class="guard-banner passed">SQL Guard: passed</div>`;
    if (canViewSqlCommand && sql) {
      sqlHtml = `
        <div class="sql-container">
          <div class="sql-header">
            <span>SQL Query</span>
            <button class="btn btn-secondary" style="padding: 4px 8px; font-size:11px;" onclick="navigator.clipboard.writeText(\`${escapeJs(sql)}\`); addLog('SQL 已複製到剪貼簿', 'success');">複製</button>
          </div>
          <pre><code>${escapeHtml(sql)}</code></pre>
        </div>
      `;
    } else {
      sqlHtml = `<div class="guard-banner passed">已通過 SQL Guard；依權限不顯示 SQL 指令內容。</div>`;
    }
    if (shouldAutoExecute) {
      resultsHtml = `<div id="results-container-${queryLogId}" class="result-section" style="display:block;"><div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 自動執行 Oracle 查詢中...</div></div>`;
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
    ${sqlHtml}
    ${guardHtml}
    ${policyHtml}
    ${resultsHtml}
  `;

  if (shouldAutoExecute) {
    setTimeout(() => runQuery(queryLogId), 0);
  }
}

// 6. 唯讀執行查詢
function runQuery(queryLogId, btn) {
  let originalText = "";
  if (btn) {
    originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<div class="spinner"></div> 執行中...`;
  }
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
    .replace(/'/g, "\\'")
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

function testCurrentSql(btn) {
  const fieldsEl = btn.closest(".training-fields");
  const sqlEl = fieldsEl.querySelector("#trainingSqlInput");
  const maxRowsEl = fieldsEl.querySelector("#currentSqlMaxRowsInput");
  const resultEl = fieldsEl.querySelector(".current-sql-test-result");
  const sql = sqlEl.value.trim();
  const maxRows = parseInt(maxRowsEl.value || "10", 10);

  if (!sql) {
    addLog("請輸入 SQL 後再執行測試。", "error");
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 執行中...`;
  resultEl.style.display = "block";
  resultEl.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 正在執行 SQL 測試...</div>`;
  addLog("訓練編輯器 SQL 測試開始執行。", "info");

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
      max_rows: Number.isFinite(maxRows) ? maxRows : 10
    })
  })
  .then(res => responseTextOrJson(res))
  .then(data => {
    if (!data.ok) {
      resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>執行失敗:</strong><br>${escapeHtml(data.error)}</div>`;
      addLog(`編輯器 SQL 測試失敗: ${data.error}`, "error");
      return;
    }
    addLog(`編輯器 SQL 測試成功，取得 ${(data.rows || []).length} 筆資料。`, "success");
    renderResultTable(resultEl, data);
  })
  .catch(err => {
    const statusText = err.status ? `HTTP ${err.status}` : "連線錯誤";
    const urlText = err.url || endpoint;
    resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>執行失敗 (${escapeHtml(statusText)}):</strong><br>${escapeHtml(err.message)}<br><small>URL: ${escapeHtml(urlText)}</small></div>`;
    addLog(`編輯器 SQL 測試失敗: ${statusText} ${urlText}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

function debugRagPrompt(btn) {
  const formEl = btn.closest(".rag-debugger-form");
  const questionEl = formEl.querySelector("#ragDebugQuestionInput");
  const resultEl = formEl.querySelector(".rag-debug-result");
  const question = questionEl.value.trim();

  if (!question) {
    addLog("請輸入提問後再執行除錯檢索。", "error");
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> 檢索中...`;
  resultEl.style.display = "block";
  resultEl.innerHTML = `<div style="display:flex;align-items:center;gap:10px;"><div class="spinner" style="border-top-color:#06b6d4;"></div> 正在進行 RAG 檢索與 Prompt 組裝...</div>`;
  addLog("開始執行 RAG Prompt 除錯檢索...", "info");

  fetch(apiurl("/nl2sql/api/vanna/rag-debug/"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCookie("csrftoken")
    },
    body: JSON.stringify({
      code: selectedDataSourceCode(),
      question: question
    })
  })
  .then(res => responseTextOrJson(res))
  .then(data => {
    if (!data.ok) {
      resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>檢索失敗:</strong><br>${escapeHtml(data.error)}</div>`;
      addLog(`RAG 檢索失敗: ${data.error}`, "error");
      return;
    }
    
    addLog("RAG 檢索與 Prompt 組裝完成。", "success");

    let seHtml = (data.schema_matches || []).map(item => `
      <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); padding:8px 12px; border-radius:8px; margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <strong>🗂️ ${escapeHtml(item.schema_name)}.${escapeHtml(item.object_name)} (${escapeHtml(item.chunk_type)})</strong>
          <span style="color:#14b8a6; font-weight:700;">相似度: ${(item.similarity * 100).toFixed(2)}% (Cos: ${item.distance.toFixed(4)})</span>
        </div>
        <pre style="margin:0; padding:6px; font-size:11.5px; background:#0f172a; border-radius:4px; max-height:120px; overflow-y:auto; color:#a5f3fc;"><code style="font-size:11.5px; color:#a5f3fc;">${escapeHtml(item.chunk_text)}</code></pre>
      </div>
    `).join("") || `<div style="color:#94a3b8; font-style:italic;">無 SchemaEmbedding 向量匹配結果 (可能未計算向量)</div>`;

    let eeHtml = (data.example_matches || []).map(item => `
      <div style="background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06); padding:8px 12px; border-radius:8px; margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
          <strong>💬 問題: ${escapeHtml(item.question)}</strong>
          <span style="color:#14b8a6; font-weight:700;">相似度: ${(item.similarity * 100).toFixed(2)}% (Cos: ${item.distance.toFixed(4)})</span>
        </div>
        <pre style="margin:0; padding:6px; font-size:11.5px; background:#0f172a; border-radius:4px; max-height:120px; overflow-y:auto; color:#a5f3fc;"><code style="font-size:11.5px; color:#38bdf8;">${escapeHtml(item.sql)}</code></pre>
      </div>
    `).join("") || `<div style="color:#94a3b8; font-style:italic;">無 ExampleEmbedding 向量匹配結果 (可能未計算向量)</div>`;

    resultEl.innerHTML = `
      <div>
        <strong style="color:#38bdf8; display:block; margin-bottom:6px;">1. SchemaEmbedding (DDL / Documentation 向量匹配)</strong>
        ${seHtml}
      </div>
      <div>
        <strong style="color:#38bdf8; display:block; margin-bottom:6px;">2. ExampleEmbedding (Approved SQL 範例向量匹配)</strong>
        ${eeHtml}
      </div>
      <div>
        <strong style="color:#38bdf8; display:block; margin-bottom:6px;">3. 組裝後 LLM 系統提示詞 (Final Assembled Prompt)</strong>
        <textarea style="font-family:monospace; font-size:12px; min-height:220px; background:#0f172a; color:#e2e8f0; width:100%;" readonly>${escapeHtml(data.prompt)}</textarea>
      </div>
    `;
  })
  .catch(err => {
    resultEl.innerHTML = `<div style="color:#ef4444;padding:12px;border:1px solid rgba(239,68,68,0.2);border-radius:8px;background:rgba(239,68,68,0.05);"><strong>檢索失敗:</strong><br>${escapeHtml(err.message)}</div>`;
    addLog(`RAG 檢索連線錯誤: ${err.message}`, "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = originalText;
  });
}

// 9. 綁定按鈕監聽 (等 DOMContentLoaded)
document.addEventListener("DOMContentLoaded", () => {
  addLog("Vanna 2.0 整合對話工作區已載入。", "success");
  renderPresetQuestions(buildDefaultPresetQuestions());

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

// webapps/meetingreply/static/meetingreply/js/index.js
(() => {
  "use strict";

// ============================================================
// ✅ 專案規範：全專案共用 apiurlFn（唯一入口）
// - 真正對外函式名稱以專案為準：多數是 window.apiurl(path)
// - 為避免互相干擾：同時相容舊版 window.apiurlFn
// - 若 helper 未載入：提供最小 fallback（避免整支 JS 掛掉）
// ============================================================
function _normPrefix(p) {
  let s = String(p || "").trim();
  if (!s) return "";
  if (!s.startsWith("/")) s = "/" + s;
  while (s.length > 1 && s.endsWith("/")) s = s.slice(0, -1);
  return s === "/" ? "" : s;
}

function _getBaseUrl() {
  const body = document.body;
  if (!body || !body.dataset) return "";
  return _normPrefix(body.dataset.baseUrl || "");
}

function _getAaa() {
  try {
    return new URLSearchParams(window.location.search).get("aaa") || "";
  } catch {
    return "";
  }
}

function _appendAaa(url) {
  const aaa = _getAaa();
  if (!aaa) return url;
  try {
    const u = new URL(url, window.location.origin);
    if (u.origin !== window.location.origin) return url;
    if (!u.searchParams.get("aaa")) u.searchParams.set("aaa", aaa);
    return u.pathname + u.search + u.hash;
  } catch {
    if (String(url).includes("aaa=")) return String(url);
    return String(url).includes("?")
      ? `${url}&aaa=${encodeURIComponent(aaa)}`
      : `${url}?aaa=${encodeURIComponent(aaa)}`;
  }
}

function _fallbackApiurl(path) {
  const base = _getBaseUrl();
  let p = String(path || "").trim();
  if (!p) return _appendAaa(base || "/");
  if (p.startsWith("http://") || p.startsWith("https://")) return _appendAaa(p);
  if (!p.startsWith("/")) p = "/" + p;
  if (base && (p === base || p.startsWith(base + "/"))) {
    p = p.slice(base.length) || "/";
    if (!p.startsWith("/")) p = "/" + p;
  }
  return _appendAaa(base + p);
}

const hasApiurl =
  typeof window.apiurl === "function" || typeof window.apiurlFn === "function";
const apiurlFn =
  (typeof window.apiurl === "function" && window.apiurl) ||
  (typeof window.apiurlFn === "function" && window.apiurlFn) ||
  _fallbackApiurl;

if (!hasApiurl) {
  console.warn(
    "apiurl helper not found; using fallback apiurl. Please ensure static 'portal/js/apiurl_factory.js' is loaded."
  );
}


  const $ = (id) => document.getElementById(id);
  const ENV = String(document.body?.dataset?.env || "").trim().toUpperCase();
  const INT_TODO_URL = String(document.body?.dataset?.intTodoUrl || "").trim();
  const MOCK_TODO_URL = String(document.body?.dataset?.mockTodoUrl || "").trim();

  // ============================================================
  // ✅ API path（只讀 dataset；template 只提供「內部路徑字串」不 reverse）
  // - 例如：meetingreply/api/rag_only/ 、 meetingreply/api/build_reply/
  // - 真正請求 URL 必須經 apiurlFn() 補上 baseUrl(prefix)
  // ============================================================
  function _datasetKeyToAttr(key) {
    return `data-${String(key).replace(/[A-Z]/g, (m) => "-" + m.toLowerCase())}`;
  }

  function _normalizeInternalPath(p) {
    // ✅ 為避免互相干擾：允許 template 給 "meetingreply/..." 或 "/meetingreply/..."
    // 統一成 "meetingreply/..."（不以 "/" 開頭），交給 apiurlFn 組 prefix
    let s = String(p || "").trim();
    while (s.startsWith("/")) s = s.slice(1);
    return s;
  }

  function apiPathFromDataset(key) {
    const ds = document.body && document.body.dataset ? document.body.dataset : {};
    const raw = String(ds[key] || "").trim();
    if (!raw) {
      throw new Error(`Missing required dataset: ${_datasetKeyToAttr(key)}`);
    }
    return _normalizeInternalPath(raw);
  }

function apiFromDatasetPath(key) {
  const p = apiPathFromDataset(key);
  return apiurlFn(p);
}


  // ✅ 與新版 HTML 對齊：
  // <body data-api-rag-path="meetingreply/api/rag_only/" data-api-build-path="meetingreply/api/build_reply/">
  const API_TODO = () => apiFromDatasetPath("apiTodoPath");
  const API_RAG_ONLY = () => apiFromDatasetPath("apiRagPath");
  const API_BUILD = () => apiFromDatasetPath("apiBuildPath");

  // ============================================================
  // state
  // ============================================================
  let lastRag = { ok: false, sources: [] };
  let mode = "long";
  window.__lastMeetingShort = "";
  window.__lastMeetingLong = "";
  let _todoRows = [];
  let _busyTodo = false;

  // ============================================================
  // UI helpers
  // ============================================================
  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function stripHtml(s) {
    let t = String(s || "");
    if (!t) return "";
    t = t.replace(/<br\s*\/?>/gi, "\n");
    t = t.replace(/<\/p>/gi, "\n");
    t = t.replace(/<[^>]+>/g, "");
    t = t.replace(/&nbsp;/gi, " ");
    t = t.replace(/&amp;/gi, "&");
    t = t.replace(/&lt;/gi, "<");
    t = t.replace(/&gt;/gi, ">");
    t = t.replace(/&quot;/gi, '"');
    t = t.replace(/&#39;/gi, "'");
    return t.trim();
  }

  function setText(id, text) {
    const el = $(id);
    if (el) el.textContent = String(text ?? "");
  }

  function setHTML(id, html) {
    const el = $(id);
    if (el) el.innerHTML = html;
  }

  function setTodoPickVisible(flag) {
    const el = $("todoPickWrap");
    if (!el) return;
    el.style.display = flag ? "" : "none";
  }

  // ============================================================
  // todo list helpers
  // ============================================================
  function pickVal(obj, keys) {
    obj = obj || {};
    for (const k of keys) {
      const v = obj[k];
      if (v !== undefined && v !== null && String(v).trim() !== "") return String(v).trim();
    }
    return "";
  }

  function clipText(s, maxLen = 60) {
    const t = String(s || "").trim();
    if (!t) return "";
    return t.length > maxLen ? t.slice(0, maxLen) + "…" : t;
  }

  function buildTodoLabel(row, idx) {
    const id =
      pickVal(row, ["item_no", "ItemNo", "ITEMNO", "case_id", "CaseID", "case_no", "doc_id", "id"]) ||
      String(idx + 1);
    const title = stripHtml(
      pickVal(row, ["meeting_name", "case_name", "title", "Title", "TITLE", "subject", "案件名稱", "會議名稱"])
    );
    const directive = pickVal(row, ["directive", "指裁示", "contents", "content", "事項", "item"]);
    let label = `${idx + 1}. ${id}`;
    if (title) label += `｜${clipText(title, 40)}`;
    if (directive) label += `｜${clipText(directive, 40)}`;
    return label;
  }

  function buildDirectiveTextFromTodo(row) {
    const meetingName = stripHtml(
      pickVal(row, ["meeting_name", "case_name", "subject", "案件名稱", "會議名稱"])
    );
    const rawTitle = stripHtml(pickVal(row, ["title", "Title", "TITLE"]));
    const caseId = pickVal(row, ["case_id", "CaseID"]);
    const itemNo = pickVal(row, ["item_no", "ItemNo", "ITEMNO"]);
    let directive = stripHtml(
      pickVal(row, ["directive", "指裁示", "contents", "content", "事項", "item", "todo"])
    );
    if (!directive && rawTitle) directive = rawTitle;
    const status = stripHtml(pickVal(row, ["status", "進度", "DeptContents", "dept_contents"]));
    const dept = stripHtml(pickVal(row, ["dept", "dept_factory", "unit", "承辦單位"]));
    const due = pickVal(row, ["due_date", "finish_date", "期限", "Dte_Finish", "dte_finish"]);

    const lines = [];
    if (meetingName) lines.push(`會議名稱：${meetingName}`);
    if (caseId) lines.push(`CaseID：${caseId}`);
    if (itemNo) lines.push(`ItemNo：${itemNo}`);
    if (directive) lines.push(`指裁示：\n${directive}`);
    if (status) lines.push(`執行情形：\n${status}`);
    if (dept) lines.push(`承辦單位：${dept}`);
    if (due) lines.push(`期限：${due}`);

    if (lines.length) return lines.join("\n");

    const rawText = stripHtml(pickVal(row, ["text", "raw_text", "content_text", "memo"]));
    if (rawText) return rawText;

    return "";
  }

  function renderTodoOptions(rows) {
    const elPick = $("todoPick");
    if (!elPick) return;
    elPick.innerHTML = "";
    const opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "（請選擇）";
    elPick.appendChild(opt0);

    (rows || []).forEach((r, idx) => {
      const opt = document.createElement("option");
      opt.value = String(idx);
      opt.textContent = buildTodoLabel(r, idx);
      elPick.appendChild(opt);
    });
  }

  function applyTodoToDirective(silent = false, opts = null) {
    const elPick = $("todoPick");
    let idx = elPick ? parseInt(String(elPick.value || ""), 10) : NaN;
    if (isNaN(idx) && opts && typeof opts.index === "number") {
      idx = opts.index;
      if (elPick) elPick.value = String(idx);
    }
    if (isNaN(idx)) {
      if (!silent) alert("請先選擇一筆待辦");
      return;
    }
    const picked = _todoRows[idx] || {};
    const text = buildDirectiveTextFromTodo(picked);
    if (!text) {
      if (!silent) alert("待辦內容無法帶入指裁示事項");
      return;
    }
    if ($("directive")) $("directive").value = text;
    setText("todoStatus", `已帶入第 ${idx + 1} 筆待辦`);
  }

  async function loadTodoList() {
    if (_busyTodo) return;
    _busyTodo = true;
    if ($("btnTodoLoad")) $("btnTodoLoad").disabled = true;
    setText("todoStatus", "載入待辦中…");

    try {
      let j;
      if (ENV === "INT") {
        const url =
          INT_TODO_URL ||
          "https://www.mpc.mil.tw/notificationsingleton/WebService/CaseManager/UnHandle_Item_AssignJson.ashx";
        const resp = await fetch(url, {
          method: "POST",
          body: JSON.stringify({ aaa: new URLSearchParams(window.location.search).get("aaa") }),
          headers: { "Accept": "application/json" },
        });
        j = await readJsonOrThrow(resp);
      } else {
        if (!MOCK_TODO_URL) {
          throw new Error("missing mock todo url");
        }
        const resp = await fetch(MOCK_TODO_URL, { method: "GET" });
        j = await readJsonOrThrow(resp);
      }
      let items = [];
      if (Array.isArray(j)) items = j;
      else if (Array.isArray(j.items)) items = j.items;
      else if (Array.isArray(j.rows)) items = j.rows;
      else if (Array.isArray(j.data)) items = j.data;
      else if (Array.isArray(j.list)) items = j.list;

      _todoRows = items || [];
      renderTodoOptions(_todoRows);
      setText("todoStatus", `待辦 ${_todoRows.length} 筆`);
      if (_todoRows.length > 0) {
        applyTodoToDirective(true, { index: 0 });
        setTodoPickVisible(true);
      } else {
        setTodoPickVisible(true);
      }
    } catch (e) {
      console.error(e);
      setText("todoStatus", "載入待辦失敗：" + (e?.message || String(e)));
    } finally {
      _busyTodo = false;
      if ($("btnTodoLoad")) $("btnTodoLoad").disabled = false;
    }
  }

  // ============================================================
  // input validators
  // ============================================================
  function mustDirectiveOrStaff() {
    const d = ($("directive")?.value || "").trim();
    const s = ($("staff")?.value || "").trim();
    if (!d && !s) {
      alert("請先輸入「指裁示事項」或「參謀想法」");
      return "";
    }
    return d || s;
  }

  function mustDirective() {
    const d = ($("directive")?.value || "").trim();
    if (!d) {
      alert("請先輸入「指裁示事項」");
      return "";
    }
    return d;
  }

  // ============================================================
  // tabs
  // ============================================================
  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
      t.classList.add("active");
      mode = t.dataset.mode || "long";
      const out = mode === "long" ? window.__lastMeetingLong : window.__lastMeetingShort;
      if ($("genOut")) $("genOut").textContent = out || "";
    });
  });

  // ============================================================
  // normalize hits
  // ============================================================
  function normalizeSources(src) {
    if (Array.isArray(src)) return src;

    if (src && typeof src === "object") {
      return Object.keys(src).map((k) => {
        const v = src[k] || {};
        return {
          doc_id: v.doc_id || v.id || k,
          id: v.id || k,
          distance: v.distance ?? v.dist ?? null,
          dist: v.dist ?? v.distance ?? null,
          snippet: v.snippet || v.text || v.document || "",
          metadata: v.metadata || v.meta || {},
        };
      });
    }
    return [];
  }

  function getDocId(h) {
    const m = (h && (h.meta || h.metadata)) || {};
    return String(h.doc_id || m.doc_id || h.id || "").trim();
  }

  function getHitKey(h) {
    const docId = getDocId(h);
    return docId || String(h?.id || "").trim();
  }

  function getDist(h) {
    const v = h && (h.distance ?? h.dist);
    if (v === undefined || v === null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }

  function clipBlock(text, maxLen = 180) {
    const s = String(text || "").replace(/\s+/g, " ").trim();
    if (!s) return "";
    return s.length > maxLen ? s.slice(0, maxLen) + "..." : s;
  }

  // ============================================================
  // snippet formatting
  // ============================================================
  function formatSnippetForPickList(raw, meta = {}) {
    const text = String(raw || "").replace(/\r/g, "").trim();
    const m = meta && typeof meta === "object" ? meta : {};

    const lines = text ? text.split("\n").map((x) => x.trim()).filter(Boolean) : [];
    const pickVal = (keys) => {
      for (const ln of lines) {
        for (const key of keys) {
          const esc = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
          const re = new RegExp("^" + esc + "\\s*[:=：]\\s*(.*)$", "i");
          const match = ln.match(re);
          if (match && match[1] !== undefined) return match[1].trim();
        }
      }
      return "";
    };

    const meetingName = String(
      m.case_name || m.meeting_name || m.title || pickVal(["案件名稱", "會議名稱", "會議名稱"])
    ).trim();
    const directive = String(
      m.directive || pickVal(["指裁示內容", "指裁示", "指示", "裁示"])
    ).trim();
    const status = String(
      m.status || pickVal(["辦理情形/擬答", "辦理情形", "辦理狀況", "辦理結果", "辦況"])
    ).trim();
    const deptName = String(
      m.dept_name || m.dept || pickVal(["主辦單位", "回覆單位", "廠別"])
    ).trim();
    const updatedAt = String(
      m.updated_at || pickVal(["回覆日期", "核定日", "審定日"])
    ).trim();

    const out = [];
    if (meetingName) out.push(`會議名稱：${meetingName}`);
    if (directive) out.push(`指裁示：${clipBlock(directive, 160)}`);
    if (status) out.push(`辦理情形：${clipBlock(status, 160)}`);

    const tail = [];
    if (deptName) tail.push(`主辦單位：${deptName}`);
    if (updatedAt) tail.push(`日期：${updatedAt}`);
    if (tail.length) out.push(tail.join("   "));

    if (out.length) return out.join("\n");
    return lines.slice(0, 6).join("\n");
  }

  function getSnippet(h) {
    const meta = (h && (h.meta || h.metadata)) || {};
    const raw = String(h?.snippet || h?.text || h?.document || "").trim();
    return formatSnippetForPickList(raw, meta);
  }

  function getMeta(h) {
    return (h && (h.meta || h.metadata)) || {};
  }

  // ============================================================
  // selection UI
  // ============================================================
  function setSelCount() {
    const n = document.querySelectorAll(".pickCk:checked").length;
    setText("selCount", String(n));
  }

  function renderPickList(rawHits) {
    const hits = normalizeSources(rawHits || []);
    setText("hitCount", String(hits.length));
    setText("selCount", "0");
    if ($("pickList")) $("pickList").innerHTML = "";

    if (!hits.length) {
      setHTML("pickList", `<div class="muted">（hits=0）</div>`);
      return;
    }

    hits.slice(0, 10).forEach((h, i) => {
      const key = getHitKey(h);
      const docId = getDocId(h);
      const dist = getDist(h);
      const snip = getSnippet(h);
      const meta = getMeta(h);
      const meetingName = String(meta.case_name || meta.meeting_name || h.title || "").trim();
      const directive = clipBlock(meta.directive || "", 220);
      const status = clipBlock(meta.status || "", 220);
      const deptName = String(meta.dept_name || meta.dept || "").trim();
      const updatedAt = String(meta.updated_at || "").trim();
      const detailRows = [];
      if (meetingName) detailRows.push(`<div><b>會議名稱：</b>${escHtml(meetingName)}</div>`);
      if (directive) detailRows.push(`<div><b>指裁示：</b>${escHtml(directive)}</div>`);
      if (status) detailRows.push(`<div><b>辦理情形：</b>${escHtml(status)}</div>`);
      if (deptName || updatedAt) {
        detailRows.push(
          `<div><b>主辦單位：</b>${escHtml(deptName || "—")}　<b>日期：</b>${escHtml(updatedAt || "—")}</div>`
        );
      }

      let distPill = `<span class="pill warn">no distance</span>`;
      if (dist !== null) {
        if (dist <= 0.15) distPill = `<span class="pill good">dist=${dist}</span>`;
        else if (dist < 0.25) distPill = `<span class="pill warn">dist=${dist}</span>`;
        else distPill = `<span class="pill bad">dist=${dist}</span>`;
      }

      const disabled = !key;

      const el = document.createElement("div");
      el.className = "pickitem";
      el.innerHTML = `
        <div class="pickrow">
          <input class="pickCk" type="checkbox" ${disabled ? "disabled" : ""} value="${escHtml(key)}">
          <div class="pickmeta">
            <div class="picktop">
              <div class="pickid">[${i + 1}] ${escHtml(docId || key || "（missing id）")}</div>
              ${distPill}
            </div>
            <div class="snippet">${detailRows.length ? detailRows.join("") : (snip ? escHtml(snip) : "（無資料）")}</div>
          </div>
        </div>
      `;
      $("pickList")?.appendChild(el);
    });

    document.querySelectorAll(".pickCk").forEach((ck) => {
      ck.addEventListener("change", () => {
        const checked = Array.from(document.querySelectorAll(".pickCk:checked"));
        if (checked.length > 2) {
          ck.checked = false;
          alert("人工勾選最多只能納入 2 筆");
        }
        setSelCount();
      });
    });

    setSelCount();
  }

  $("btnClearSel")?.addEventListener("click", () => {
    document.querySelectorAll(".pickCk").forEach((x) => {
      if (!x.disabled) x.checked = false;
    });
    setSelCount();
  });

  function bestPick(maxN = 2) {
    const enabled = Array.from(document.querySelectorAll(".pickCk")).filter((x) => !x.disabled);
    enabled.forEach((x) => (x.checked = false));

    const hits = normalizeSources(lastRag.sources || []);
    const pairs = hits
      .map((h) => ({ dist: getDist(h), key: getHitKey(h) }))
      .filter((x) => x.key && x.dist !== null)
      .sort((a, b) => a.dist - b.dist);

    if (!pairs.length) {
      setSelCount();
      return;
    }

    const BASE_MAX = 0.15;
    const FALLBACK_MAX = 0.25;

    let chosen = [];
    const base = pairs.filter((p) => p.dist <= BASE_MAX);
    if (base.length) chosen = base.slice(0, maxN);
    else {
      const fb = pairs.filter((p) => p.dist < FALLBACK_MAX);
      chosen = fb.length ? fb.slice(0, maxN) : pairs.slice(0, maxN);
    }

    const chosenSet = new Set(chosen.map((x) => String(x.key)));
    enabled.forEach((ck) => {
      if (chosenSet.has(String(ck.value))) ck.checked = true;
    });
    setSelCount();
  }

  $("btnSelectBest")?.addEventListener("click", () => bestPick(2));

  // ============================================================
  // fetch helpers（✅ 專案規範：API 一律 JSON）
  // ============================================================
  function _formatAclDebug(j) {
    if (!j || typeof j !== "object") return "";
    const keys = ["error", "node", "auth", "is_authenticated", "username", "login_user", "path", "method"];
    const parts = [];
    for (const k of keys) {
      if (j[k] !== undefined && j[k] !== null && String(j[k]) !== "") {
        parts.push(`${k}=${j[k]}`);
      }
    }
    return parts.length ? `\nACL: ${parts.join(" | ")}` : "";
  }

  async function readJsonOrThrow(resp) {
    const text = await resp.text();

    if (!text || !String(text).trim()) {
      throw new Error(
        `API 回應空內容（可能被反代規則吃掉、或 upstream 未回 JSON）\n` +
          `status=${resp.status}\n` +
          `url=${resp.url}`
      );
    }

    let j;
    try {
      j = JSON.parse(text);
    } catch {
      const hint =
        `API 回應非 JSON（可能 URL 組合錯 / 被反代導頁 / ACL 回了 HTML）\n` +
        `status=${resp.status}\n` +
        `url=${resp.url}\n\n` +
        `前 200 字：\n` +
        `${String(text).slice(0, 200)}`;
      throw new Error(hint);
    }

    if (!resp.ok) {
      const msg = (j && (j.error || j.detail || j.message)) || `HTTP ${resp.status}`;
      throw new Error(msg + _formatAclDebug(j));
    }

    return j || {};
  }

  function _extractSourcesFromRagResponse(j) {
    const candidates = [j?.sources, j?.hits, j?.rag?.sources, j?.rag?.hits];
    for (const c of candidates) if (Array.isArray(c) || (c && typeof c === "object")) return c;
    return [];
  }

  // ============================================================
  // Step3: rag_only
  // ============================================================
  async function ragOnly() {
    const qBase = mustDirectiveOrStaff();
    if (!qBase) return;

    if ($("btnRag")) $("btnRag").disabled = true;
    setText("ragStatus", "⏳ RAG 查詢中…");
    setHTML("pickList", `<div class="muted">⏳ 檢索中…</div>`);
    setText("hitCount", "0");
    setText("selCount", "0");

    try {
      const url = API_RAG_ONLY();
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify({ q: qBase, k: Number($("k")?.value || 10) }),
      });

      const j = await readJsonOrThrow(resp);
      const sources = _extractSourcesFromRagResponse(j);

      lastRag = { ok: true, sources };

      const srcArr = normalizeSources(sources);
      if (srcArr.length === 0) {
        setHTML("ragStatus", "<span class='ok'>✅ 完成</span> <span class='muted'>（未命中類案）</span>");
      } else {
        setHTML("ragStatus", "<span class='ok'>✅ 完成</span>");
      }

      renderPickList(sources);
    } catch (e) {
      lastRag = { ok: false, sources: [] };
      setHTML("ragStatus", "<span class='err'>❌ " + escHtml(e?.message || String(e)) + "</span>");
      setHTML("pickList", `<div class="err">（RAG 失敗）</div>`);
    } finally {
      if ($("btnRag")) $("btnRag").disabled = false;
    }
  }

  // ============================================================
  // Step4: build_reply
  // ============================================================
  async function genWithManualOrAuto() {
    const d = mustDirective();
    if (!d) return;

    if (!lastRag.ok) await ragOnly();

    if ($("btnGen")) $("btnGen").disabled = true;
    setText("genStatus", "⏳ 生成中…");
    setText("genOut", "");

    try {
      const staffRaw = ($("staff")?.value || "").trim();

      const picks = Array.from(document.querySelectorAll(".pickCk:checked"))
        .map((x) => x.value)
        .filter(Boolean);

      const payload = { directive: d, staff: staffRaw };
      if (picks.length) {
        payload.manual_inject_sources = picks;
        payload.manual_inject_mode = "override";
      }

      const resp = await fetch(API_BUILD(), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const j = await readJsonOrThrow(resp);
      if (j && j.ok === false) throw new Error(j.error || "生成失敗");

      window.__lastMeetingShort = String(j.short || "").trim();
      window.__lastMeetingLong = String(j.long || "").trim();

      setHTML("genStatus", "<span class='ok'>✅ 完成</span>");
      setText("genOut", mode === "long" ? window.__lastMeetingLong : window.__lastMeetingShort);

      const ctx = j?.rag?.context ? String(j.rag.context) : "";
      setText("ragInjected", ctx || "（後端未勾選 / 無）");

      const meta = {
        note: j?.rag?.note || "",
        hits: Array.isArray(j?.rag?.hits) ? j.rag.hits.length : 0,
        injected: Array.isArray(j?.rag?.hits_injected) ? j.rag.hits_injected.length : 0,
        query: j?.rag?.query || "",
      };
      setText("ragMeta", JSON.stringify(meta, null, 2));
    } catch (e) {
      setHTML("genStatus", "<span class='err'>❌ " + escHtml(e?.message || String(e)) + "</span>");
    } finally {
      if ($("btnGen")) $("btnGen").disabled = false;
    }
  }

  // ============================================================
  // wire up
  // ============================================================
  $("btnTodoLoad")?.addEventListener("click", loadTodoList);
  $("btnTodoUse")?.addEventListener("click", () => applyTodoToDirective(false));
  $("todoPick")?.addEventListener("change", () => applyTodoToDirective(true));
  $("btnRag")?.addEventListener("click", ragOnly);
  $("btnGen")?.addEventListener("click", genWithManualOrAuto);
})();

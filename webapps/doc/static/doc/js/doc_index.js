// webapps/doc/static/doc/js/doc_index.js
(function () {
  "use strict";

  // =========================================================
  // ✅ 全專案共用：apiurl_factory（由 portal/js/apiurl_factory.js 提供）
  // - 只讀 document.body.dataset.baseUrl (= request.script_name)
  // =========================================================
  var apiurl_factory = window.apiurl_factory || function(path){
    var base = String((document.body && document.body.dataset && document.body.dataset.baseUrl) || "").trim();
    var p = String(path || "");
    if (p && p.charAt(0) !== "/") p = "/" + p;
    return base + p;
  };

// ============================================================
  // ✅ API endpoints
  // ============================================================
  const API_TEMPLATES = apiurl_factory("doc/templates/");
  const API_GENERATE = apiurl_factory("doc/generate/");
  const API_PARSE = apiurl_factory("doc/parse/");
  const API_PARSE_FOCUS = apiurl_factory("doc/parse_focus/");

  const API_INCOMING_LOOKUP = apiurl_factory("doc/incoming_lookup/");
  const API_INCOMING_FILE = apiurl_factory("doc/incoming_file/"); // + attach_key + "/"

  const DOC_TYPE_LABEL = {
    sign_memo: "簽呈",
    order_draft: "令稿",
    submit_draft: "呈稿",
    letter_draft: "函稿",
    note: "便籤",
  };

  const TAG_GROUPS = [
    "人事",
    "行政",
    "主財",
    "計劃",
    "資訊",
    "研發",
    "品保",
    "生產",
    "採購",
    "設施供應",
    "測情",
    "職安衛",
  ];

  const dom = {
    docType: document.getElementById("docType"),
    tplScope: document.getElementById("tplScope"),
    tagFilter: document.getElementById("tagFilter"),
    tplList: document.getElementById("tplList"),
    requirement: document.getElementById("requirement"),

    incomingText: document.getElementById("incomingText"),
    attachmentsText: document.getElementById("attachmentsText"),
    referenceText: document.getElementById("referenceText"),

    promptOut: document.getElementById("promptOut"),
    docResult: document.getElementById("docResult"),
    examplePreview: document.getElementById("examplePreview"),
    genMeta: document.getElementById("genMeta"),

    btnReloadTemplates: document.getElementById("btnReloadTemplates"),
    btnGenerate: document.getElementById("btnGenerate"),
    btnCopyPrompt: document.getElementById("btnCopyPrompt"),
    btnCopyDraft: document.getElementById("btnCopyDraft"),
    btnClearAll: document.getElementById("btnClearAll"),

    btnClearPrompt: document.getElementById("btnClearPrompt"),
    btnClearDraft: document.getElementById("btnClearDraft"),
    btnDownloadPromptTxt: document.getElementById("btnDownloadPromptTxt"),
    btnDownloadDraftTxt: document.getElementById("btnDownloadDraftTxt"),

    btnSaveDraftAsTemplate: document.getElementById("btnSaveDraftAsTemplate"),

    importTplFileInput: document.getElementById("importTplFileInput"),
    btnImportTplFile: document.getElementById("btnImportTplFile"),

    attachInput: document.getElementById("attachInput"),
    btnParseAttach: document.getElementById("btnParseAttach"),
    attachStatus: document.getElementById("attachStatus"),

    exampleHint: document.getElementById("exampleHint"),
    btnExportTplJson: document.getElementById("btnExportTplJson"),
    btnExportTplCsv: document.getElementById("btnExportTplCsv"),
    btnExportTplTxt: document.getElementById("btnExportTplTxt"),

    btnSaveReferenceAsTemplate: document.getElementById("btnSaveReferenceAsTemplate"),

    saveTplModalOverlay: document.getElementById("saveTplModalOverlay"),
    btnCloseSaveTplModal: document.getElementById("btnCloseSaveTplModal"),
    btnCancelSaveTpl: document.getElementById("btnCancelSaveTpl"),
    btnConfirmSaveTpl: document.getElementById("btnConfirmSaveTpl"),
    saveTplTitle: document.getElementById("saveTplTitle"),
    saveTplDesc: document.getElementById("saveTplDesc"),
    saveTplScope: document.getElementById("saveTplScope"),
    saveTplConflict: document.getElementById("saveTplConflict"),
    saveTplTagPills: document.getElementById("saveTplTagPills"),
    saveTplCustomTags: document.getElementById("saveTplCustomTags"),
    saveTplContentPreview: document.getElementById("saveTplContentPreview"),
    saveTplHint: document.getElementById("saveTplHint"),
    saveTplModalSub: document.getElementById("saveTplModalSub"),

    // from doc/_incoming_sybase.html (may be null if include removed)
    qEmGrsno: document.getElementById("qEmGrsno"),
    qEmSno: document.getElementById("qEmSno"),
    btnLookupIncoming: document.getElementById("btnLookupIncoming"),
    incomingLookupStatus: document.getElementById("incomingLookupStatus"),
    incomingPick: document.getElementById("incomingPick"),
    btnApplyIncoming: document.getElementById("btnApplyIncoming"),
    btnLoadIncomingAttachments: document.getElementById("btnLoadIncomingAttachments"),

    incomingAttachBox: document.getElementById("incomingAttachBox"),
    incomingAttachList: document.getElementById("incomingAttachList"),
    btnIncomingAttachAll: document.getElementById("btnIncomingAttachAll"),
    btnIncomingAttachNone: document.getElementById("btnIncomingAttachNone"),
  };

  let templatesCache = [];
  let saveModalSource = "reference";

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function normalizeContentText(s) {
    let t = String(s || "");
    const pairs = [
      [/SLA/gi, "服務水準"],
      [/SOP/gi, "標準作業程序"],
      [/OEE/gi, "設備綜合效率"],
      [/MTTR/gi, "平均修復時間"],
      [/POC/gi, "概念驗證"],
      [/EDR/gi, "端點偵測回應"],
      [/MES/gi, "製造執行系統"],
      [/IIoT/gi, "工業物聯網"],
      [/SOC/gi, "資安監控中心"],
    ];
    for (const [re, rep] of pairs) t = t.replace(re, rep);
    return t;
  }

  function mapTagsToGroups(tags) {
    const raw = (tags || []).map((x) => String(x || "").trim()).filter(Boolean);
    const out = new Set();

    for (const tag of raw) {
      if (TAG_GROUPS.includes(tag)) {
        out.add(tag);
        continue;
      }

      if (
        [
          "主計",
          "主財",
          "預算",
          "經費",
          "核銷",
          "報支",
          "憑證",
          "會計",
          "出納",
          "決算",
          "概算",
          "追加",
          "控管",
          "補助",
          "分攤",
          "付款",
          "撥款",
          "請款",
        ].some((k) => tag.includes(k))
      ) {
        out.add("主財");
        continue;
      }
      if (
        [
          "測情",
          "情資",
          "情蒐",
          "研判",
          "通報",
          "預警",
          "態勢",
          "情勢",
          "威脅",
          "SOC",
          "事件",
          "資安事件",
          "告警",
          "監測",
        ].some((k) => tag.includes(k))
      ) {
        out.add("測情");
        continue;
      }

      if (
        [
          "系統",
          "資料",
          "看板",
          "網路",
          "程式",
          "資訊",
          "資安",
          "弱點",
          "掃描",
          "端點",
          "權限",
          "帳號",
          "維運",
          "監控",
          "備份",
          "機房",
          "伺服器",
          "資安監控中心",
        ].some((k) => tag.includes(k))
      )
        out.add("資訊");
      else if (["職安", "安全", "衛生", "工安", "環安"].some((k) => tag.includes(k)))
        out.add("職安衛");
      else if (["採購", "招標", "詢價", "廠商", "契約", "勞務", "開口", "框架"].some((k) => tag.includes(k)))
        out.add("採購");
      else if (
        ["設備", "設施", "供應", "設供", "維護", "保養", "治具", "工程", "修繕", "空調", "電力", "消防", "水電"].some((k) =>
          tag.includes(k)
        )
      )
        out.add("設施供應");
      else if (["生產", "產線", "排程", "產能", "稼動", "試量產", "備料", "物流", "倉儲"].some((k) => tag.includes(k)))
        out.add("生產");
      else if (["品管", "品保", "品質", "檢驗", "首件", "不良", "異常", "報廢", "RCA", "改善", "稽核"].some((k) => tag.includes(k)))
        out.add("品保");
      else if (["行政", "會議", "公告", "制度", "流程", "總務", "庶務", "文書"].some((k) => tag.includes(k)))
        out.add("行政");
      else if (["人事", "人力", "教育訓練", "派遣", "約用", "招募", "考績"].some((k) => tag.includes(k)))
        out.add("人事");
      else if (["研發", "設計", "驗證", "試驗", "新產品", "專利"].some((k) => tag.includes(k)))
        out.add("研發");
      else if (["計劃", "計畫", "專案", "專題", "里程碑", "年度計畫"].some((k) => tag.includes(k)))
        out.add("計劃");
    }

    if (out.size === 0 && raw.length) out.add("行政");
    return Array.from(out);
  }

  function buildTagOptions() {
    const select = dom.tagFilter;
    if (!select) return;
    select.innerHTML = `<option value="">全部</option>`;
    TAG_GROUPS.forEach((tag) => {
      const opt = document.createElement("option");
      opt.value = tag;
      opt.textContent = tag;
      select.appendChild(opt);
    });
    dom.tagFilter.value = TAG_GROUPS.indexOf("資訊") >= 0 ? "資訊" : "";
  }

  function getSelectedExampleIds() {
    return Array.from(document.querySelectorAll(".tplCk:checked"))
      .map((x) => parseInt(x.value, 10))
      .filter((n) => !isNaN(n));
  }

  function updateExampleHint() {
    if (!dom.exampleHint) return;
    const n = getSelectedExampleIds().length;
    const base = `已選擇：${n} 份（建議 1～3 份）`;
    if (n === 0) {
      dom.exampleHint.textContent = base + "；可先用「業務類別」縮小範圍。";
      dom.exampleHint.style.color = "#6b7280";
    } else if (n <= 3) {
      dom.exampleHint.textContent = base + "；效果最佳。";
      dom.exampleHint.style.color = "#2563eb";
    } else {
      dom.exampleHint.textContent = base + "；已超過建議，可能稀釋生成風格（建議保留 1～3 份）。";
      dom.exampleHint.style.color = "#ef4444";
    }
  }

  function renderExamplePreview() {
    if (!dom.examplePreview) return;

    const ids = getSelectedExampleIds();
    updateExampleHint();

    if (!ids.length) {
      dom.examplePreview.innerHTML = `<div class="muted">尚未選擇範例</div>`;
      return;
    }

    const selected = templatesCache.filter((t) => ids.includes(t.id));
    dom.examplePreview.innerHTML = "";

    selected.forEach((t) => {
      const item = document.createElement("div");
      item.className = "preview-item";

      const tagsHtml = (t.tags || [])
        .map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`)
        .join("");

      const scopeBadge =
        t.scope === "personal"
          ? `<span class="badge" style="background:rgba(107,114,128,0.12);color:#6b7280;">個人</span>`
          : `<span class="badge">公開</span>`;

      const previewText = (t.content_text || "").slice(0, 800);
      item.innerHTML = `
        <div style="font-weight:600; margin-bottom:6px;">
          ${escapeHtml(t.title)}
          <span class="muted">(#${t.id} / ${escapeHtml(DOC_TYPE_LABEL[t.doc_type] || t.doc_type)})</span>
          ${scopeBadge}
        </div>
        <div style="margin-bottom:6px;">
          ${tagsHtml || `<span class="muted">（無分類）</span>`}
        </div>
        <pre>${escapeHtml(previewText)}${(t.content_text || "").length > 800 ? "\n...(略)" : ""}</pre>
      `;
      dom.examplePreview.appendChild(item);
    });
  }

  function getFilteredTemplatesForExport() {
    const docType = dom.docType ? dom.docType.value : "";
    const tag = dom.tagFilter ? dom.tagFilter.value : "";

    const listByType = templatesCache.filter((t) => t.doc_type === docType);
    const list = tag ? listByType.filter((t) => (t.tags || []).includes(tag)) : listByType;
    return list;
  }

  function downloadBlob(filename, content, mime) {
    const blob = new Blob([content], { type: mime || "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function exportTemplatesAsJSON() {
    const list = getFilteredTemplatesForExport();
    if (!list.length) return alert("目前沒有可匯出的範例");

    const out = list.map((t) => ({
      title: t.title,
      doc_type: t.doc_type,
      tags: t.tags || [],
      description: t.description || "",
      content_text: t.content_text || "",
      scope: t.scope || "public",
      schema_ver: t.schema_ver || 2,
      sections: t.sections || {},
      doc_fields: t.doc_fields || {},
      meta: t.meta || {},
    }));

    const docType = dom.docType ? dom.docType.value : "templates";
    const filename = `templates_${docType}_${new Date().toISOString().slice(0, 10)}.json`;
    downloadBlob(filename, JSON.stringify(out, null, 2), "application/json;charset=utf-8");
  }

  function csvEscape(v) {
    const s = String(v == null ? "" : v);
    const escaped = s.replace(/"/g, '""');
    return `"${escaped}"`;
  }

  function exportTemplatesAsCSV() {
    const list = getFilteredTemplatesForExport();
    if (!list.length) return alert("目前沒有可匯出的範例");

    const header = ["title", "content_text", "description", "tags", "scope"].map(csvEscape).join(",");
    const rows = list.map((t) => {
      const tags = (t.tags || []).join(";");
      return [
        csvEscape(t.title),
        csvEscape(t.content_text || ""),
        csvEscape(t.description || ""),
        csvEscape(tags),
        csvEscape(t.scope || "public"),
      ].join(",");
    });

    const csv = [header, ...rows].join("\r\n");
    const csvWithBom = "\ufeff" + csv;

    const docType = dom.docType ? dom.docType.value : "templates";
    const filename = `templates_${docType}_${new Date().toISOString().slice(0, 10)}.csv`;
    downloadBlob(filename, csvWithBom, "text/csv;charset=utf-8");
  }

  function exportTemplatesAsTXT() {
    const list = getFilteredTemplatesForExport();
    if (!list.length) return alert("目前沒有可匯出的範例");

    const blocks = list.map((t) => {
      const tags = (t.tags || []).join(";");
      const scope = t.scope || "public";
      return [(t.title || "").trim(), `scope: ${scope}`, `tags: ${tags}`.trim(), (t.content_text || "").trim(), "\n---\n"].join("\n");
    });

    const txt = blocks.join("").trim();
    const txtWithBom = "\ufeff" + txt;

    const docType = dom.docType ? dom.docType.value : "templates";
    const filename = `templates_${docType}_${new Date().toISOString().slice(0, 10)}.txt`;
    downloadBlob(filename, txtWithBom, "text/plain;charset=utf-8");
  }

  function parseCSV(text) {
    const s = String(text || "");
    const rows = [];
    let row = [];
    let cur = "";
    let inQuotes = false;

    for (let i = 0; i < s.length; i++) {
      const ch = s[i];
      const next = s[i + 1];

      if (ch === '"') {
        if (inQuotes && next === '"') {
          cur += '"';
          i++;
        } else {
          inQuotes = !inQuotes;
        }
        continue;
      }

      if (!inQuotes && ch === ",") {
        row.push(cur);
        cur = "";
        continue;
      }

      if (!inQuotes && (ch === "\n" || ch === "\r")) {
        if (ch === "\r" && next === "\n") i++;
        row.push(cur);
        rows.push(row);
        row = [];
        cur = "";
        continue;
      }

      cur += ch;
    }

    row.push(cur);
    if (row.length > 1 || row[0].trim() !== "") rows.push(row);

    return rows.map((r) => r.map((c) => String(c == null ? "" : c).trim()));
  }

  async function loadTemplates() {
    const docType = dom.docType ? dom.docType.value : "";
    const tag = dom.tagFilter ? dom.tagFilter.value : "";
    const scope = dom.tplScope ? dom.tplScope.value : "";

    if (dom.tplList) dom.tplList.innerHTML = "⏳ 載入中...";

    try {
      let url = API_TEMPLATES;
      const qs = [];
      if (scope) qs.push("scope=" + encodeURIComponent(scope));
      if (docType) qs.push("doc_type=" + encodeURIComponent(docType));
      if (tag) qs.push("tag=" + encodeURIComponent(tag));
      if (qs.length) url = url + "?" + qs.join("&");

      const res = await fetch(url, { method: "GET" });

      if (res.status === 401) {
        if (dom.tplScope) dom.tplScope.value = "public";
        return await loadTemplates();
      }

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`templates api error: ${res.status} ${t}`);
      }

      const data = await res.json();

      templatesCache = (data.templates || []).map((t) => ({
        ...t,
        content_text: normalizeContentText(t.content_text || ""),
        description: normalizeContentText(t.description || ""),
        tags: mapTagsToGroups(t.tags || []),
        scope: t.scope || "public",
        schema_ver: t.schema_ver || 2,
        sections: t.sections || {},
        doc_fields: t.doc_fields || {},
        meta: t.meta || {},
      }));

      const list = templatesCache;

      if (list.length === 0) {
        const typeLabel = DOC_TYPE_LABEL[docType] || docType;
        if (dom.tplList) {
          dom.tplList.innerHTML = `
            <div class="muted">
              目前沒有符合「${escapeHtml(typeLabel)}」${tag ? ` + 類別「${escapeHtml(tag)}」` : ""} 的範例。
              請先到 /admin/ 新增，或用「匯入範例檔」。
            </div>`;
        }
        renderExamplePreview();
        return;
      }

      if (dom.tplList) dom.tplList.innerHTML = "";
      list.forEach((t) => {
        const div = document.createElement("div");
        div.className = "template-item";

        const tagsHtml = (t.tags || [])
          .map((tag) => `<span class="badge">${escapeHtml(tag)}</span>`)
          .join("");

        const scopeBadge =
          t.scope === "personal"
            ? `<span class="badge" style="background:rgba(107,114,128,0.12);color:#6b7280;">個人</span>`
            : `<span class="badge">公開</span>`;

        div.innerHTML = `
          <input type="checkbox" class="tplCk" value="${t.id}" style="margin-top:3px;">
          <div style="flex:1;">
            <b>${escapeHtml(t.title)}</b>
            <div class="muted">#${t.id}　${escapeHtml(t.description || "")}　${scopeBadge}</div>
            <div style="margin-top:6px;">
              ${tagsHtml || `<span class="muted">（無分類）</span>`}
            </div>
          </div>
        `;

        if (dom.tplList) dom.tplList.appendChild(div);
      });

      if (dom.tplList) {
        dom.tplList.querySelectorAll(".tplCk").forEach((ck) => {
          ck.addEventListener("change", renderExamplePreview);
        });
      }

      renderExamplePreview();
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      if (dom.tplList) dom.tplList.innerHTML = `<div style="color:#c00">❌ 載入失敗：${escapeHtml(msg)}</div>`;
      renderExamplePreview();
    }
  }

  async function parseAttachments() {
    const files = dom.attachInput ? dom.attachInput.files : null;
    if (!files || files.length === 0) {
      alert("請先選擇附件檔案");
      return;
    }

    if (dom.attachStatus) dom.attachStatus.textContent = "⏳ 解析附件重點中...";
    if (dom.attachmentsText) dom.attachmentsText.value = "⏳ 解析附件重點中...";

    try {
      const fd = new FormData();
      for (const f of files) fd.append("attachments", f);

      const extraHint = String(dom.promptOut && dom.promptOut.value ? dom.promptOut.value : "").trim();
      if (extraHint) fd.append("prompt", extraHint);

      const res = await fetch(API_PARSE_FOCUS, { method: "POST", body: fd });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`parse_focus api error: ${res.status} ${t}`);
      }
      const data = await res.json();

      if (dom.attachmentsText) dom.attachmentsText.value = data.summary_text || "";
      if (dom.attachStatus) dom.attachStatus.textContent = `✅ 重點完成（${(data.files || []).length} 檔）`;
    } catch (e) {
      console.error(e);
      const msg = e && e.message ? e.message : String(e);
      if (dom.attachStatus) dom.attachStatus.textContent = "❌ 解析失敗";
      if (dom.attachmentsText) dom.attachmentsText.value = "❌ 解析失敗：" + msg;
    }
  }

  async function generateDoc() {
    const docType = dom.docType ? dom.docType.value : "";
    const requirement = dom.requirement ? dom.requirement.value.trim() : "";
    const exampleIds = getSelectedExampleIds();

    if (!requirement) {
      alert("請先輸入需求描述！");
      return;
    }

    if (dom.promptOut) dom.promptOut.value = "⏳ 產生中...";
    if (dom.docResult) dom.docResult.value = "⏳ 生成公文中...";
    if (dom.genMeta) dom.genMeta.textContent = "";

    try {
      const res = await fetch(API_GENERATE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          doc_type: docType,
          requirement: requirement,
          example_ids: exampleIds,
          reference_text: (dom.referenceText && dom.referenceText.value ? dom.referenceText.value : "").trim(),
          incoming_text: (dom.incomingText && dom.incomingText.value ? dom.incomingText.value : "").trim(),
          attachments_text: (dom.attachmentsText && dom.attachmentsText.value ? dom.attachmentsText.value : "").trim(),
          save_as_template: false,
        }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`generate api error: ${res.status} ${t}`);
      }

      const data = await res.json();
      if (dom.promptOut) dom.promptOut.value = data.prompt || "";
      if (dom.docResult) dom.docResult.value = data.draft_text || "(未取得 draft_text；請確認後端回傳 draft_text 欄位)";

      const provider = data.provider ? `provider=${data.provider}` : "";
      const model = data.model ? `model=${data.model}` : "";
      const rag = data.rag_backend ? `rag=${data.rag_backend}` : "";
      if (dom.genMeta) dom.genMeta.textContent = [provider, model, rag].filter(Boolean).join("，");
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      if (dom.promptOut) dom.promptOut.value = "❌ 產生失敗：" + msg;
      if (dom.docResult) dom.docResult.value = "❌ 生成失敗：" + msg;
    }
  }

  async function copyTextToClipboard(text, fallbackEl) {
    const t = (text || "").trim();
    if (!t) return false;

    try {
      await navigator.clipboard.writeText(t);
      return true;
    } catch (_e) {
      if (fallbackEl) {
        try {
          fallbackEl.focus();
          fallbackEl.select();
          document.execCommand("copy");
          return true;
        } catch (_e2) {
          return false;
        }
      }
      return false;
    }
  }

  async function copyPrompt() {
    const ok = await copyTextToClipboard(dom.promptOut ? dom.promptOut.value : "", dom.promptOut);
    alert(ok ? "✅ 已複製 Prompt 到剪貼簿" : "❌ 複製失敗");
  }

  async function copyDraft() {
    const ok = await copyTextToClipboard(dom.docResult ? dom.docResult.value : "", dom.docResult);
    alert(ok ? "✅ 已複製草稿到剪貼簿" : "❌ 複製失敗");
  }

  function downloadTxt(filenamePrefix, content) {
    const text = (content || "").trim();
    if (!text) return alert("沒有內容可下載");

    const withBom = "\ufeff" + text;
    const blob = new Blob([withBom], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadTxtSafe(prefix, text) {
    downloadTxt(prefix, text);
  }

  function clearAll() {
    if (!confirm("確定要清除輸入與輸出？")) return;

    if (dom.requirement) dom.requirement.value = "";
    if (dom.incomingText) dom.incomingText.value = "";
    if (dom.attachmentsText) dom.attachmentsText.value = "";
    if (dom.referenceText) dom.referenceText.value = "";
    if (dom.promptOut) dom.promptOut.value = "";
    if (dom.docResult) dom.docResult.value = "";
    if (dom.genMeta) dom.genMeta.textContent = "";

    document.querySelectorAll(".tplCk").forEach((ck) => (ck.checked = false));
    renderExamplePreview();
    autoGrow(dom.requirement);
  }

  function clearPromptOnly() {
    if (dom.promptOut) dom.promptOut.value = "";
  }
  function clearDraftOnly() {
    if (dom.docResult) dom.docResult.value = "";
    if (dom.genMeta) dom.genMeta.textContent = "";
  }

  function importTemplateFile() {
    if (dom.importTplFileInput) dom.importTplFileInput.click();
  }

  function parseTagsFromLine(line) {
    const s = String(line || "").trim();
    if (!s.toLowerCase().startsWith("tags:")) return [];
    const raw = s.slice(5).trim();
    if (!raw) return [];
    return raw.split(";").map((x) => x.trim()).filter(Boolean);
  }

  async function handleTemplateFileUpload(e) {
    const file = e && e.target ? e.target.files[0] : null;
    if (!file) return;

    const ext = file.name.split(".").pop().toLowerCase();
    const docType = dom.docType ? dom.docType.value : "";

    const reader = new FileReader();
    reader.onload = async function (ev) {
      const raw = (ev && ev.target ? ev.target.result : "") || "";

      try {
        if (ext === "txt") {
          const lines = String(raw).split(/\r?\n/);
          const title = (lines[0] || "").trim() || file.name.replace(/\.[^.]+$/, "");
          let tagLine = "";
          for (let i = 0; i < Math.min(lines.length, 10); i++) {
            if (String(lines[i] || "").trim().toLowerCase().startsWith("tags:")) {
              tagLine = lines[i];
              break;
            }
          }
          const maybeTags = mapTagsToGroups(parseTagsFromLine(tagLine));
          const content_text = normalizeContentText(String(raw).trim());

          await postTemplate({
            title: title,
            doc_type: docType,
            description: `匯入：${file.name}`,
            tags: maybeTags,
            content_text: content_text,
            scope: "personal",
            on_conflict: "suffix",
          });
        } else if (ext === "csv") {
          const rows = parseCSV(raw);
          if (!rows.length) throw new Error("CSV 無內容");

          const header = rows[0].map((x) => x.toLowerCase());
          const hasHeader = header.includes("title") && (header.includes("content_text") || header.includes("content"));

          const idx = (name, def) => {
            const i = header.indexOf(name);
            return i >= 0 ? i : def;
          };

          const startIndex = hasHeader ? 1 : 0;

          for (let i = startIndex; i < rows.length; i++) {
            const r = rows[i] || [];
            const title = (r[idx("title", 0)] || "").trim() || `匯入範例_${i}`;

            const content_text = normalizeContentText(((r[idx("content_text", -1)] || r[idx("content", 1)] || "") + "").trim());

            const description = normalizeContentText((r[idx("description", 2)] || `匯入：${file.name}`).trim());
            const tagRaw = (r[idx("tags", 3)] || "").trim();
            const scopeRaw = (r[idx("scope", 4)] || "").trim().toLowerCase();

            const tags = mapTagsToGroups(tagRaw ? tagRaw.split(";").map((x) => x.trim()).filter(Boolean) : []);
            const scope = scopeRaw === "public" || scopeRaw === "personal" ? scopeRaw : "personal";

            if (!content_text) continue;

            await postTemplate({
              title: title,
              doc_type: docType,
              description: description,
              tags: tags,
              content_text: content_text,
              scope: scope,
              on_conflict: "suffix",
            });
          }
        } else {
          alert("不支援的檔案類型，請使用 .txt 或 .csv");
          return;
        }

        alert("✅ 匯入完成，將重新載入範例庫");
        if (dom.importTplFileInput) dom.importTplFileInput.value = "";
        await loadTemplates();
      } catch (err) {
        console.error(err);
        const msg = err && err.message ? err.message : String(err);
        alert("❌ 匯入失敗：" + msg);
      }
    };

    reader.onerror = () => alert("讀取檔案失敗");
    reader.readAsText(file, "utf-8");
  }

  async function postTemplate(payload) {
    const res = await fetch(API_TEMPLATES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.status === 401) {
      throw new Error("未登入或權限不足（401）。若要存入個人範例庫請先登入；若要存公開範例庫需具備權限。");
    }

    if (!res.ok) {
      const t = await res.text();
      throw new Error(`POST templates failed: ${res.status} ${t}`);
    }
    return res.json();
  }

  function autoGrow(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  // ====== modal / 存範例 functions ======
  function firstSubjectFromText(text) {
    const lines = String(text || "").split(/\r?\n/);
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      const m = t.match(/^主旨[:：]\s*(.+)$/);
      if (m) return m[1].trim();
    }
    return "";
  }

  function _inferTagsFromTextFront(text) {
    const t = String(text || "");
    const rules = [
      ["資訊", /系統|資安|弱點|帳號|權限|伺服器|備份|機房|端點|EDR|SOC|告警|監測|MES|IIoT/i],
      ["採購", /採購|招標|詢價|契約|廠商|決標|開標|比價|規格|驗收|開口|框架/i],
      ["主財", /預算|經費|核銷|報支|憑證|請款|撥款|付款|概算|決算/i],
      ["品保", /品質|檢驗|首件|不良|異常|RCA|稽核|改善|報廢/i],
      ["生產", /產線|稼動|排程|產能|備料|出貨|停線|試量產/i],
      ["設施供應", /修繕|空調|電力|消防|水電|工程|設備保養|維護|治具/i],
      ["人事", /人力|招募|派遣|約用|教育訓練|考績/i],
      ["行政", /會議|公告|制度|流程|總務|庶務|文書/i],
      ["研發", /研發|設計|驗證|試驗|專利|新產品/i],
      ["計劃", /計畫|專案|里程碑|年度計畫/i],
      ["職安衛", /職安|工安|環安|安全衛生|危害|風險/i],
      ["測情", /情資|研判|通報|預警|態勢|威脅|SOC|告警|監測|事件/i],
    ];
    const out = [];
    for (const [tag, re] of rules) if (re.test(t)) out.push(tag);
    return out.length ? out : ["行政"];
  }

  function modalSetVisible(visible) {
    if (!dom.saveTplModalOverlay) return;
    dom.saveTplModalOverlay.style.display = visible ? "flex" : "none";
    dom.saveTplModalOverlay.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function buildTagPills(defaultSelected = []) {
    if (!dom.saveTplTagPills) return;
    dom.saveTplTagPills.innerHTML = "";
    TAG_GROUPS.forEach((tag) => {
      const pill = document.createElement("label");
      pill.className = "tag-pill";

      const ck = document.createElement("input");
      ck.type = "checkbox";
      ck.value = tag;
      ck.checked = defaultSelected.includes(tag);

      const text = document.createElement("span");
      text.textContent = tag;

      pill.appendChild(ck);
      pill.appendChild(text);

      function sync() {
        pill.classList.toggle("active", ck.checked);
      }
      ck.addEventListener("change", sync);
      sync();

      dom.saveTplTagPills.appendChild(pill);
    });
  }

  function getModalSelectedTags() {
    const base = dom.saveTplTagPills
      ? Array.from(dom.saveTplTagPills.querySelectorAll('input[type="checkbox"]:checked'))
          .map((x) => x.value)
          .filter(Boolean)
      : [];

    const customRaw = String(dom.saveTplCustomTags && dom.saveTplCustomTags.value ? dom.saveTplCustomTags.value : "").trim();
    const custom = customRaw ? customRaw.split(";").map((s) => s.trim()).filter(Boolean) : [];

    const out = [];
    const seen = new Set();
    for (const x of [...base, ...custom]) {
      if (!x) continue;
      if (seen.has(x)) continue;
      seen.add(x);
      out.push(x);
    }
    return out;
  }

  function openSaveModalWithContent(source, contentText) {
    const docType = dom.docType ? dom.docType.value : "";
    const content = (contentText || "").trim();

    if (!content) {
      alert(source === "draft" ? "草稿內容是空的，無法存為範例。" : "參考前案內容是空的，請先貼上內容再存為範例。");
      return;
    }

    saveModalSource = source;

    const subj = firstSubjectFromText(content) || (source === "draft" ? "草稿" : "前案參考");
    const suggestedTitle = `${DOC_TYPE_LABEL[docType] || docType}—${subj.replace(/[。．\.]+$/, "")}範例`;

    const inferred = mapTagsToGroups(_inferTagsFromTextFront(content));
    const suggestedDesc = inferred.length
      ? `${inferred.slice(0, 4).join(" / ")} / ${source === "draft" ? "草稿" : "前案參考"}`
      : source === "draft"
      ? "草稿"
      : "前案參考";

    if (dom.saveTplModalSub) dom.saveTplModalSub.textContent = `doc_type：${DOC_TYPE_LABEL[docType] || docType}（存入範例庫）`;
    if (dom.saveTplTitle) dom.saveTplTitle.value = suggestedTitle;
    if (dom.saveTplDesc) dom.saveTplDesc.value = suggestedDesc;

    if (dom.saveTplScope) dom.saveTplScope.value = "personal";
    if (dom.saveTplConflict) dom.saveTplConflict.value = "suffix";

    if (dom.saveTplCustomTags) dom.saveTplCustomTags.value = "";
    if (dom.saveTplContentPreview) dom.saveTplContentPreview.value = normalizeContentText(content);

    buildTagPills(inferred);

    if (dom.saveTplHint) dom.saveTplHint.textContent = "提示：tags 可多選；也可在「自訂 tags」輸入（分號 ; 分隔）。";
    modalSetVisible(true);

    setTimeout(() => {
      if (dom.saveTplTitle) dom.saveTplTitle.focus();
    }, 30);
  }

  function openSaveReferenceModal() {
    openSaveModalWithContent("reference", dom.referenceText ? dom.referenceText.value : "");
  }
  function openSaveDraftModal() {
    openSaveModalWithContent("draft", dom.docResult ? dom.docResult.value : "");
  }
  function closeSaveReferenceModal() {
    modalSetVisible(false);
  }

  async function confirmSaveAsTemplate() {
    const docType = dom.docType ? dom.docType.value : "";
    const content = (dom.saveTplContentPreview && dom.saveTplContentPreview.value ? dom.saveTplContentPreview.value : "").trim();
    if (!content) return alert("內容空白，無法儲存。");

    const title = (dom.saveTplTitle && dom.saveTplTitle.value ? dom.saveTplTitle.value : "").trim();
    if (!title) return alert("請輸入標題（title）。");

    const tags = getModalSelectedTags();
    const description =
      (dom.saveTplDesc && dom.saveTplDesc.value ? dom.saveTplDesc.value : "").trim() ||
      (tags.length
        ? `${tags.slice(0, 4).join(" / ")} / ${saveModalSource === "draft" ? "草稿" : "前案參考"}`
        : saveModalSource === "draft"
        ? "草稿"
        : "前案參考");

    const scope = String(dom.saveTplScope && dom.saveTplScope.value ? dom.saveTplScope.value : "personal").trim();
    const on_conflict = String(dom.saveTplConflict && dom.saveTplConflict.value ? dom.saveTplConflict.value : "suffix").trim();

    try {
      if (dom.btnConfirmSaveTpl) {
        dom.btnConfirmSaveTpl.disabled = true;
        dom.btnConfirmSaveTpl.textContent = "儲存中...";
      }

      await postTemplate({
        title,
        doc_type: docType,
        tags,
        description,
        content_text: normalizeContentText(content),
        scope,
        on_conflict,
      });

      closeSaveReferenceModal();
      alert("✅ 已存入範例庫");
      await loadTemplates();
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      alert("❌ 儲存失敗：" + msg);
    } finally {
      if (dom.btnConfirmSaveTpl) {
        dom.btnConfirmSaveTpl.disabled = false;
        dom.btnConfirmSaveTpl.textContent = "儲存為範例";
      }
    }
  }

  // ============================================================
  // ✅ 初始化
  // ============================================================
  window.addEventListener("DOMContentLoaded", () => {
    buildTagOptions();

    if (dom.btnReloadTemplates) dom.btnReloadTemplates.addEventListener("click", loadTemplates);
    if (dom.btnGenerate) dom.btnGenerate.addEventListener("click", generateDoc);

    if (dom.docType) dom.docType.addEventListener("change", loadTemplates);
    if (dom.tplScope) dom.tplScope.addEventListener("change", loadTemplates);
    if (dom.tagFilter) dom.tagFilter.addEventListener("change", loadTemplates);

    if (dom.btnCopyPrompt) dom.btnCopyPrompt.addEventListener("click", copyPrompt);
    if (dom.btnCopyDraft) dom.btnCopyDraft.addEventListener("click", copyDraft);

    if (dom.btnClearAll) dom.btnClearAll.addEventListener("click", clearAll);
    if (dom.btnClearPrompt) dom.btnClearPrompt.addEventListener("click", clearPromptOnly);
    if (dom.btnClearDraft) dom.btnClearDraft.addEventListener("click", clearDraftOnly);

    if (dom.btnDownloadPromptTxt) dom.btnDownloadPromptTxt.addEventListener("click", () => downloadTxtSafe("公文Prompt", dom.promptOut ? dom.promptOut.value : ""));
    if (dom.btnDownloadDraftTxt) dom.btnDownloadDraftTxt.addEventListener("click", () => downloadTxtSafe("公文草稿", dom.docResult ? dom.docResult.value : ""));

    if (dom.btnImportTplFile) dom.btnImportTplFile.addEventListener("click", importTemplateFile);
    if (dom.importTplFileInput) dom.importTplFileInput.addEventListener("change", handleTemplateFileUpload);

    if (dom.btnParseAttach) dom.btnParseAttach.addEventListener("click", parseAttachments);

    if (dom.btnExportTplJson) dom.btnExportTplJson.addEventListener("click", exportTemplatesAsJSON);
    if (dom.btnExportTplCsv) dom.btnExportTplCsv.addEventListener("click", exportTemplatesAsCSV);
    if (dom.btnExportTplTxt) dom.btnExportTplTxt.addEventListener("click", exportTemplatesAsTXT);

    autoGrow(dom.requirement);
    if (dom.requirement) dom.requirement.addEventListener("input", () => autoGrow(dom.requirement));

    if (dom.btnSaveReferenceAsTemplate) dom.btnSaveReferenceAsTemplate.addEventListener("click", openSaveReferenceModal);
    if (dom.btnSaveDraftAsTemplate) dom.btnSaveDraftAsTemplate.addEventListener("click", openSaveDraftModal);

    if (dom.btnCloseSaveTplModal) dom.btnCloseSaveTplModal.addEventListener("click", closeSaveReferenceModal);
    if (dom.btnCancelSaveTpl) dom.btnCancelSaveTpl.addEventListener("click", closeSaveReferenceModal);
    if (dom.btnConfirmSaveTpl) dom.btnConfirmSaveTpl.addEventListener("click", confirmSaveAsTemplate);

    if (dom.saveTplModalOverlay) {
      dom.saveTplModalOverlay.addEventListener("click", (e) => {
        if (e.target === dom.saveTplModalOverlay) closeSaveReferenceModal();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dom.saveTplModalOverlay && dom.saveTplModalOverlay.style.display === "flex") {
        closeSaveReferenceModal();
      }
    });

    // ✅ 方案A：Sybase 初始化
    try {
      if (window.initIncomingSybase) {
        window.initIncomingSybase({
          dom,
          api: {
            lookupUrl: API_INCOMING_LOOKUP,
            fileUrlPrefix: API_INCOMING_FILE,
          },
        });
      }
    } catch (e) {
      console.error("initIncomingSybase failed:", e);
    }

    loadTemplates();
  });
})();

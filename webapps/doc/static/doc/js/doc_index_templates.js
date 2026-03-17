// webapps/doc/static/doc/js/doc_index_templates.js
// ============================================================
// 【專案規範註解】（Mandatory）
// 1) URL 組合：全專案唯一入口 apiurl_factory() → 只讀 document.body.dataset.baseUrl
// 2) JS 禁止寫死任何 proxy/node 前綴（例如 /djangoai）
// 3) 本檔不得自行綁 DOMContentLoaded（避免重複初始化）
// 4) 所有 API URL 必須經過 apiurl_factory() 組合（由 bootstrap 注入 NS.api）
// 5) 本檔所有 API 只能讀 NS.api.*（避免互相干擾、避免 prefix 重複）
// ============================================================

(function () {
  "use strict";

  const NS = (window.DocDocApp = window.DocDocApp || {});
  NS.modules = NS.modules || {};

  const state = {
    __INITED__: false,
    templatesCache: [],
  };

  function _ctx() {
    if (!NS || !NS.api || !NS.dom || !NS.utils || !NS.consts) throw new Error("DocDocApp context not ready.");
    return NS;
  }

  function buildTagOptions() {
    const { dom, consts } = _ctx();
    const select = dom.tagFilter;
    if (!select) return;

    select.innerHTML = `<option value="">全部</option>`;
    consts.TAG_GROUPS.forEach((tag) => {
      const opt = document.createElement("option");
      opt.value = tag;
      opt.textContent = tag;
      select.appendChild(opt);
    });

    if (dom.sybImportTag) {
      dom.sybImportTag.innerHTML = `<option value="">(未指定)</option>`;
      consts.TAG_GROUPS.forEach((tag) => {
        const opt = document.createElement("option");
        opt.value = tag;
        opt.textContent = tag;
        dom.sybImportTag.appendChild(opt);
      });
    }

    // 預設先選資訊（若存在）
    dom.tagFilter.value = consts.TAG_GROUPS.indexOf("資訊") >= 0 ? "資訊" : "";
  }

  function normalizeSybImportLabels() {
    const { dom } = _ctx();
    if (dom.sybImportScope) {
      const label = dom.sybImportScope.closest(".field-block")?.querySelector("label");
      if (label) label.textContent = "範例庫範圍";
      dom.sybImportScope.querySelectorAll("option").forEach((opt) => {
        if (opt.value === "public") opt.textContent = "公開範例";
        if (opt.value === "personal") opt.textContent = "個人範例";
      });
    }
    if (dom.sybImportTag) {
      const label = dom.sybImportTag.closest(".field-block")?.querySelector("label");
      if (label) label.textContent = "標籤";
      dom.sybImportTag.querySelectorAll("option").forEach((opt) => {
        if (opt.value === "") opt.textContent = "(未指定)";
      });
    }
  }

  function normalizeSybImportPreviewTitle() {
    const { dom } = _ctx();
    if (!dom.sybImportPreview) return;
    const card = dom.sybImportPreview.closest(".card");
    const h3 = card && card.previousElementSibling;
    if (h3 && h3.tagName === "H3") h3.textContent = "轉入範例預覽";
  }

  function getSelectedExampleIds() {
    return Array.from(document.querySelectorAll(".tplCk:checked"))
      .map((x) => parseInt(x.value, 10))
      .filter((n) => !isNaN(n));
  }

  function updateExampleHint() {
    const { dom } = _ctx();
    if (!dom.exampleHint) return;

    const n = getSelectedExampleIds().length;
    const base = `已選擇 ${n} 筆範例（建議 1 筆即可）`;

    if (n === 0) {
      dom.exampleHint.textContent = base + "，未選擇範例，系統會使用預設範例。";
      dom.exampleHint.style.color = "#6b7280";
    } else if (n <= 3) {
      dom.exampleHint.textContent = base + "，範例數量合理。";
      dom.exampleHint.style.color = "#2563eb";
    } else {
      dom.exampleHint.textContent = base + "，範例過多，可能降低品質，建議保留 1 筆。";
      dom.exampleHint.style.color = "#ef4444";
    }
  }

  function renderExamplePreview() {
    const { dom, utils, consts } = _ctx();
    if (!dom.examplePreview) return;

    const ids = getSelectedExampleIds();
    updateExampleHint();

    if (!ids.length) {
      dom.examplePreview.innerHTML = `<div class="muted">尚未選取範例</div>`;
      return;
    }

    const selected = state.templatesCache.filter((t) => ids.includes(t.id));
    dom.examplePreview.innerHTML = "";

    selected.forEach((t) => {
      const item = document.createElement("div");
      item.className = "preview-item";

      const tagsHtml = (t.tags || []).map((tag) => `<span class="badge">${utils.escapeHtml(tag)}</span>`).join("");
      const scopeBadge =
        t.scope === "personal"
          ? `<span class="badge" style="background:rgba(107,114,128,0.12);color:#6b7280;">個人</span>`
          : `<span class="badge">公開</span>`;

      const previewText = (t.content_text || "").slice(0, 800);

      item.innerHTML = `
        <div style="font-weight:600; margin-bottom:6px;">
          ${utils.escapeHtml(t.title)}
          <span class="muted">(#${t.id} / ${utils.escapeHtml(consts.DOC_TYPE_LABEL[t.doc_type] || t.doc_type)})</span>
          ${scopeBadge}
        </div>
        <div style="margin-bottom:6px;">
          ${tagsHtml || `<span class="muted">（無標籤）</span>`}
        </div>
        <pre>${utils.escapeHtml(previewText)}${(t.content_text || "").length > 800 ? "\n...(略)" : ""}</pre>
      `;
      dom.examplePreview.appendChild(item);
    });
  }

  function getFilteredTemplatesForExport() {
    const { dom } = _ctx();
    const docType = dom.docType ? dom.docType.value : "";
    const tag = dom.tagFilter ? dom.tagFilter.value : "";
    const listByType = state.templatesCache.filter((t) => t.doc_type === docType);
    return tag ? listByType.filter((t) => (t.tags || []).includes(tag)) : listByType;
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
    const { dom } = _ctx();
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
    const { dom } = _ctx();
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
    const csvWithBom = "﻿" + csv;

    const docType = dom.docType ? dom.docType.value : "templates";
    const filename = `templates_${docType}_${new Date().toISOString().slice(0, 10)}.csv`;
    downloadBlob(filename, csvWithBom, "text/csv;charset=utf-8");
  }

  function exportTemplatesAsTXT() {
    const { dom } = _ctx();
    const list = getFilteredTemplatesForExport();
    if (!list.length) return alert("目前沒有可匯出的範例");

    const blocks = list.map((t) => {
      const tags = (t.tags || []).join(";");
      const scope = t.scope || "public";
      return [(t.title || "").trim(), `scope: ${scope}`, `tags: ${tags}`.trim(), (t.content_text || "").trim(), "\n---\n"].join("\n");
    });

    const txt = blocks.join("").trim();
    const txtWithBom = "﻿" + txt;

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

  async function postTemplate(payload) {
    const { api } = _ctx();
    const res = await fetch(api.templates, {
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

  // =========================================================
  // Sybase：先查詢可轉入清單，再讓使用者勾選案件
  // =========================================================
  const sybState = { docs: [] };

  function _findSybDocByKey(key) {
    return sybState.docs.find((d) => String(d && d.key || "").trim() === String(key || "").trim());
  }

  function _escapeRegExp(s) {
    return String(s || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function _extractByTags(raw, allowTags) {
    const src = String(raw || "");
    if (!src) return "";
    const re = new RegExp(`<(${allowTags.join("|")})>[\\s\\S]*?(?=<[^>]+>|$)`, "g");
    const parts = src.match(re) || [];
    const joined = parts.join("\n");
    const cleaned = joined
      .replace(/<[^>]+>/g, (m) => {
        const tag = m.slice(1, -1);
        return allowTags.includes(tag) ? m : "";
      })
      .split("\n")
      .map((line) => line.trimEnd())
      .filter((line) => line.trim() !== "")
      .join("\n")
      .trim();
    return cleaned;
  }

  function _extractByLabels(raw, allowLabels) {
    const src = String(raw || "");
    if (!src) return "";
    const lines = src.split(/\r?\n/);
    const blocks = {};
    let cur = "";
    let buf = [];

    function flush() {
      if (!cur) return;
      const text = buf.join("\n").trim();
      if (text) blocks[cur] = (blocks[cur] ? blocks[cur] + "\n" : "") + text;
      buf = [];
    }

    for (let i = 0; i < lines.length; i++) {
      const t = String(lines[i] || "").trim();
      let matched = false;
      for (let j = 0; j < allowLabels.length; j++) {
        const label = allowLabels[j];
        const re = new RegExp("^" + _escapeRegExp(label) + "\\s*[:：]?\\s*(.*)$");
        const m = t.match(re);
        if (m) {
          flush();
          cur = label;
          if (m[1]) buf.push(m[1]);
          matched = true;
          break;
        }
      }
      if (!matched && cur) {
        if (t) buf.push(t);
      }
    }
    flush();

    const out = [];
    allowLabels.forEach((label) => {
      const v = (blocks[label] || "").trim();
      if (v) out.push("<" + label + ">" + v);
    });
    return out.join("\n").trim();
  }


  function renderSybImportPreview() {
    const { dom, utils } = _ctx();
    if (!dom.sybImportPreview) return;

    const keys = getSelectedSybDocKeys();
    if (!keys.length) {
      dom.sybImportPreview.innerHTML = `<div class="muted">尚未選取轉入案件</div>`;
      return;
    }

    const blocks = keys.map((k) => {
      const d = _findSybDocByKey(k) || {};
      const ck = document.querySelector(`.sybImportDocCk[value="${String(k).replace(/"/g, '\\"')}"]`);
      const fmt = ck ? String(ck.getAttribute("data-format") || "").trim() : "";
      const title = utils.escapeHtml(d.title || d.subject || d.name || d.format || d.key || "");
      const allowTags = fmt === "簽呈" ? ["主旨", "說明", "擬辦"] : ["主旨", "說明"];
      const raw = String(d.content_text || "");
      let cleaned = _extractByTags(raw, allowTags);
      if (!cleaned) cleaned = _extractByLabels(raw, allowTags);
      if (!cleaned && raw.trim()) cleaned = raw.trim();
      const content = utils.escapeHtml(cleaned || "");
      return `
        <div class="preview-item">
          <div style="font-weight:600; margin-bottom:6px;">${title}</div>
          <textarea class="syb-preview-content" data-key="${utils.escapeHtml(d.key || "")}" rows="10">${content}</textarea>
        </div>
      `;
    });

    dom.sybImportPreview.innerHTML = blocks.join("");
  }

  function renderSybPreview(docs) {
    const { dom, utils } = _ctx();
    if (!dom.sybImportList || !dom.sybImportSummary) return;

    sybState.docs = Array.isArray(docs) ? docs : [];
    dom.sybImportList.innerHTML = "";

    if (!sybState.docs.length) {
      dom.sybImportSummary.textContent = "查無可轉入案件";
      dom.sybImportList.innerHTML = '<div class="muted">查無可轉入案件</div>';
      return;
    }

    const seen = new Set();
    const uniqDocs = [];
    sybState.docs.forEach((d) => {
      const title = (d && (d.title || d.subject || d.name) ? String(d.title || d.subject || d.name) : "").trim();
      const fmt = (d && d.format ? String(d.format) : "").trim();
      const key = `${title}::${fmt}`;
      if (seen.has(key)) return;
      seen.add(key);
      uniqDocs.push(d);
    });

    dom.sybImportSummary.textContent = `共 ${uniqDocs.length} 筆可轉入案件，請勾選要轉入者。`;

    uniqDocs.forEach((d, idx) => {
      const row = document.createElement("label");
      row.className = "syb-import-item";

      const ck = document.createElement("input");
      ck.type = "checkbox";
      ck.className = "sybImportDocCk";
      ck.value = d.key || "";
      ck.setAttribute("data-format", d.format || "");
      ck.checked = idx === 0;

      const title = utils.escapeHtml(d.title || d.subject || d.name || d.format || d.key || "");
      const meta = utils.escapeHtml(d.format || "");
      const content = utils.escapeHtml((d.content_text || "").trim());

      row.innerHTML = `
        <span class="ck-wrap"></span>
        <span class="syb-import-text">
          <span class="syb-import-title">${title}</span>
          <span class="syb-import-meta">${meta ? `（${meta}）` : ""}</span>
        </span>
      `;
      row.querySelector(".ck-wrap").appendChild(ck);

      dom.sybImportList.appendChild(row);
    });

    dom.sybImportList.querySelectorAll(".sybImportDocCk").forEach((ck) => {
      ck.addEventListener("change", renderSybImportPreview);
    });
    renderSybImportPreview();
  }

  function getSelectedSybDocKeys() {
    return Array.from(document.querySelectorAll(".sybImportDocCk:checked"))
      .map((x) => String(x.value || "").trim())
      .filter(Boolean);
  }

  async function previewSybaseDocs() {
    const { dom, api, utils } = _ctx();

    if (!api.syb_template_import) {
      alert("缺少 NS.api.syb_template_import（請確認 doc_index_bootstrap.js 已補上）。");
      return;
    }

    const grsno = String(dom.sybImportGrsno && dom.sybImportGrsno.value ? dom.sybImportGrsno.value : "").trim();
    if (!grsno) return alert("請先輸入公文相關號（TM.TM_GRSNO）");
    if (!/^\d+$/.test(grsno)) return alert("公文相關號格式錯誤：請輸入純數字");

    if (dom.sybImportSummary) dom.sybImportSummary.textContent = "查詢中...";
    if (dom.sybImportList) dom.sybImportList.innerHTML = "";

    try {
      const payload = {
        grsno: grsno,
        tm_grsno: grsno,
        action: "preview",
      };

      const res = await fetch(api.syb_template_import, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.status === 401) {
        throw new Error("未登入或權限不足（401）。查詢個人案件需登入。");
      }

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`sybase preview api error: ${res.status} ${t}`);
      }

      const data = await res.json();
      renderSybPreview((data && data.docs) || []);
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      if (dom.sybImportSummary) dom.sybImportSummary.textContent = "查詢失敗。";
      if (dom.sybImportList) {
        dom.sybImportList.innerHTML = `<div class="muted">查詢失敗：${utils.escapeHtml(msg)}</div>`;
      }
    }
  }

  async function importSelectedSybaseDocs() {
    const { dom, api, utils } = _ctx();

    if (!api.syb_template_import) {
      alert("缺少 NS.api.syb_template_import（請確認 doc_index_bootstrap.js 已補上）。");
      return;
    }

    const grsno = String(dom.sybImportGrsno && dom.sybImportGrsno.value ? dom.sybImportGrsno.value : "").trim();
    if (!grsno) return alert("請先輸入公文相關號（TM.TM_GRSNO）");
    if (!/^\d+$/.test(grsno)) return alert("公文相關號格式錯誤：請輸入純數字");

    const selectedKeys = getSelectedSybDocKeys();
    const contentOverride = {};
    document.querySelectorAll(".syb-preview-content").forEach((ta) => {
      const key = String(ta.getAttribute("data-key") || "").trim();
      if (!key) return;
      contentOverride[key] = String(ta.value || "");
    });

    if (!selectedKeys.length) return alert("請至少勾選一筆可轉入案件。");

    const docType = dom.docType ? dom.docType.value : "";
    const scope = dom.sybImportScope ? String(dom.sybImportScope.value || "").trim() : "personal";
    const tag = dom.sybImportTag ? String(dom.sybImportTag.value || "").trim() : "";
    if (!tag) return alert("請先選擇標籤（不可為未指定）。");
    const tags = [tag];

    const oldText = dom.btnImportTplSelected ? dom.btnImportTplSelected.textContent : "";
    if (dom.btnImportTplSelected) {
      dom.btnImportTplSelected.disabled = true;
      dom.btnImportTplSelected.textContent = "轉入中...";
    }

    try {
      const payload = {
        grsno: grsno,
        tm_grsno: grsno,
        action: "import",
        doc_keys: selectedKeys,
        doc_type: docType,
        scope: scope,
        tags: tags,
        on_conflict: "suffix",
        content_override: contentOverride,
      };

      const res = await fetch(api.syb_template_import, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (res.status === 401) {
        throw new Error("未登入或權限不足（401）。轉入個人範例庫需登入。");
      }

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`sybase template import api error: ${res.status} ${t}`);
      }

      const data = await res.json();
      const createdN = Number(data && (data.created_count || data.created || data.count || 0)) || 0;
      const msg =
        createdN > 0
          ? `轉入完成：新增 ${createdN} 筆範例（將重新載入範例庫）`
          : "轉入完成（將重新載入範例庫）";
      alert(msg);

      await loadTemplates();
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      alert("轉入失敗：" + utils.escapeHtml(msg));
    } finally {
      if (dom.btnImportTplSelected) {
        dom.btnImportTplSelected.disabled = false;
        dom.btnImportTplSelected.textContent = oldText || "轉入勾選項目";
      }
    }
  }

  function parseTagsFromLine(line) {
    const s = String(line || "").trim();
    if (!s.toLowerCase().startsWith("tags:")) return [];
    const raw = s.slice(5).trim();
    if (!raw) return [];
    return raw
      .split(";")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  async function handleTemplateFileUpload(e) {
    const { dom, utils } = _ctx();
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
          const maybeTags = utils.mapTagsToGroups(parseTagsFromLine(tagLine));
          const content_text = utils.normalizeContentText(String(raw).trim());

          await postTemplate({
            title: title,
            doc_type: docType,
            description: `匯入：${file.name}`,
            tags: maybeTags,
            content_text: content_text,
            scope: "personal",
            on_conflict: "suffix",
        content_override: contentOverride,
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
            const content_text = utils.normalizeContentText(((r[idx("content_text", -1)] || r[idx("content", 1)] || "") + "").trim());
            const description = utils.normalizeContentText((r[idx("description", 2)] || `匯入：${file.name}`).trim());
            const tagRaw = (r[idx("tags", 3)] || "").trim();
            const scopeRaw = (r[idx("scope", 4)] || "").trim().toLowerCase();

            const tags = utils.mapTagsToGroups(tagRaw ? tagRaw.split(";").map((x) => x.trim()).filter(Boolean) : []);
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
        content_override: contentOverride,
            });
          }
        } else {
          alert("不支援的檔案類型，請使用 .txt 或 .csv");
          return;
        }

        alert("匯入完成，將重新載入範例庫");
        if (dom.importTplFileInput) dom.importTplFileInput.value = "";
        await loadTemplates();
      } catch (err) {
        console.error(err);
        const msg = err && err.message ? err.message : String(err);
        alert("匯入失敗：" + msg);
      }
    };

    reader.onerror = () => alert("讀取檔案失敗");
    reader.readAsText(file, "utf-8");
  }

  async function loadTemplates() {
    const { api, dom, utils, consts } = _ctx();

    const docType = dom.docType ? dom.docType.value : "";
    const tag = dom.tagFilter ? dom.tagFilter.value : "";
    const scope = dom.tplScope ? dom.tplScope.value : "";

    if (dom.tplList) dom.tplList.innerHTML = "載入中...";

    try {
      let url = api.templates;
      const qs = [];
      if (scope) qs.push("scope=" + encodeURIComponent(scope));
      if (docType) qs.push("doc_type=" + encodeURIComponent(docType));
      if (tag) qs.push("tag=" + encodeURIComponent(tag));
      if (qs.length) url = url + "?" + qs.join("&");

      const res = await fetch(url, { method: "GET" });

      if (res.status === 401) {
        // 未登入：強制切公開再載一次
        if (dom.tplScope) dom.tplScope.value = "public";
        return await loadTemplates();
      }

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`templates api error: ${res.status} ${t}`);
      }

      const data = await res.json();

      state.templatesCache = (data.templates || []).map((t) => ({
        ...t,
        content_text: utils.normalizeContentText(t.content_text || ""),
        description: utils.normalizeContentText(t.description || ""),
        tags: utils.mapTagsToGroups(t.tags || []),
        scope: t.scope || "public",
        schema_ver: t.schema_ver || 2,
        sections: t.sections || {},
        doc_fields: t.doc_fields || {},
        meta: t.meta || {},
      }));

      const list = state.templatesCache;

      if (list.length === 0) {
        const typeLabel = consts.DOC_TYPE_LABEL[docType] || docType;
        if (dom.tplList) {
          dom.tplList.innerHTML = `
            <div class="muted">
              目前沒有符合「${utils.escapeHtml(typeLabel)}」${tag ? ` + 類別「${utils.escapeHtml(tag)}」` : ""} 的範例。
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

        const tagsHtml = (t.tags || []).map((tag) => `<span class="badge">${utils.escapeHtml(tag)}</span>`).join("");
        const scopeBadge =
          t.scope === "personal"
            ? `<span class="badge" style="background:rgba(107,114,128,0.12);color:#6b7280;">個人</span>`
            : `<span class="badge">公開</span>`;

        div.innerHTML = `
          <input type="checkbox" class="tplCk" value="${t.id}" style="margin-top:3px;">
          <div style="flex:1;">
            <b>${utils.escapeHtml(t.title)}</b>
            <div class="muted">#${t.id} ${utils.escapeHtml(t.description || "")} ${scopeBadge}</div>
            <div style="margin-top:6px;">
              ${tagsHtml || `<span class="muted">（無標籤）</span>`}
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
      if (dom.tplList) dom.tplList.innerHTML = `<div style="color:#c00">載入失敗：${utils.escapeHtml(msg)}</div>`;
      renderExamplePreview();
    }
  }

  function init(appCtx) {
    // 只由 bootstrap 呼叫；本 module 不綁 DOMContentLoaded
    void appCtx;

    if (state.__INITED__) return;
    state.__INITED__ = true;

    buildTagOptions();
    normalizeSybImportLabels();
    normalizeSybImportPreviewTitle();

    const { dom } = _ctx();

    // templates 事件
    if (dom.btnReloadTemplates) dom.btnReloadTemplates.addEventListener("click", loadTemplates);
    if (dom.docType) dom.docType.addEventListener("change", loadTemplates);
    if (dom.tplScope) dom.tplScope.addEventListener("change", loadTemplates);
    if (dom.tagFilter) dom.tagFilter.addEventListener("change", loadTemplates);

    if (dom.btnExportTplJson) dom.btnExportTplJson.addEventListener("click", exportTemplatesAsJSON);
    if (dom.btnExportTplCsv) dom.btnExportTplCsv.addEventListener("click", exportTemplatesAsCSV);
    if (dom.btnExportTplTxt) dom.btnExportTplTxt.addEventListener("click", exportTemplatesAsTXT);

    if (dom.btnImportTplFile) dom.btnImportTplFile.addEventListener("click", () => dom.importTplFileInput && dom.importTplFileInput.click());
    if (dom.importTplFileInput) dom.importTplFileInput.addEventListener("change", handleTemplateFileUpload);

    // Sybase：先查詢清單，再轉入勾選
    if (dom.btnImportTplFromSybase) dom.btnImportTplFromSybase.addEventListener("click", previewSybaseDocs);
    if (dom.btnImportTplSelected) dom.btnImportTplSelected.addEventListener("click", importSelectedSybaseDocs);
    if (dom.sybImportGrsno) {
      dom.sybImportGrsno.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          previewSybaseDocs();
        }
      });
    }
  }

  // 對外提供（bootstrap 會呼叫）
  NS.modules.templates = {
    init,
    loadTemplates,
    getSelectedExampleIds,
    renderExamplePreview,
    // 讓 editor module 可取 templatesCache（不共享可變引用）
    getTemplatesCache: () => state.templatesCache.slice(),
    postTemplate, // editor 存範例會用到
    previewSybaseDocs,
    importSelectedSybaseDocs,
    renderSybImportPreview,
  };
})();




// webapps/doc/static/doc/incoming_sybase.js
(function () {
  "use strict";

  // ============================================================
  // helpers
  // ============================================================
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function _pickedIndex(dom) {
    const v = (dom && dom.incomingPick && dom.incomingPick.value ? dom.incomingPick.value : "").trim();
    if (v === "") return null;
    const idx = parseInt(v, 10);
    return isNaN(idx) ? null : idx;
  }

  function _setStatus(dom, msg) {
    if (dom && dom.incomingLookupStatus) dom.incomingLookupStatus.textContent = msg || "";
  }

  function _uniqueKeys(arr) {
    const out = [];
    const seen = new Set();
    (arr || []).forEach(function (x) {
      const k = String(x || "").trim();
      if (!k) return;
      if (seen.has(k)) return;
      seen.add(k);
      out.push(k);
    });
    return out;
  }

  function _ensureExt(name) {
    const n = String(name || "").trim() || "attachment";
    return /\.[a-z0-9]{1,8}$/i.test(n) ? n : (n + ".bin");
  }

  function _dedupeFilename(existingNameSet, filename) {
    const raw = String(filename || "").trim() || "attachment.bin";
    const m = raw.match(/^(.*?)(\.[a-z0-9]{1,8})$/i);
    const base = m ? m[1] : raw;
    const ext = m ? m[2] : "";
    let candidate = raw;

    if (!existingNameSet.has(candidate)) {
      existingNameSet.add(candidate);
      return candidate;
    }

    for (let i = 2; i < 1000; i++) {
      candidate = base + " (" + i + ")" + ext;
      if (!existingNameSet.has(candidate)) {
        existingNameSet.add(candidate);
        return candidate;
      }
    }

    const fallback = base + " (" + Date.now() + ")" + ext;
    existingNameSet.add(fallback);
    return fallback;
  }

  function _joinUrl(prefix, key) {
    // prefix 可能是 "/doc/incoming_file/" 或 "/doc/incoming_file" 或含 query 的 template prefix
    const p = String(prefix || "");
    const fixed = p.endsWith("/") ? p : (p + "/");
    return fixed + encodeURIComponent(String(key)) + "/";
  }

  function _getCookie(name) {
    // Django 常用 csrftoken
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (let i = 0; i < cookies.length; i++) {
      const c = cookies[i].trim();
      if (!c) continue;
      if (c.startsWith(name + "=")) return decodeURIComponent(c.substring(name.length + 1));
    }
    return "";
  }

  function _csrfHeaders() {
    const token = _getCookie("csrftoken");
    return token ? { "X-CSRFToken": token } : {};
  }

  function _isProbablyJsonResponse(res) {
    const ct = (res && res.headers && res.headers.get("content-type")) ? res.headers.get("content-type") : "";
    return (ct || "").toLowerCase().indexOf("application/json") >= 0;
  }

  // ============================================================
  // UI rendering
  // ============================================================
  function _renderAttachments(dom, item) {
    const box = dom ? dom.incomingAttachBox : null;
    const list = dom ? dom.incomingAttachList : null;
    if (!box || !list) return;

    const atts = item && item.attachments ? item.attachments : [];
    box.style.display = "block";
    list.innerHTML = "";

    if (!atts.length) {
      list.innerHTML = '<div class="muted">（此筆無附件）</div>';
      return;
    }

    atts.forEach((a, i) => {
      const attachKey = a && (a.attach_key != null || a.attachKey != null)
        ? String(a.attach_key != null ? a.attach_key : a.attachKey)
        : "";

      const filename = (a && (a.filename || a.file_name || a.name))
        ? (a.filename || a.file_name || a.name)
        : ("附件_" + (i + 1));

      const metaText = [
        a && a.source ? ("source:" + a.source) : "",
        a && a.td_format ? ("format:" + a.td_format) : ""
      ].filter(Boolean).join(" / ");

      const row = document.createElement("div");
      row.className = "att-item";

      row.innerHTML =
        '<input type="checkbox" class="incomingAttCk" data-attach-key="' + escapeHtml(attachKey) + '" checked>' +
        '<div>' +
          '<div class="att-name">' + escapeHtml(filename) + '</div>' +
          (metaText ? ('<div class="att-meta">' + escapeHtml(metaText) + '</div>') : "") +
        '</div>';

      list.appendChild(row);
    });
  }

  // ============================================================
  // Main init
  // ============================================================
  window.initIncomingSybase = function initIncomingSybase(opts) {
    const dom = opts ? opts.dom : null;
    const api = opts ? opts.api : null;

    if (!dom) throw new Error("initIncomingSybase: dom is required");
    if (!api || !api.lookupUrl || !api.fileUrlPrefix) {
      throw new Error("initIncomingSybase: api.lookupUrl & api.fileUrlPrefix required");
    }

    let incomingLookupCache = [];

    function getPickedIncomingItem() {
      const idx = _pickedIndex(dom);
      if (idx === null) return null;
      return incomingLookupCache[idx] || null;
    }

    async function lookupIncomingFromSybase() {
      const tm_grsno = (dom.qEmGrsno && dom.qEmGrsno.value ? dom.qEmGrsno.value : "").trim();
      if (!tm_grsno) {
        alert("請輸入 TM.TM_GRSNO（公文系統相關號 / 來文案件號）");
        return;
      }

      console.log("[incoming_sybase] lookup start", { tm_grsno: tm_grsno, url: api.lookupUrl });

      _setStatus(dom, "⏳ 查詢中...");
      if (dom.incomingPick) dom.incomingPick.innerHTML = '<option value="">⏳ 查詢中...</option>';

      // reset attachment UI
      if (dom.incomingAttachBox) dom.incomingAttachBox.style.display = "none";
      if (dom.incomingAttachList) dom.incomingAttachList.innerHTML = '<div class="muted">（尚無附件／或尚未載入）</div>';

      try {
        // ✅ 後端 incoming_lookup 是 POST JSON
        const res = await fetch(api.lookupUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: Object.assign(
            { "Content-Type": "application/json" },
            _csrfHeaders()
          ),
          body: JSON.stringify({ tm_grsno: tm_grsno })
        });

        console.log("[incoming_sybase] lookup response", res.status, res.headers.get("content-type"));

        if (!res.ok) {
          const t = await res.text();
          throw new Error("incoming_lookup api error: " + res.status + " " + t);
        }

        let data = null;
        if (_isProbablyJsonResponse(res)) {
          data = await res.json();
        } else {
          // 保險：避免代理回非 json
          const t = await res.text();
          try { data = JSON.parse(t); } catch (e) { throw new Error("incoming_lookup non-json: " + t); }
        }

        if (!data || data.ok !== true) {
          throw new Error((data && (data.error || data.detail)) ? (data.error || data.detail) : "incoming_lookup returned not ok");
        }

        incomingLookupCache = data && data.items ? data.items : [];

        if (!incomingLookupCache.length) {
          if (dom.incomingPick) dom.incomingPick.innerHTML = '<option value="">（查無資料）</option>';
          _setStatus(dom, "⚠️ 查無符合資料（僅限本人承辦案件）");
          return;
        }

        if (dom.incomingPick) dom.incomingPick.innerHTML = '<option value="">（請選擇一筆）</option>';

        incomingLookupCache.forEach(function (it, idx) {
          const opt = document.createElement("option");
          opt.value = String(idx);

          const subj = String(it && it.td_subj ? it.td_subj : "").replace(/\s+/g, " ").slice(0, 60);
          const grsno = (it && (it.tm_grsno || it.tmGrsno || it.em_grsno))
            ? (it.tm_grsno || it.tmGrsno || it.em_grsno)
            : "";
          const psid = (it && (it.tm_psid || it.tmPsid)) ? (it.tm_psid || it.tmPsid) : "";

          opt.textContent = "#" + (idx + 1) + "｜GRSNO:" + grsno + (psid ? ("｜PSID:" + psid) : "") + "｜" + subj;

          dom.incomingPick.appendChild(opt);
        });

        _setStatus(dom, "✅ 查到 " + incomingLookupCache.length + " 筆（本人承辦）");
      } catch (e) {
        console.error(e);
        if (dom.incomingPick) dom.incomingPick.innerHTML = '<option value="">（查詢失敗）</option>';
        _setStatus(dom, "❌ 查詢失敗");
        alert("❌ 查詢失敗：" + (e && e.message ? e.message : String(e)));
      }
    }

    function applyIncomingToText() {
      const it = getPickedIncomingItem();
      if (!it) return alert("請先選擇一筆查詢結果");

      const subj = String(it.td_subj || "").trim();
      if (!subj) return alert("該筆沒有 TD_SUBJ");

      // ✅ 你想「載入主旨到來文內容」：用 主旨：... 置頂
      const prefix = "主旨：" + subj;
      const existing = String(dom.incomingText && dom.incomingText.value ? dom.incomingText.value : "").trim();
      if (dom.incomingText) dom.incomingText.value = existing ? (prefix + "\n\n" + existing) : prefix;
    }

    async function loadSelectedIncomingAttachmentsToFileInput() {
      const it = getPickedIncomingItem();
      if (!it) return alert("請先選擇一筆查詢結果");

      const atts = it.attachments || [];
      if (!atts.length) return alert("該筆沒有附件可載入");

      const listRoot = dom.incomingAttachList || document;
      const checked = Array.from(listRoot.querySelectorAll(".incomingAttCk:checked"));
      if (!checked.length) return alert("請至少勾選 1 個附件");

      const selectedKeys = _uniqueKeys(
        checked.map(function (ck) {
          return (ck.getAttribute("data-attach-key") || "").trim();
        })
      );
      if (!selectedKeys.length) return alert("勾選的附件沒有 attach_key");

      if (!dom.attachInput) return alert("找不到附件上傳欄位（attachInput）");

      console.log("[incoming_sybase] download attachments", selectedKeys);
      _setStatus(dom, "⏳ 下載附件中...");

      const dt = new DataTransfer();

      // 保留使用者手動已選檔案
      const existingFiles = dom.attachInput.files || [];
      const nameSet = new Set();
      for (const f of existingFiles) {
        dt.items.add(f);
        nameSet.add(f.name);
      }

      try {
        let okCount = 0;

        for (const attach_key of selectedKeys) {
          const fileUrl = _joinUrl(api.fileUrlPrefix, attach_key);
          console.log("[incoming_sybase] GET", fileUrl);

          const res = await fetch(fileUrl, {
            method: "GET",
            credentials: "same-origin",
          });

          if (!res.ok) {
            const t = await res.text();
            throw new Error("incoming_file error: " + res.status + " " + t);
          }

          const blob = await res.blob();

          // 從 it.attachments 找回檔名（若找不到就 fallback）
          const meta = atts.find(function (x) {
            const k = x && (x.attach_key != null || x.attachKey != null)
              ? String(x.attach_key != null ? x.attach_key : x.attachKey)
              : "";
            return k === String(attach_key);
          });

          let name = meta && (meta.filename || meta.file_name || meta.name)
            ? (meta.filename || meta.file_name || meta.name)
            : ("attach_" + attach_key);

          name = _ensureExt(name);
          name = _dedupeFilename(nameSet, name);

          const file = new File([blob], name, { type: blob.type || "application/octet-stream" });
          dt.items.add(file);
          okCount++;
        }

        dom.attachInput.files = dt.files;
        _setStatus(dom, "✅ 已載入附件 " + okCount + " 個（可直接按「解析附件重點」）");
      } catch (e) {
        console.error(e);
        _setStatus(dom, "❌ 附件下載失敗");
        alert("❌ 附件下載失敗：" + (e && e.message ? e.message : String(e)));
      }
    }

    function onIncomingPickChanged() {
      const it = getPickedIncomingItem();
      if (!it) {
        if (dom.incomingAttachBox) dom.incomingAttachBox.style.display = "none";
        if (dom.incomingAttachList) dom.incomingAttachList.innerHTML = '<div class="muted">（尚無附件／或尚未載入）</div>';
        return;
      }
      _renderAttachments(dom, it);
    }

    function selectAllIncomingAttachments(checked) {
      const listRoot = dom.incomingAttachList || document;
      const cks = Array.from(listRoot.querySelectorAll(".incomingAttCk"));
      cks.forEach(function (ck) { ck.checked = !!checked; });
    }

    // bind events（保險：先檢查 DOM）
    if (dom.btnLookupIncoming) dom.btnLookupIncoming.addEventListener("click", lookupIncomingFromSybase);
    if (dom.btnApplyIncoming) dom.btnApplyIncoming.addEventListener("click", applyIncomingToText);
    if (dom.btnLoadIncomingAttachments) dom.btnLoadIncomingAttachments.addEventListener("click", loadSelectedIncomingAttachmentsToFileInput);
    if (dom.incomingPick) dom.incomingPick.addEventListener("change", onIncomingPickChanged);

    if (dom.btnIncomingAttachAll) dom.btnIncomingAttachAll.addEventListener("click", function () { selectAllIncomingAttachments(true); });
    if (dom.btnIncomingAttachNone) dom.btnIncomingAttachNone.addEventListener("click", function () { selectAllIncomingAttachments(false); });

    console.log("[incoming_sybase] init ok", { lookupUrl: api.lookupUrl, fileUrlPrefix: api.fileUrlPrefix });
  };

  // ============================================================
  // Auto init (recommended)
  // ============================================================
  function autoInit() {
    const root = document.getElementById("incomingSybase");

    // 若頁面沒有 include 來文區塊，就不動作
    if (!root) return;

    // ✅ HTML 建議提供：
    // data-lookup-url="{% url 'doc:incoming_lookup' %}"
    // data-file-url-prefix="/doc/incoming_file/"
    const lookupUrl = root.dataset.lookupUrl || "";
    const fileUrlPrefix =
      root.dataset.fileUrlPrefix ||
      root.dataset.fileUrl || ""; // 兼容你可能用 data-file-url

    // ✅ fallback（相對路徑）
    const fallbackLookup = "/doc/incoming_lookup/";
    const fallbackFilePrefix = "/doc/incoming_file/";

    const api = {
      lookupUrl: lookupUrl || fallbackLookup,
      fileUrlPrefix: fileUrlPrefix || fallbackFilePrefix,
    };

    const dom = {
      qEmGrsno: document.getElementById("qEmGrsno"),
      qEmSno: document.getElementById("qEmSno"),

      incomingLookupStatus: document.getElementById("incomingLookupStatus"),
      incomingPick: document.getElementById("incomingPick"),

      incomingAttachBox: document.getElementById("incomingAttachBox"),
      incomingAttachList: document.getElementById("incomingAttachList"),

      btnLookupIncoming: document.getElementById("btnLookupIncoming"),
      btnApplyIncoming: document.getElementById("btnApplyIncoming"),
      btnLoadIncomingAttachments: document.getElementById("btnLoadIncomingAttachments"),

      btnIncomingAttachAll: document.getElementById("btnIncomingAttachAll"),
      btnIncomingAttachNone: document.getElementById("btnIncomingAttachNone"),

      // 你主頁的「來文內容」textarea id（沒有也不會爆）
      incomingText: document.getElementById("incomingText"),

      // ✅ 你主頁「附件上傳」input id：
      // 你之前常見是 id="attachments" 或你自己定的 id="attachInput"
      // 這裡雙保險
      attachInput: document.getElementById("attachInput") || document.getElementById("attachments"),
    };

    window.initIncomingSybase({ dom, api });
  }

  document.addEventListener("DOMContentLoaded", autoInit);
})();

(function () {
  "use strict";

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function api(path) {
    if (typeof window.apiurl_factory === "function") {
      return window.apiurl_factory(path);
    }
    var base = String((document.body && document.body.dataset && document.body.dataset.baseUrl) || "").trim();
    var p = String(path || "");
    if (p && p.charAt(0) !== "/") p = "/" + p;
    return base + p;
  }

  function setStatus(el, text, isErr) {
    if (!el) return;
    el.textContent = text || "";
    el.style.color = isErr ? "#b42318" : "#5f6b7a";
  }

  function buildActionHtml(attachKey, plant) {
    var key = String(attachKey || "").trim();
    var p = String(plant || "").trim();
    if (!key) return '<span style="color:#98a2b3;">無 BLOB</span>';
    var plantAttr = p ? ' data-plant="' + escapeHtml(p) + '"' : "";
    return (
      '<div class="actions">' +
      '<button type="button" class="btn-preview" data-key="' + escapeHtml(key) + '"' + plantAttr + '>內容預覽</button>' +
      '<button type="button" class="btn-download secondary" data-key="' + escapeHtml(key) + '"' + plantAttr + '>下載</button>' +
      "</div>"
    );
  }

  function renderRows(tbody, rows, rowBuilder) {
    if (!tbody) return;
    tbody.innerHTML = "";
    if (!rows || !rows.length) {
      tbody.innerHTML = '<tr><td colspan="12" style="color:#64748b;">查無資料</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(rowBuilder).join("");
  }

  function fmt(v) {
    return escapeHtml(String(v == null ? "" : v));
  }

  function bindRowActions(root, previewFn, downloadFn) {
    if (!root) return;
    root.querySelectorAll(".btn-preview").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "").trim();
        var plant = String(btn.getAttribute("data-plant") || "").trim();
        if (key) previewFn(key, plant);
      });
    });
    root.querySelectorAll(".btn-download").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = String(btn.getAttribute("data-key") || "").trim();
        var plant = String(btn.getAttribute("data-plant") || "").trim();
        if (key) downloadFn(key, plant);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var elGrsno = document.getElementById("qGrsno");
    var elSubject = document.getElementById("qSubject");
    var elHandlerName = document.getElementById("qHandlerName");
    var elLimit = document.getElementById("qLimit");
    var elDocCategory = document.getElementById("qDocCategory");
    var elPlant = document.getElementById("qPlant");
    var btnSearch = document.getElementById("btnSearch");
    var btnClear = document.getElementById("btnClear");
    var elStatus = document.getElementById("queryStatus");
    var elDateStart = document.getElementById("qDateStart");
    var elDateEnd = document.getElementById("qDateEnd");
    var elPreviewText = document.getElementById("previewText");

    var tbIncomingDocs = document.getElementById("tbIncomingDocs");
    var tbIncomingAttach = document.getElementById("tbIncomingAttach");
    var tbDraftDocs = document.getElementById("tbDraftDocs");
    var tbDraftAttach = document.getElementById("tbDraftAttach");

    var urlSearch = api("api/sybase/query/search/");
    var urlPreview = api("api/sybase/query/preview/");
    var urlFile = api("api/sybase/query/file/");
    var defaultPlant = String((document.body && document.body.dataset && document.body.dataset.defaultPlant) || "").trim() || "MPC";
    var limitMax = Number.parseInt(String(elLimit && elLimit.max ? elLimit.max : "5000"), 10);
    if (!Number.isFinite(limitMax) || limitMax <= 0) limitMax = 5000;
    var limitMin = Number.parseInt(String(elLimit && elLimit.min ? elLimit.min : "100"), 10);
    if (!Number.isFinite(limitMin) || limitMin <= 0) limitMin = 100;
    var limitDefault = Number.parseInt(String(elLimit && elLimit.value ? elLimit.value : "3000"), 10);
    if (!Number.isFinite(limitDefault) || limitDefault <= 0) limitDefault = 3000;

    function parseDateOnly(value) {
      var s = String(value || "").trim();
      if (!s) return null;
      var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
      if (!m) return null;
      var y = Number.parseInt(m[1], 10);
      var mm = Number.parseInt(m[2], 10);
      var d = Number.parseInt(m[3], 10);
      var dt = new Date(Date.UTC(y, mm - 1, d));
      if (
        dt.getUTCFullYear() !== y ||
        dt.getUTCMonth() !== mm - 1 ||
        dt.getUTCDate() !== d
      ) {
        return null;
      }
      return dt;
    }

    function toIsoDate(dt) {
      if (!dt) return "";
      var y = String(dt.getUTCFullYear());
      var m = String(dt.getUTCMonth() + 1).padStart(2, "0");
      var d = String(dt.getUTCDate()).padStart(2, "0");
      return y + "-" + m + "-" + d;
    }

    function normalizeDateRange() {
      var start = parseDateOnly(elDateStart && elDateStart.value);
      var end = parseDateOnly(elDateEnd && elDateEnd.value);
      if (!start || !end) {
        return { ok: false, startDate: "", endDate: "", days: 0 };
      }
      if (start.getTime() > end.getTime()) {
        var tmp = start;
        start = end;
        end = tmp;
      }
      var startDate = toIsoDate(start);
      var endDate = toIsoDate(end);
      if (elDateStart) elDateStart.value = startDate;
      if (elDateEnd) elDateEnd.value = endDate;
      var diffDays = Math.floor((end.getTime() - start.getTime()) / 86400000) + 1;
      if (!Number.isFinite(diffDays) || diffDays <= 0) diffDays = 1;
      return { ok: true, startDate: startDate, endDate: endDate, days: diffDays };
    }

    function autoAdjustLimit() {
      var range = normalizeDateRange();
      if (!range.ok) return null;
      var next = range.days * 100;
      if (!Number.isFinite(next) || next <= 0) next = limitDefault;
      if (next > limitMax) next = limitMax;
      if (next < limitMin) next = limitMin;
      if (elLimit) elLimit.value = String(next);
      return range;
    }

    function clearTables() {
      [tbIncomingDocs, tbIncomingAttach, tbDraftDocs, tbDraftAttach].forEach(function (tb) {
        if (tb) tb.innerHTML = "";
      });
      if (elPreviewText) elPreviewText.value = "";
    }

    async function previewBlob(attachKey, plant) {
      if (elPreviewText) elPreviewText.value = "讀取預覽中...";
      try {
        var p = String(plant || (elPlant && elPlant.value) || "").trim();
        var qs = "?attach_key=" + encodeURIComponent(attachKey);
        if (p) qs += "&plant=" + encodeURIComponent(p);
        var res = await fetch(urlPreview + qs, { method: "GET" });
        if (!res.ok) {
          throw new Error("HTTP " + res.status);
        }
        var data = await res.json();
        var text = String(data.preview_text || "").trim();
        if (!text) text = "(此 BLOB 非文字內容或無法解析，請改用下載檔案檢視)";
        if (elPreviewText) elPreviewText.value = text;
      } catch (e) {
        if (elPreviewText) elPreviewText.value = "預覽失敗：" + (e && e.message ? e.message : String(e));
      }
    }

    function downloadBlob(attachKey, plant) {
      var p = String(plant || (elPlant && elPlant.value) || "").trim();
      var href = urlFile + "?attach_key=" + encodeURIComponent(attachKey);
      if (p) href += "&plant=" + encodeURIComponent(p);
      window.open(href, "_blank", "noopener");
    }

    async function doSearch() {
      var grsno = String(elGrsno && elGrsno.value ? elGrsno.value : "").trim();
      var subject = String(elSubject && elSubject.value ? elSubject.value : "").trim();
      var handlerName = String(elHandlerName && elHandlerName.value ? elHandlerName.value : "").trim();
      var plant = String(elPlant && elPlant.value ? elPlant.value : defaultPlant).trim();
      var docCategory = String(elDocCategory && elDocCategory.value ? elDocCategory.value : "all").trim();
      var range = autoAdjustLimit();
      if (!range || !range.ok) {
        setStatus(elStatus, "請輸入有效起始日期與結束日期", true);
        return;
      }

      var limit = Number.parseInt(String(elLimit && elLimit.value ? elLimit.value : String(limitDefault)), 10);
      if (!Number.isFinite(limit) || limit <= 0) limit = limitDefault;
      if (limit > limitMax) limit = limitMax;
      if (limit < limitMin) limit = limitMin;

      var startDate = range.startDate;
      var endDate = range.endDate;

      if (!grsno && !subject && !handlerName) {
        setStatus(elStatus, "請至少輸入：承辦人姓名、相關號或主旨子字串。", true);
        return;
      }

      if (btnSearch) btnSearch.disabled = true;
      setStatus(elStatus, "查詢中...", false);
      clearTables();

      try {
        var res = await fetch(urlSearch, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            grsno: grsno,
            subject: subject,
            handler_name: handlerName,
            plant: plant,
            limit: limit,
            start_date: startDate,
            end_date: endDate,
            doc_category: docCategory
          })
        });
        if (!res.ok) {
          var t = await res.text();
          throw new Error("search api error: " + res.status + " " + t);
        }

        var data = await res.json();
        if (!data.ok) {
          throw new Error(data.error || "查詢失敗");
        }

        var incomingDocs = data.incoming_docs || [];
        var incomingAttachments = data.incoming_attachments || [];
        var draftDocs = data.draft_docs || [];
        var draftAttachments = data.draft_attachments || [];
        var counts = data.counts || {};
        var query = data.query || {};
        var resultPlant = String(query.plant || plant || defaultPlant).trim();

        renderRows(tbDraftDocs, draftDocs, function (r) {
          return (
            "<tr>" +
            "<td>" + fmt(r.grsno) + "</td>" +
            "<td>" + fmt(r.date) + "</td>" +
            "<td>" + fmt(r.handler_name || r.sender || r.psid) + "</td>" +
            "<td>" + fmt(r.flow_info) + "</td>" +
            "<td>" + fmt(r.format) + "</td>" +
            "<td>" + fmt(r.subject || r.filename) + "</td>" +
            "<td>" + buildActionHtml(r.attach_key, r.plant || resultPlant) + "</td>" +
            "</tr>"
          );
        });

        renderRows(tbDraftAttach, draftAttachments, function (r) {
          return (
            "<tr>" +
            "<td>" + fmt(r.grsno) + "</td>" +
            "<td>" + fmt(r.date) + "</td>" +
            "<td>" + fmt(r.handler_name || r.sender || r.psid) + "</td>" +
            "<td>" + fmt(r.format) + "</td>" +
            "<td>" + fmt(r.filename || r.subject) + "</td>" +
            "<td>" + buildActionHtml(r.attach_key, r.plant || resultPlant) + "</td>" +
            "</tr>"
          );
        });

        renderRows(tbIncomingDocs, incomingDocs, function (r) {
          return (
            "<tr>" +
            "<td>" + fmt(r.grsno) + "</td>" +
            "<td>" + fmt(r.handler_name || r.psid) + "</td>" +
            "<td>" + fmt(r.subject) + "</td>" +
            "<td>" + fmt(r.attach_count) + "</td>" +
            "</tr>"
          );
        });

        renderRows(tbIncomingAttach, incomingAttachments, function (r) {
          return (
            "<tr>" +
            "<td>" + fmt(r.grsno) + "</td>" +
            "<td>" + fmt(r.subject) + "</td>" +
            "<td>" + fmt(r.filename) + "</td>" +
            "<td>" + fmt(r.page) + "</td>" +
            "<td>" + buildActionHtml(r.attach_key, r.plant || resultPlant) + "</td>" +
            "</tr>"
          );
        });

        bindRowActions(tbDraftDocs, previewBlob, downloadBlob);
        bindRowActions(tbDraftAttach, previewBlob, downloadBlob);
        bindRowActions(tbIncomingAttach, previewBlob, downloadBlob);
        var statusMsg = (
          "查詢完成：簽稿主檔 " + String(counts.draft_docs || 0) + " 筆、" +
          "簽稿附件 " + String(counts.draft_attachments || 0) + " 筆、" +
          "來文主旨 " + String(counts.incoming_docs || 0) + " 筆、" +
          "來文附件 " + String(counts.incoming_attachments || 0) + " 筆" +
          "\n(起訖=" + String(query.start_date || startDate) + " ~ " + String(query.end_date || endDate) +
          "，筆數上限=" + String(query.limit || limit) +
          "，抓取上限=" + String(query.fetch_limit || "") + ")"
        );
        setStatus(elStatus, statusMsg, false);
      } catch (e) {
        setStatus(elStatus, "查詢失敗：" + (e && e.message ? e.message : String(e)), true);
      } finally {
        if (btnSearch) btnSearch.disabled = false;
      }
    }

    if (btnSearch) btnSearch.addEventListener("click", doSearch);
    if (btnClear) {
      btnClear.addEventListener("click", function () {
        if (elGrsno) elGrsno.value = "";
        if (elSubject) elSubject.value = "";
        if (elHandlerName) elHandlerName.value = "";
        if (elDateStart) elDateStart.value = "";
        if (elDateEnd) elDateEnd.value = "";
        if (elDocCategory) elDocCategory.value = "all";
        if (elPlant) elPlant.value = defaultPlant;
        if (elDateEnd) {
          var now = new Date();
          var end = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
          var start = new Date(end.getTime() - 29 * 86400000);
          if (elDateStart) elDateStart.value = toIsoDate(start);
          elDateEnd.value = toIsoDate(end);
        }
        autoAdjustLimit();
        clearTables();
        setStatus(elStatus, "", false);
      });
    }

    if (elDateStart) {
      elDateStart.addEventListener("change", function () {
        autoAdjustLimit();
      });
    }
    if (elDateEnd) {
      elDateEnd.addEventListener("change", function () {
        autoAdjustLimit();
      });
    }
    autoAdjustLimit();
  });
})();

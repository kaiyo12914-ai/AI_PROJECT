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
    var elDaysAgo = document.getElementById("qDaysAgo");
    var elPreviewText = document.getElementById("previewText");

    var tbIncomingDocs = document.getElementById("tbIncomingDocs");
    var tbIncomingAttach = document.getElementById("tbIncomingAttach");
    var tbDraftDocs = document.getElementById("tbDraftDocs");
    var tbDraftAttach = document.getElementById("tbDraftAttach");

    var urlSearch = api("api/sybase/query/search/");
    var urlPreview = api("api/sybase/query/preview/");
    var urlFile = api("api/sybase/query/file/");
    var defaultPlant = String((document.body && document.body.dataset && document.body.dataset.defaultPlant) || "").trim() || "MPC";

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
      var limit = Number.parseInt(String(elLimit && elLimit.value ? elLimit.value : "50"), 10);
      if (!Number.isFinite(limit) || limit <= 0) limit = 50;
      if (limit > 500) limit = 500;

      var daysAgoRaw = String(elDaysAgo && elDaysAgo.value ? elDaysAgo.value : "").trim();
      var daysAgo = daysAgoRaw ? Number.parseInt(daysAgoRaw, 10) : null;
      if (!Number.isFinite(daysAgo) || daysAgo <= 0) daysAgo = null;

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
            days_ago: daysAgo,
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

        setStatus(
          elStatus,
          "查詢完成：簽稿主檔 " + (counts.draft_docs || 0) +
            " 筆、簽稿附件 " + (counts.draft_attachments || 0) +
            " 筆、來文主旨 " + (counts.incoming_docs || 0) +
            " 筆、來文附件 " + (counts.incoming_attachments || 0) + " 筆。",
          false
        );
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
        if (elLimit) elLimit.value = "50";
        if (elDaysAgo) elDaysAgo.value = "30";
        if (elDocCategory) elDocCategory.value = "all";
        if (elPlant) elPlant.value = defaultPlant;
        clearTables();
        setStatus(elStatus, "", false);
      });
    }
  });
})();

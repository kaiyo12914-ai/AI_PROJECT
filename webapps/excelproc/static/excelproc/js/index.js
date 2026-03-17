const apiurlFn = (typeof window.apiurl === "function" && window.apiurl) || ((p) => p);
const API_RUN = (() => {
  const raw = document.body && document.body.dataset ? document.body.dataset.apiRunPath : "";
  return apiurlFn(raw || "run/");
})();
const $ = (id) => document.getElementById(id);

function setBusy(btn, busy){ btn.disabled = !!busy; }

function getCookie(name) {
  const v = document.cookie.split("; ").find(x => x.startsWith(name + "="));
  return v ? decodeURIComponent(v.split("=").slice(1).join("=")) : "";
}

function filenameFromDisposition(disposition){
  if (!disposition) return "report.xlsx";
  const m = disposition.match(/filename\*\=UTF-8''([^;]+)/i);
  if (m && m[1]) return decodeURIComponent(m[1]);
  const m2 = disposition.match(/filename\=\"?([^\";]+)\"?/i);
  if (m2 && m2[1]) return m2[1];
  return "report.xlsx";
}

function triggerDownload(blob, filename){
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "report.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function postJob(action, file, outEl, btnEl){
  outEl.value = "⏳ 執行中...";
  if (btnEl) setBusy(btnEl, true);

  const fd = new FormData();
  fd.append("action", action);
  if (file) fd.append("file", file);

  // 如果你 views.py 用 csrf_exempt，這段可留可不留；留著也沒副作用
  const csrftoken = getCookie("csrftoken");

  try {
    const r = await fetch(API_RUN, {
      method: "POST",
      body: fd,
      credentials: "same-origin",
      headers: csrftoken ? { "X-CSRFToken": csrftoken } : {},
    });

    const ct = (r.headers.get("content-type") || "").toLowerCase();
    const disp = r.headers.get("content-disposition") || "";

    const looksLikeFile =
      disp.toLowerCase().includes("attachment") ||
      ct.includes("application/vnd") ||
      ct.includes("application/octet-stream");

    if (r.ok && looksLikeFile) {
      const blob = await r.blob();
      const fn = filenameFromDisposition(disp);
      triggerDownload(blob, fn);
      outEl.value = "✅ 完成（已下載：" + fn + "）";
      return;
    }

    // 其餘：嘗試 JSON
    let j = null;
    try {
      j = await r.json();
    } catch (e) {
      // ✅ 讀 text，直接看到是 IIS/CSRF/其他 forbidden 頁
      const t = await r.text().catch(() => "");
      const snippet = (t || "").replace(/\s+/g, " ").slice(0, 400);
      outEl.value =
        "❌ 伺服器回應非檔案/非 JSON，狀態碼：" + r.status +
        (snippet ? ("\n\n【回應片段】\n" + snippet) : "");
      return;
    }

    if (!j || !j.ok) {
      outEl.value = "❌ " + ((j && j.error) ? j.error : "執行失敗");
      return;
    }

    outEl.value = "✅ 完成（但未收到檔案）";
  } catch (err) {
    outEl.value = "❌ 連線/解析錯誤：" + err;
  } finally {
    if (btnEl) setBusy(btnEl, false);
  }
}

$("btnCompare").addEventListener("click", () => {
  const f = $("fCompare").files[0];
  if (!f) { $("oCompare").value = "❌ 請先選擇 Excel 檔案"; return; }
  postJob("compare", f, $("oCompare"), $("btnCompare"));
});

$("btnImport").addEventListener("click", () => {
  const f = $("fImport").files[0];
  if (!f) { $("oImport").value = "❌ 請先選擇 Excel 檔案"; return; }
  postJob("import", f, $("oImport"), $("btnImport"));
});

$("btnExport").addEventListener("click", () => {
  postJob("export", null, $("oExport"), $("btnExport"));
});

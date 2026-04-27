(function () {
  "use strict";

  const el = {
    srcText: document.getElementById("srcText"),
    mode: document.getElementById("mode"),
    optFixTypos: document.getElementById("optFixTypos"),
    optConcise: document.getElementById("optConcise"),
    optEnhanceStructure: document.getElementById("optEnhanceStructure"),
    optPoliteTone: document.getElementById("optPoliteTone"),
    optKeepParagraphs: document.getElementById("optKeepParagraphs"),
    btnRun: document.getElementById("btnRun"),
    btnRefill: document.getElementById("btnRefill"),
    btnCopy: document.getElementById("btnCopy"),
    btnExportTxt: document.getElementById("btnExportTxt"),
    btnExportDocx: document.getElementById("btnExportDocx"),
    btnClear: document.getElementById("btnClear"),
    statusText: document.getElementById("statusText"),
    srcPreview: document.getElementById("srcPreview"),
    dstText: document.getElementById("dstText"),
    summaryList: document.getElementById("summaryList"),
    historyBox: document.getElementById("historyBox"),
  };

  function getOptions() {
    return {
      fixTypos: !!el.optFixTypos.checked,
      concise: !!el.optConcise.checked,
      enhanceStructure: !!el.optEnhanceStructure.checked,
      politeTone: !!el.optPoliteTone.checked,
      keepParagraphs: !!el.optKeepParagraphs.checked,
    };
  }

  function setBusy(busy, text) {
    el.btnRun.disabled = busy;
    el.statusText.textContent = text || "";
  }

  function renderSummary(items) {
    el.summaryList.innerHTML = "";
    (items || []).forEach((x) => {
      const li = document.createElement("li");
      li.textContent = x;
      el.summaryList.appendChild(li);
    });
  }

  async function postJson(url, body) {
    const res = await fetch(apiurl(url), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.status === "error") {
      throw new Error(data.message || data.errorCode || "request failed");
    }
    return data;
  }

  async function runFormalize() {
    const text = (el.srcText.value || "").trim();
    if (!text) {
      alert("請先輸入內容");
      return;
    }

    setBusy(true, "轉換中...");
    try {
      const data = await postJson("/formalize/api/document/formalize/", {
        text,
        mode: el.mode.value,
        options: getOptions(),
      });
      el.srcPreview.value = data.originalText || "";
      el.dstText.value = data.formalizedText || "";
      renderSummary(data.summaryOfChanges || []);
      let tag = "";
      if (data.llmFallback) {
        const err = (data.llmError || "").trim();
        const errShort = err.length > 180 ? err.slice(0, 180) + "..." : err;
        const errText = errShort ? `，llmError: ${errShort}` : "";
        tag = `（使用 fallback${errText}）`;
      }
      setBusy(false, `完成 ${data.processingTime || 0} ms ${tag}`);
      await loadHistory();
    } catch (e) {
      setBusy(false, "");
      alert("轉換失敗：" + (e.message || e));
    }
  }

  async function doExport(format) {
    const text = (el.dstText.value || "").trim();
    if (!text) {
      alert("尚無可匯出內容");
      return;
    }
    const res = await fetch(apiurl("/formalize/api/document/formalize/export/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, format }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      alert("匯出失敗：" + (data.message || res.status));
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    const url = URL.createObjectURL(blob);
    a.href = url;
    a.download = format === "docx" ? "formalized.docx" : "formalized.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function loadHistory() {
    const res = await fetch(apiurl("/formalize/api/document/formalize/history/?limit=10"));
    const data = await res.json().catch(() => ({}));
    const items = data.items || [];
    el.historyBox.innerHTML = "";
    if (!items.length) {
      el.historyBox.textContent = "目前沒有紀錄";
      return;
    }
    items.forEach((it) => {
      const div = document.createElement("div");
      div.className = "history-item";
      div.textContent = `${it.createdAt || ""} | ${it.mode} | ${it.inputChars}→${it.outputChars} 字`;
      el.historyBox.appendChild(div);
    });
  }

  el.btnRun.addEventListener("click", runFormalize);
  el.btnCopy.addEventListener("click", async () => {
    const t = el.dstText.value || "";
    if (!t.trim()) return;
    await navigator.clipboard.writeText(t);
    el.statusText.textContent = "已複製";
  });
  el.btnRefill.addEventListener("click", () => {
    if (el.dstText.value.trim()) el.srcText.value = el.dstText.value;
  });
  el.btnClear.addEventListener("click", () => {
    el.srcText.value = "";
    el.srcPreview.value = "";
    el.dstText.value = "";
    el.summaryList.innerHTML = "";
    el.statusText.textContent = "";
  });
  el.btnExportTxt.addEventListener("click", () => doExport("txt"));
  el.btnExportDocx.addEventListener("click", () => doExport("docx"));

  loadHistory().catch(() => {});
})();

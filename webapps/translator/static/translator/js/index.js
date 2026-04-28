function getTranslateApiUrl() {
  const rawPath =
    (document.body && document.body.dataset && document.body.dataset.apiTranslatePath) ||
    "translator/translate/";
  if (typeof window.apiurl === "function") {
    return window.apiurl(rawPath);
  }
  const path = rawPath.startsWith("/") ? rawPath : "/" + rawPath;
  const base = (document.body && document.body.dataset && document.body.dataset.baseUrl) || "";
  return `${base}${path}`;
}

const pdfjsSrc = (document.body && document.body.dataset && document.body.dataset.pdfjsSrc) ? document.body.dataset.pdfjsSrc : "";
const pdfjsWorker = (document.body && document.body.dataset && document.body.dataset.pdfjsWorker) ? document.body.dataset.pdfjsWorker : "";
if (pdfjsSrc) {
  import(pdfjsSrc).then((pdfjsLib) => {
    if (pdfjsWorker) pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;
    window.pdfjsLib = pdfjsLib;
  }).catch((e) => {
    console.error("pdf.js load failed:", e);
  });
}

// ✅ 後端 API：翻譯 endpoint

    const inputTextEl = document.getElementById("inputText");
    const outputTextEl = document.getElementById("outputText");
    const statusEl = document.getElementById("status");

    const sourceLangEl = document.getElementById("sourceLang");
    const targetLangEl = document.getElementById("targetLang");

    const fileInputEl = document.getElementById("fileInput");
    const btnImportEl = document.getElementById("btnImport");
    const btnTranslateEl = document.getElementById("btnTranslate");
    const btnClearEl = document.getElementById("btnClear");
    const btnResetAllEl = document.getElementById("btnResetAll");
    const btnExportTxtEl = document.getElementById("btnExportTxt");
    const btnExportCsvEl = document.getElementById("btnExportCsv");

    function setStatus(msg) {
      statusEl.textContent = msg || "";
    }

    function downloadFile(filename, content, mime) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 800);
    }

    async function readTxtOrCsv(file) {
      const text = await file.text();
      const ext = file.name.split(".").pop().toLowerCase();
      if (ext === "csv") {
        const lines = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
        return lines.join("\n");
      }
      return text;
    }

    async function readDocx(file) {
      if (!window.mammoth) throw new Error("mammoth 尚未載入（請檢查 static 路徑）");
      const arrayBuffer = await file.arrayBuffer();
      const result = await window.mammoth.extractRawText({ arrayBuffer });
      return (result && result.value) ? result.value : "";
    }

    async function readPdf(file) {
      if (!window.pdfjsLib) throw new Error("pdf.js 尚未載入（請檢查 static 路徑與檔名）");

      const arrayBuffer = await file.arrayBuffer();
      const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;

      let fullText = "";
      for (let pageNum = 1; pageNum <= pdf.numPages; pageNum++) {
        const page = await pdf.getPage(pageNum);
        const content = await page.getTextContent();
        const strings = content.items.map(it => it.str).filter(Boolean);
        fullText += strings.join(" ") + "\n\n";
      }
      return fullText.trim();
    }

    btnImportEl.addEventListener("click", () => fileInputEl.click());

    fileInputEl.addEventListener("change", async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      const ext = file.name.split(".").pop().toLowerCase();
      setStatus(`匯入解析中：${file.name}`);

      try {
        let text = "";
        if (ext === "txt" || ext === "csv") text = await readTxtOrCsv(file);
        else if (ext === "docx") text = await readDocx(file);
        else if (ext === "pdf") text = await readPdf(file);
        else { alert("只支援 .txt / .csv / .docx / .pdf"); return; }

        if (!text.trim()) {
          alert("匯入成功，但解析到的內容為空（PDF 可能是掃描影像型）");
        }

        inputTextEl.value = text;
        setStatus(`匯入完成：${file.name}`);
      } catch (err) {
        console.error(err);
        alert("匯入解析失敗：" + err.message);
        setStatus("匯入失敗");
      } finally {
        e.target.value = "";
        setTimeout(() => setStatus(""), 1200);
      }
    });

    async function translateNow() {
      const text = (inputTextEl.value || "").trim();
      if (!text) return alert("請輸入要翻譯的文字或匯入檔案");

      outputTextEl.textContent = "⏳ 翻譯中，請稍候...";
      setStatus("送出翻譯請求中...");

      try {
        const resp = await fetch(getTranslateApiUrl(), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            source_lang: sourceLangEl.value,
            target_lang: targetLangEl.value
          })
        });

        const raw = await resp.text();
        let data = {};
        try { data = JSON.parse(raw); } catch (e) {}

        if (!resp.ok) {
          const msg = data.detail || data.llmError || data.error || raw;
          throw new Error(`伺服器錯誤 ${resp.status}: ${msg}`);
        }

        const translated = (data.translated ?? data.reply ?? "").toString();
        outputTextEl.textContent = translated || "";
        if (data.fallback) {
          const err = (data.llmError || "").trim();
          const errShort = err.length > 180 ? err.slice(0, 180) + "..." : err;
          setStatus(`翻譯完成（規則備援）${errShort ? "｜llmError: " + errShort : ""}`);
        } else {
          setStatus("翻譯完成");
        }
      } catch (err) {
        console.error(err);
        outputTextEl.textContent = `❌ 翻譯失敗：${err.message}`;
        setStatus("翻譯失敗");
      } finally {
        // Keep status visible so users can see success/failure instead of "no reaction".
      }
    }

    btnTranslateEl.addEventListener("click", translateNow);

    btnClearEl.addEventListener("click", () => {
      inputTextEl.value = "";
      outputTextEl.textContent = "（尚無結果）";
      setStatus("");
    });

    btnResetAllEl.addEventListener("click", () => {
      if (!confirm("確定要重置？")) return;
      inputTextEl.value = "";
      outputTextEl.textContent = "（尚無結果）";
      sourceLangEl.value = "auto";
      targetLangEl.value = "zh-Hant";
      fileInputEl.value = "";
      setStatus("");
    });

    btnExportTxtEl.addEventListener("click", () => {
      const out = outputTextEl.textContent || "";
      if (!out || out === "（尚無結果）") return alert("沒有可匯出的翻譯結果");
      const name = `translation_${new Date().toISOString().slice(0,10)}.txt`;
      downloadFile(name, out, "text/plain;charset=utf-8");
    });

    btnExportCsvEl.addEventListener("click", () => {
      const out = outputTextEl.textContent || "";
      if (!out || out === "（尚無結果）") return alert("沒有可匯出的翻譯結果");
      const csvHeader = "\uFEFF";
      const header = `"translated"`;
      const rows = out.split(/\r?\n/).map(line => `"${line.replace(/"/g,'""')}"`).join("\n");
      const content = `${csvHeader}${header}\n${rows}`;
      const name = `translation_${new Date().toISOString().slice(0,10)}.csv`;
      downloadFile(name, content, "text/csv;charset=utf-8");
    });

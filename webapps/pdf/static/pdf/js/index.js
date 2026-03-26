const API_EXTRACT = apiurl("extract/");
const API_SUMMARY = apiurl("summary/");
const API_TXT = apiurl("download/txt/");
const API_DOCX = apiurl("download/docx/");

const $ = (id) => document.getElementById(id);
const pdf = $("pdf");
const out = $("out");
const status = $("status");
const summaryStatus = $("summaryStatus");
const summaryOut = $("summaryOut");

function setStatus(html) {
  status.innerHTML = html;
}

function setSummaryStatus(html) {
  summaryStatus.innerHTML = html;
}

function getFile() {
  const f = pdf.files && pdf.files[0];
  if (!f) {
    alert("請先選擇 PDF 檔案");
    return null;
  }
  return f;
}

async function extract() {
  const f = getFile();
  if (!f) return;

  setStatus("⏳ 擷取中（若啟動 OCR 會較久）...");
  out.value = "⏳ 擷取中...";

  const fd = new FormData();
  fd.append("pdf", f);
  try {
    const r = await fetch(API_EXTRACT, { method: "POST", body: fd });
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    let j = null;
    if (ct.includes("application/json")) {
      j = await r.json();
    } else {
      const raw = await r.text();
      throw new Error("API 回傳非 JSON：" + raw.slice(0, 120));
    }

    if (!r.ok || !j || !j.ok) {
      out.value = "";
      setStatus("<span class='err'>✖ " + ((j && j.error) || ("HTTP " + r.status)) + "</span>");
      return;
    }

    out.value = j.text || "";
    const tag = j.used_ocr ? "（抽取 + OCR）" : "（抽字）";
    setStatus(
      "<span class='ok'>✅ 完成</span> " +
        tag +
        "（" +
        (j.filename || "") +
        "，" +
        (j.chars ?? 0) +
        "字元）",
    );
  } catch (e) {
    out.value = "";
    setStatus("<span class='err'>✖ 擷取失敗：" + ((e && e.message) || "未知錯誤") + "</span>");
  }
}

async function summarize() {
  const text = (out.value || "").trim();
  if (!text) {
    alert("請先完成文件擷取，再進行摘要");
    return;
  }

  setSummaryStatus("⏳ 摘要產生中...");
  summaryOut.value = "⏳ 摘要產生中...";

  try {
    const r = await fetch(API_SUMMARY, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const ct = (r.headers.get("content-type") || "").toLowerCase();
    let j = null;
    if (ct.includes("application/json")) {
      j = await r.json();
    } else {
      const raw = await r.text();
      throw new Error("摘要 API 回傳非 JSON：" + raw.slice(0, 120));
    }

    if (!r.ok || !j || !j.ok) {
      setSummaryStatus("<span class='err'>✖ " + ((j && j.error) || ("HTTP " + r.status)) + "</span>");
      summaryOut.value = "";
      return;
    }

    summaryOut.value = j.summary || "";
    if (j.fallback) {
      setSummaryStatus("<span class='ok'>✅ 摘要完成（備援模式）</span>");
    } else {
      setSummaryStatus("<span class='ok'>✅ 摘要完成</span>");
    }
  } catch (e) {
    summaryOut.value = "";
    setSummaryStatus("<span class='err'>✖ 摘要失敗：" + ((e && e.message) || "未知錯誤") + "</span>");
  }
}

async function dl(ep, fallback) {
  const f = getFile();
  if (!f) return;

  const fd = new FormData();
  fd.append("pdf", f);

  const r = await fetch(ep, { method: "POST", body: fd });
  if (!r.ok) {
    alert("下載失敗：" + r.status);
    return;
  }

  const b = await r.blob();

  let fn = fallback;
  const cd = r.headers.get("Content-Disposition") || "";
  const m = cd.match(/filename="([^"]+)"/i);
  if (m && m[1]) fn = m[1];

  const u = URL.createObjectURL(b);
  const a = document.createElement("a");
  a.href = u;
  a.download = fn;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(u), 800);
}

$("btnExtract").addEventListener("click", extract);
$("btnSummary").addEventListener("click", summarize);
$("btnTxt").addEventListener("click", () => dl(API_TXT, "output.txt"));
$("btnDocx").addEventListener("click", () => dl(API_DOCX, "output.docx"));

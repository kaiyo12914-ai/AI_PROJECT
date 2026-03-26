const apiurlFn = (typeof window.apiurl === "function" && window.apiurl) || ((p) => p);
const API_BUILD = apiurlFn("build_text/");
const API_SUMMARY = apiurlFn("summary/");

const $ = (id) => document.getElementById(id);

const refs = {
  title: $("title"),
  notes: $("notes"),
  image: $("image"),
  out: $("out"),
  summaryOut: $("summaryOut"),
  status: $("status"),
  summaryStatus: $("summaryStatus"),
  uploadStatus: $("uploadStatus"),
  go: $("go"),
  summary: $("summary"),
  copy: $("copy"),
  downloadTxt: $("downloadTxt"),
  pasteZone: $("pasteZone"),
  imgInput: $("imgInput"),
  imgPreview: $("imgPreview"),
};

function setStatus(msg, level = "normal") {
  refs.status.classList.remove("ok", "err");
  if (level === "ok") refs.status.classList.add("ok");
  if (level === "err") refs.status.classList.add("err");
  refs.status.textContent = msg || "";
}

function setSummaryStatus(msg, level = "normal") {
  refs.summaryStatus.classList.remove("ok", "err");
  if (level === "ok") refs.summaryStatus.classList.add("ok");
  if (level === "err") refs.summaryStatus.classList.add("err");
  refs.summaryStatus.textContent = msg || "";
}

function getSafeFileName() {
  const title = (refs.title.value || "").trim();
  const base = title || "graph_text_result";
  return `${base.replace(/[\\/:*?"<>|]+/g, "_")}.txt`;
}

function setImageFile(file) {
  if (!file) return;
  const dt = new DataTransfer();
  dt.items.add(file);
  refs.image.files = dt.files;
  refs.imgInput.files = dt.files;

  refs.imgPreview.src = URL.createObjectURL(file);
  refs.imgPreview.style.display = "block";
  refs.uploadStatus.textContent = `已選擇：${file.name}`;
}

async function buildText() {
  const fd = new FormData();
  fd.append("title", refs.title.value || "");
  fd.append("notes", refs.notes.value || "");
  if (refs.image.files && refs.image.files[0]) {
    fd.append("image", refs.image.files[0]);
  }

  refs.go.disabled = true;
  setStatus("產生中...");
  try {
    const resp = await fetch(API_BUILD, { method: "POST", body: fd });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }

    refs.out.value = data.text || "";
    setStatus("產生完成", "ok");
  } catch (err) {
    setStatus(`產生失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.go.disabled = false;
  }
}

async function summarizeText() {
  const text = (refs.out.value || "").trim();
  if (!text) {
    alert("請先產生文字內容");
    return;
  }

  refs.summary.disabled = true;
  setSummaryStatus("摘要中...");
  refs.summaryOut.value = "";
  try {
    const resp = await fetch(API_SUMMARY, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }

    refs.summaryOut.value = data.summary || "";
    setSummaryStatus("摘要完成", "ok");
  } catch (err) {
    setSummaryStatus(`摘要失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.summary.disabled = false;
  }
}

async function copyText() {
  const text = refs.out.value || "";
  if (!text.trim()) {
    alert("目前沒有可複製的文字");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setStatus("已複製到剪貼簿", "ok");
  } catch {
    refs.out.focus();
    refs.out.select();
    document.execCommand("copy");
    setStatus("已複製到剪貼簿", "ok");
  }
}

function downloadTxt() {
  const text = refs.out.value || "";
  if (!text.trim()) {
    alert("目前沒有可下載的文字");
    return;
  }
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = getSafeFileName();
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 800);
}

refs.go?.addEventListener("click", buildText);
refs.summary?.addEventListener("click", summarizeText);
refs.copy?.addEventListener("click", copyText);
refs.downloadTxt?.addEventListener("click", downloadTxt);

refs.image?.addEventListener("change", () => {
  const file = refs.image.files && refs.image.files[0];
  if (file) setImageFile(file);
});

refs.pasteZone?.addEventListener("click", () => refs.imgInput.click());
refs.imgInput?.addEventListener("change", () => {
  const file = refs.imgInput.files && refs.imgInput.files[0];
  if (file) setImageFile(file);
});

document.addEventListener("paste", (e) => {
  const items = e.clipboardData?.items || [];
  for (const item of items) {
    if (item.type && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        setImageFile(file);
        setStatus("已貼上圖片，可直接產生文字", "ok");
      }
      break;
    }
  }
});

refs.pasteZone?.addEventListener("dragover", (e) => {
  e.preventDefault();
  refs.pasteZone.classList.add("drag");
});
refs.pasteZone?.addEventListener("dragleave", () => {
  refs.pasteZone.classList.remove("drag");
});
refs.pasteZone?.addEventListener("drop", (e) => {
  e.preventDefault();
  refs.pasteZone.classList.remove("drag");
  const file = e.dataTransfer?.files && e.dataTransfer.files[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    setStatus("僅支援圖片檔案", "err");
    return;
  }
  setImageFile(file);
  setStatus("圖片已載入", "ok");
});

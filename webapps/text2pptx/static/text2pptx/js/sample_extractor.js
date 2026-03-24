(function () {
  const STORAGE_KEY = "text2pptx_sample_from_pptx";
  const textarea = document.getElementById("extracted-sample-text");
  const copyBtn = document.getElementById("copy-extracted-sample-btn");
  const saveBtn = document.getElementById("save-extracted-sample-btn");
  const applyBtn = document.getElementById("apply-extracted-sample-btn");

  if (!textarea) return;

  function getText() {
    return (textarea.value || "").trim();
  }

  function toSafeFilenamePart(name) {
    return String(name || "")
      .trim()
      .replace(/\.pptx$/i, "")
      .replace(/[\\/:*?"<>|]/g, "_")
      .replace(/\s+/g, "_");
  }

  function buildDownloadName() {
    const baseFromUpload = saveBtn ? toSafeFilenamePart(saveBtn.dataset.uploadedFilename) : "";
    const now = new Date();
    const ts = [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
      "_",
      String(now.getHours()).padStart(2, "0"),
      String(now.getMinutes()).padStart(2, "0"),
      String(now.getSeconds()).padStart(2, "0"),
    ].join("");
    const base = baseFromUpload || "pptx_sample";
    return base + "_text2pptx_" + ts + ".txt";
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async function () {
      const text = getText();
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "已複製";
        setTimeout(function () {
          copyBtn.textContent = "複製結果";
        }, 1200);
      } catch (_error) {
        alert("複製失敗，請手動複製。");
      }
    });
  }

  if (saveBtn) {
    saveBtn.addEventListener("click", function () {
      const text = getText();
      if (!text) {
        alert("目前沒有可儲存的內容。");
        return;
      }
      const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = buildDownloadName();
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      const text = getText();
      if (!text) {
        alert("目前沒有可帶回主頁的內容。");
        return;
      }
      try {
        localStorage.setItem(STORAGE_KEY, text);
      } catch (_error) {
        // ignore localStorage write errors and fallback to direct navigation
      }
      const targetUrl = applyBtn.dataset.targetUrl || "";
      if (targetUrl) {
        window.location.href = targetUrl;
      }
    });
  }
})();

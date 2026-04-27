(function () {
  const runBtn = document.getElementById("extract-batch-sample-and-master-btn");
  const sourcePickerBtn = document.getElementById("batch-source-picker-btn");
  const sourcePickerInput = document.getElementById("batch-source-picker-input");
  const sourcePickedLabel = document.getElementById("batch-source-picked-label");
  const outputPickerBtn = document.getElementById("batch-output-picker-btn");
  const outputPickedLabel = document.getElementById("batch-output-picked-label");
  const resultTextarea = document.getElementById("batch-extract-result-text");

  if (!runBtn || !sourcePickerBtn || !sourcePickerInput || !outputPickerBtn || !resultTextarea) return;

  let selectedSourceFiles = [];
  let outputDirHandle = null;

  function getCsrfToken() {
    const formToken = document.querySelector('.import-form input[name="csrfmiddlewaretoken"]');
    if (formToken && formToken.value) return formToken.value;
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function resolveApiUrl(path, fallbackPath) {
    if (path) return path;
    if (typeof window.apiurl === "function") return window.apiurl(fallbackPath);
    return fallbackPath;
  }

  function toSafeStem(filename, fallback) {
    const base = String(filename || "").replace(/\.pptx$/i, "").trim() || fallback || "pptx";
    return base.replace(/[\\/:*?"<>|]/g, "_").replace(/\s+/g, "_").replace(/^_+|_+$/g, "") || "pptx";
  }

  function setLoading(loading) {
    runBtn.disabled = !!loading;
    sourcePickerBtn.disabled = !!loading;
    sourcePickerInput.disabled = !!loading;
    outputPickerBtn.disabled = !!loading;
    runBtn.textContent = loading ? "批次處理中..." : "執行全目錄抽取";
  }

  async function requestExtractSample(file) {
    const apiUrl = resolveApiUrl(
      runBtn.dataset.apiSampleUrl,
      "/text2pptx/extract_sample/"
    );
    const csrfToken = getCsrfToken();
    const formData = new FormData();
    formData.append("pptx_file", file, file.name);

    const resp = await fetch(apiUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: Object.assign(
        { "X-Requested-With": "XMLHttpRequest" },
        csrfToken ? { "X-CSRFToken": csrfToken } : {}
      ),
      body: formData,
    });
    const data = await resp.json();
    if (!resp.ok || !data || data.success !== true) {
      throw new Error((data && (data.message || data.error)) || "sample extract failed");
    }
    return data;
  }

  async function requestExtractTemplate(file) {
    const apiUrl = resolveApiUrl(
      runBtn.dataset.apiTemplateUrl,
      "/text2pptx/extract_template/"
    );
    const csrfToken = getCsrfToken();
    const formData = new FormData();
    formData.append("pptx_file", file, file.name);

    const resp = await fetch(apiUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: Object.assign(
        { "X-Requested-With": "XMLHttpRequest" },
        csrfToken ? { "X-CSRFToken": csrfToken } : {}
      ),
      body: formData,
    });
    const data = await resp.json();
    if (!resp.ok || !data || data.success !== true) {
      throw new Error((data && (data.message || data.error)) || "template extract failed");
    }
    return data;
  }

  async function downloadBlob(url) {
    let finalUrl = String(url || "").trim();
    if (!finalUrl) throw new Error("empty download url");
    if (finalUrl.startsWith("/") && typeof window.apiurl === "function") {
      finalUrl = window.apiurl(finalUrl);
    }
    const resp = await fetch(finalUrl, { credentials: "same-origin" });
    if (!resp.ok) {
      throw new Error("download failed: HTTP " + resp.status);
    }
    return await resp.blob();
  }

  async function writeTextFile(dirHandle, filename, text) {
    const handle = await dirHandle.getFileHandle(filename, { create: true });
    const writable = await handle.createWritable();
    await writable.write(String(text || ""));
    await writable.close();
  }

  async function writeBlobFile(dirHandle, filename, blob) {
    const handle = await dirHandle.getFileHandle(filename, { create: true });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
  }

  function filterPptxFiles(fileList) {
    return Array.from(fileList || [])
      .filter(function (f) {
        return /\.pptx$/i.test(String(f && f.name || ""));
      })
      .sort(function (a, b) {
        const pa = String(a.webkitRelativePath || a.name || "").toLowerCase();
        const pb = String(b.webkitRelativePath || b.name || "").toLowerCase();
        return pa.localeCompare(pb);
      });
  }

  sourcePickerBtn.addEventListener("click", function () {
    sourcePickerInput.click();
  });

  sourcePickerInput.addEventListener("change", function () {
    selectedSourceFiles = filterPptxFiles(sourcePickerInput.files);
    if (sourcePickedLabel) {
      if (selectedSourceFiles.length > 0) {
        const firstPath = String(selectedSourceFiles[0].webkitRelativePath || selectedSourceFiles[0].name || "");
        const rootName = firstPath.split("/")[0] || "(已選擇)";
        sourcePickedLabel.textContent = rootName + "（" + selectedSourceFiles.length + " 個 .pptx）";
      } else {
        sourcePickedLabel.textContent = "未選擇來源資料夾";
      }
    }
  });

  outputPickerBtn.addEventListener("click", async function () {
    try {
      if (!window.showDirectoryPicker) {
        alert("目前瀏覽器不支援資料夾選擇器。請改用新版 Edge/Chrome。");
        return;
      }
      outputDirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
      if (outputPickedLabel) {
        outputPickedLabel.textContent = outputDirHandle && outputDirHandle.name
          ? outputDirHandle.name
          : "已選擇輸出資料夾";
      }
    } catch (_error) {
      // user cancelled
    }
  });

  runBtn.addEventListener("click", async function () {
    if (!selectedSourceFiles.length) {
      alert("請先選擇來源資料夾。");
      return;
    }
    if (!outputDirHandle) {
      alert("請先選擇輸出資料夾。");
      return;
    }

    setLoading(true);
    resultTextarea.value = "批次處理中，請稍候...";
    const lines = [];
    let successCount = 0;
    let failedCount = 0;

    for (let i = 0; i < selectedSourceFiles.length; i += 1) {
      const file = selectedSourceFiles[i];
      const stem = toSafeStem(file.name, "pptx_" + (i + 1));
      try {
        const sampleData = await requestExtractSample(file);
        const templateData = await requestExtractTemplate(file);
        const masterBlob = await downloadBlob(templateData.download_url || templateData.media_download_url);

        await writeTextFile(outputDirHandle, stem + "_sample.txt", sampleData.sample_text || "");
        await writeTextFile(outputDirHandle, stem + "_master_template.txt", templateData.template_text || "");
        await writeBlobFile(outputDirHandle, stem + "_master_template.pptx", masterBlob);

        successCount += 1;
        lines.push("[OK] " + file.name);
      } catch (error) {
        failedCount += 1;
        lines.push("[FAIL] " + file.name + " - " + (error && error.message ? error.message : "未知錯誤"));
      }
    }

    const summary = [
      "批次處理完成",
      "處理總數: " + selectedSourceFiles.length,
      "成功: " + successCount,
      "失敗: " + failedCount,
      "",
    ];
    resultTextarea.value = summary.concat(lines).join("\n");
    setLoading(false);
  });
})();

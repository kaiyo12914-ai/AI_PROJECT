(function () {
  const STORAGE_KEY = "text2pptx_sample_from_pptx";
  const TEMPLATE_TEXT_KEY = "text2pptx_template_text";
  const TEMPLATE_NAME_KEY = "text2pptx_template_filename";
  const TEMPLATE_PPTX_KEY = "text2pptx_template_pptx_filename";
  let currentTemplateText = "";
  let currentTemplateFilename = "";
  let currentTemplatePptxFilename = "";

  const textarea = document.getElementById("extracted-sample-text");
  const copyBtn = document.getElementById("copy-extracted-sample-btn");
  const saveBtn = document.getElementById("save-extracted-sample-btn");
  const applyBtn = document.getElementById("apply-extracted-sample-btn");
  const extractMasterTemplateBtn = document.getElementById("extract-master-template-btn");
  const extractSampleAndMasterBtn = document.getElementById("extract-sample-and-master-btn");
  const importTemplateBtn = document.getElementById("import-master-template-btn");
  const templateFileInput = document.getElementById("master-template-file-input");
  const templateImportInfo = document.getElementById("template-import-info");
  const importedTemplateFilenameEl = document.getElementById("imported-template-filename");
  const templatePreviewToggleWrap = document.getElementById("template-preview-toggle-wrap");
  const templatePreviewToggle = document.getElementById("toggle-template-preview");
  const templatePreviewWrap = document.getElementById("template-preview-wrap");
  const templatePreviewTextarea = document.getElementById("imported-template-text");
  const generateRestoredBtn = document.getElementById("generate-restored-pptx-btn");
  const restoredResultWrap = document.getElementById("restored-pptx-result-wrap");
  const restoredResultMessage = document.getElementById("restored-pptx-result-message");
  const restoredDownloadLink = document.getElementById("restored-pptx-download-link");
  const restoredFeedback = document.getElementById("restored-pptx-feedback");
  const extractorForm = document.querySelector(".import-form");
  const pptxFileInput = extractorForm
    ? extractorForm.querySelector('input[name="pptx_file"]')
    : null;

  if (!textarea) return;

  function loadStoredTemplateState() {
    try {
      return {
        templateText: localStorage.getItem(TEMPLATE_TEXT_KEY) || "",
        templateFilename: localStorage.getItem(TEMPLATE_NAME_KEY) || "",
        templatePptxFilename: localStorage.getItem(TEMPLATE_PPTX_KEY) || "",
      };
    } catch (_error) {
      return {
        templateText: "",
        templateFilename: "",
        templatePptxFilename: "",
      };
    }
  }

  function persistTemplateState() {
    try {
      if (currentTemplateText) {
        localStorage.setItem(TEMPLATE_TEXT_KEY, currentTemplateText);
        localStorage.setItem(TEMPLATE_NAME_KEY, currentTemplateFilename || "");
        localStorage.setItem(TEMPLATE_PPTX_KEY, currentTemplatePptxFilename || "");
      } else {
        localStorage.removeItem(TEMPLATE_TEXT_KEY);
        localStorage.removeItem(TEMPLATE_NAME_KEY);
        localStorage.removeItem(TEMPLATE_PPTX_KEY);
      }
    } catch (_error) {
      // ignore storage errors
    }
  }

  function hydrateTemplateStateFromStorage() {
    const stored = loadStoredTemplateState();
    currentTemplateText = String(stored.templateText || "").trim();
    currentTemplateFilename = String(stored.templateFilename || "").trim();
    currentTemplatePptxFilename = String(stored.templatePptxFilename || "").trim();

    if (importedTemplateFilenameEl) {
      importedTemplateFilenameEl.textContent = currentTemplateFilename || "";
    }
    if (templateImportInfo) {
      templateImportInfo.hidden = !currentTemplateText;
    }
    if (templatePreviewToggleWrap) {
      templatePreviewToggleWrap.hidden = !currentTemplateText;
    }
    if (templatePreviewTextarea) {
      templatePreviewTextarea.value = currentTemplateText;
    }
    if (templatePreviewToggle) {
      templatePreviewToggle.checked = !!currentTemplateText;
    }
    setTemplatePreviewVisible();
  }

  hydrateTemplateStateFromStorage();

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

  function getSourceFilename() {
    if (!saveBtn) return "";
    return String(saveBtn.dataset.uploadedFilename || "").trim();
  }

  function getCsrfToken() {
    const fromForm = extractorForm
      ? extractorForm.querySelector('input[name="csrfmiddlewaretoken"]')
      : null;
    if (fromForm && fromForm.value) return fromForm.value;

    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function resolveApiUrl(path, fallbackPath) {
    if (path) return path;
    if (typeof window.apiurl === "function") {
      return window.apiurl(fallbackPath);
    }
    return fallbackPath;
  }

  function showRestoredFeedback(message, isError) {
    if (!restoredFeedback) return;
    restoredFeedback.textContent = String(message || "").trim();
    restoredFeedback.className = "msg " + (isError ? "error" : "success");
    restoredFeedback.style.display = restoredFeedback.textContent ? "block" : "none";
  }

  function clearRestoredResult() {
    if (restoredResultWrap) restoredResultWrap.hidden = true;
    if (restoredResultMessage) restoredResultMessage.textContent = "";
    if (restoredDownloadLink) {
      restoredDownloadLink.hidden = true;
      restoredDownloadLink.removeAttribute("href");
      restoredDownloadLink.removeAttribute("download");
    }
  }

  function setTemplatePreviewVisible() {
    if (!templatePreviewWrap) return;
    const hasTemplate = !!currentTemplateText;
    const shouldShow = !!(hasTemplate && templatePreviewToggle && templatePreviewToggle.checked);
    templatePreviewWrap.hidden = !shouldShow;
  }

  function isSupportedTemplateFile(filename) {
    return /\.(json|txt)$/i.test(String(filename || "").trim());
  }

  function readFileAsText(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || ""));
      };
      reader.onerror = function () {
        reject(new Error("無法讀取模板檔案"));
      };
      reader.readAsText(file, "utf-8");
    });
  }

  function setGenerateLoading(loading) {
    if (!generateRestoredBtn) return;
    generateRestoredBtn.disabled = !!loading;
    generateRestoredBtn.textContent = loading ? "生成中..." : "生成還原簡報";
  }

  function setImportLoading(loading) {
    if (!importTemplateBtn) return;
    importTemplateBtn.disabled = !!loading;
    importTemplateBtn.textContent = loading ? "匯入中..." : "匯入母片模板";
  }

  function setExtractTemplateLoading(loading) {
    if (!extractMasterTemplateBtn) return;
    extractMasterTemplateBtn.disabled = !!loading;
    extractMasterTemplateBtn.textContent = loading ? "抽取中..." : "抽取母片模板";
  }

  function setExtractBothLoading(loading) {
    if (!extractSampleAndMasterBtn) return;
    extractSampleAndMasterBtn.disabled = !!loading;
    extractSampleAndMasterBtn.textContent = loading ? "處理中..." : "抽取範例及母片";
  }

  async function downloadFileByUrl(downloadUrl, outputFilename) {
    const url = String(downloadUrl || "").trim();
    if (!url) return;

    let finalUrl = url;
    if (url.startsWith("/media/") && typeof window.apiurl === "function") {
      finalUrl = window.apiurl(url);
    }

    const a = document.createElement("a");
    a.href = finalUrl;
    if (outputFilename) {
      a.download = String(outputFilename);
    }
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }

  function applyTemplateText(templateText, templateName, successMessage, templatePptxFilename) {
    currentTemplateText = String(templateText || "").trim();
    currentTemplateFilename = String(templateName || "").trim();
    currentTemplatePptxFilename = String(templatePptxFilename || "").trim();
    if (!currentTemplateText) {
      throw new Error("母片模板內容為空");
    }

    if (importedTemplateFilenameEl) {
      importedTemplateFilenameEl.textContent = currentTemplateFilename || "未命名模板";
    }
    if (templateImportInfo) {
      templateImportInfo.hidden = false;
    }
    if (templatePreviewToggleWrap) {
      templatePreviewToggleWrap.hidden = false;
    }
    if (templatePreviewToggle) {
      templatePreviewToggle.checked = true;
    }
    if (templatePreviewTextarea) {
      templatePreviewTextarea.value = currentTemplateText;
    }
    persistTemplateState();
    setTemplatePreviewVisible();
    showRestoredFeedback(successMessage, false);
  }

  async function requestExtractTemplate(file) {
    const apiUrl = resolveApiUrl(
      (extractMasterTemplateBtn && extractMasterTemplateBtn.dataset.apiUrl)
        || (extractSampleAndMasterBtn && extractSampleAndMasterBtn.dataset.apiUrl),
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
      const message = (data && (data.message || data.error)) || "母片模板抽取失敗";
      throw new Error(message);
    }
    return data;
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

  if (templatePreviewToggle) {
    templatePreviewToggle.addEventListener("change", function () {
      setTemplatePreviewVisible();
    });
  }

  if (extractMasterTemplateBtn && pptxFileInput) {
    extractMasterTemplateBtn.addEventListener("click", async function () {
      const file = pptxFileInput.files && pptxFileInput.files[0] ? pptxFileInput.files[0] : null;
      if (!file) {
        alert("請先選擇 PPTX 檔案");
        return;
      }

      setExtractTemplateLoading(true);
      showRestoredFeedback("", false);
      clearRestoredResult();

      try {
        const data = await requestExtractTemplate(file);
        const templateName = String(file.name || "").replace(/\.pptx$/i, "") + "_母片模板.txt";
        applyTemplateText(
          data.template_text,
          templateName,
          data.message || "母片模板抽取成功",
          data.template_pptx_filename || data.output_filename || ""
        );
        await downloadFileByUrl(data.download_url, data.output_filename);
      } catch (error) {
        showRestoredFeedback(
          "母片模板抽取失敗：" + (error && error.message ? error.message : "未知錯誤"),
          true
        );
      } finally {
        setExtractTemplateLoading(false);
      }
    });
  }

  if (extractSampleAndMasterBtn && extractorForm && pptxFileInput) {
    extractSampleAndMasterBtn.addEventListener("click", async function () {
      const file = pptxFileInput.files && pptxFileInput.files[0] ? pptxFileInput.files[0] : null;
      if (!file) {
        alert("請先選擇 PPTX 檔案");
        return;
      }

      setExtractBothLoading(true);
      showRestoredFeedback("", false);

      try {
        const data = await requestExtractTemplate(file);
        const templateName = String(file.name || "").replace(/\.pptx$/i, "") + "_母片模板.txt";
        applyTemplateText(
          data.template_text,
          templateName,
          data.message || "母片模板抽取成功",
          data.template_pptx_filename || data.output_filename || ""
        );
        await downloadFileByUrl(data.download_url, data.output_filename);
      } catch (error) {
        showRestoredFeedback(
          "母片模板抽取失敗：" + (error && error.message ? error.message : "未知錯誤"),
          true
        );
      } finally {
        setExtractBothLoading(false);
        // Continue with original sample extraction flow.
        extractorForm.submit();
      }
    });
  }

  if (importTemplateBtn && templateFileInput) {
    importTemplateBtn.addEventListener("click", function () {
      templateFileInput.click();
    });

    templateFileInput.addEventListener("change", async function () {
      const file = templateFileInput.files && templateFileInput.files[0] ? templateFileInput.files[0] : null;
      if (!file) return;
      if (!isSupportedTemplateFile(file.name)) {
        alert("僅支援 .json 或 .txt 模板檔案");
        templateFileInput.value = "";
        return;
      }

      setImportLoading(true);
      showRestoredFeedback("", false);
      clearRestoredResult();

      try {
        const templateText = (await readFileAsText(file)).trim();
        applyTemplateText(templateText, String(file.name || "").trim(), "母片模板匯入成功", "");
      } catch (error) {
        currentTemplateText = "";
        currentTemplateFilename = "";
        currentTemplatePptxFilename = "";
        if (templatePreviewTextarea) {
          templatePreviewTextarea.value = "";
        }
        persistTemplateState();
        setTemplatePreviewVisible();
        showRestoredFeedback("母片模板匯入失敗：" + (error && error.message ? error.message : "未知錯誤"), true);
      } finally {
        setImportLoading(false);
        templateFileInput.value = "";
      }
    });
  }

  if (generateRestoredBtn) {
    generateRestoredBtn.addEventListener("click", async function () {
      const extractedText = getText();
      if (!extractedText) {
        alert("請先取得抽取文字結果");
        return;
      }
      if (!currentTemplateText) {
        alert("請先匯入母片模板");
        return;
      }

      const payload = {
        extracted_text: extractedText,
        template_text: currentTemplateText,
        template_pptx_filename: currentTemplatePptxFilename,
        source_filename: getSourceFilename(),
      };

      const apiUrl = resolveApiUrl(
        generateRestoredBtn.dataset.apiUrl,
        "/text2pptx/generate_restored_pptx/"
      );
      const csrfToken = getCsrfToken();

      setGenerateLoading(true);
      showRestoredFeedback("", false);
      clearRestoredResult();

      try {
        const resp = await fetch(apiUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: Object.assign(
            {
              "Content-Type": "application/json",
              "X-Requested-With": "XMLHttpRequest",
            },
            csrfToken ? { "X-CSRFToken": csrfToken } : {}
          ),
          body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!resp.ok || !data || data.success !== true) {
          const message = (data && (data.message || data.error)) || "還原簡報生成失敗";
          showRestoredFeedback(message, true);
          return;
        }

        showRestoredFeedback("還原簡報生成成功", false);
        if (restoredResultWrap) {
          restoredResultWrap.hidden = false;
        }
        if (restoredResultMessage) {
          const serverMessage = String(data.message || "").trim();
          const filename = String(data.output_filename || "").trim();
          restoredResultMessage.textContent = filename
            ? (serverMessage || "還原簡報生成成功") + "（" + filename + "）"
            : (serverMessage || "還原簡報生成成功");
        }

        const downloadUrl = String(data.download_url || "").trim();
        if (downloadUrl && restoredDownloadLink) {
          restoredDownloadLink.href = downloadUrl;
          if (data.output_filename) {
            restoredDownloadLink.setAttribute("download", String(data.output_filename));
          }
          restoredDownloadLink.hidden = false;
        }
      } catch (error) {
        showRestoredFeedback(
          "還原簡報生成失敗：" + (error && error.message ? error.message : "未知錯誤"),
          true
        );
      } finally {
        setGenerateLoading(false);
      }
    });
  }
})();

(function () {
  const STORAGE_KEY = "text2pptx_sample_from_pptx";
  const form = document.getElementById("pptx-generate-form");
  const textInput = document.getElementById("pptx_text_input");
  const sampleText = document.getElementById("pptx_sample_text");
  const applyBtn = document.getElementById("apply-sample-btn");
  const loadSampleBtn = document.getElementById("load-sample-file-btn");
  const loadSampleInput = document.getElementById("load-sample-file-input");
  const analyzeBtn = document.getElementById("analyze-image-prompts-btn");
  const modal = document.getElementById("image-prompts-modal");
  const modalCloseBtn = document.getElementById("close-image-prompts-modal");
  const modalConfirmBtn = document.getElementById("confirm-image-prompts-btn");
  const modalCopyBtn = document.getElementById("copy-image-prompts-btn");
  const preview = document.getElementById("image-prompts-preview");

  if (!form || !textInput || !sampleText || !applyBtn) return;

  function setSampleText(text) {
    const clean = String(text || "").replace(/\r\n/g, "\n");
    sampleText.textContent = clean;
    textInput.value = clean;
  }

  try {
    const importedSample = (window.localStorage && localStorage.getItem(STORAGE_KEY)) || "";
    if (importedSample) {
      setSampleText(importedSample);
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch (_error) {
    // ignore storage errors
  }

  function openModal() {
    if (!modal) return;
    modal.hidden = false;
  }

  function closeModal() {
    if (!modal) return;
    modal.hidden = true;
  }

  applyBtn.addEventListener("click", function () {
    const text = (sampleText.textContent || "").trim();
    if (!text) return;
    textInput.value = text;
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });

  if (loadSampleBtn && loadSampleInput) {
    loadSampleBtn.addEventListener("click", function () {
      loadSampleInput.click();
    });

    loadSampleInput.addEventListener("change", function () {
      const file = loadSampleInput.files && loadSampleInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = function () {
        const text = String(reader.result || "");
        if (!text.trim()) {
          alert("範本檔內容為空白。");
          return;
        }
        setSampleText(text);
        loadSampleBtn.textContent = "已載入";
        setTimeout(function () {
          loadSampleBtn.textContent = "讀取範本檔";
        }, 1200);
        loadSampleInput.value = "";
      };
      reader.onerror = function () {
        alert("讀取範本檔失敗，請確認檔案格式。");
        loadSampleInput.value = "";
      };
      reader.readAsText(file, "utf-8");
    });
  }

  if (modalCloseBtn) modalCloseBtn.addEventListener("click", closeModal);
  if (modalConfirmBtn) modalConfirmBtn.addEventListener("click", closeModal);

  if (modal) {
    modal.addEventListener("click", function (event) {
      if (event.target === modal) closeModal();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && modal && !modal.hidden) {
      closeModal();
    }
  });

  if (modalCopyBtn && preview) {
    modalCopyBtn.addEventListener("click", async function () {
      const text = (preview.value || "").trim();
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        modalCopyBtn.textContent = "已複製";
        setTimeout(function () {
          modalCopyBtn.textContent = "複製提示詞";
        }, 1200);
      } catch (_error) {
        alert("複製失敗，請手動複製。");
      }
    });
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", async function () {
      const text = (textInput.value || "").trim();
      if (!text) {
        alert("請先輸入文字內容。");
        return;
      }

      const rawUrl = form.dataset.analyzePromptsUrl;
      if (!rawUrl) {
        alert("找不到解析 API 網址。");
        return;
      }
      const url = typeof window.apiurl === "function" ? window.apiurl(rawUrl) : rawUrl;

      analyzeBtn.disabled = true;
      const originalText = analyzeBtn.textContent;
      analyzeBtn.textContent = "解析中...";
      try {
        const formData = new FormData(form);
        const response = await fetch(url, {
          method: "POST",
          body: formData,
          credentials: "same-origin",
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
          throw new Error(data.error || "解析失敗。");
        }

        const resultText = (data.preview_text || "").trim();
        if (preview) {
          preview.value = resultText || "(目前沒有可顯示的提示詞)";
        }
        openModal();
      } catch (error) {
        alert(error && error.message ? error.message : "解析失敗。");
      } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = originalText;
      }
    });
  }
})();

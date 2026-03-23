(function () {
  const form = document.getElementById("pptx-generate-form");
  const textInput = document.getElementById("pptx_text_input");
  const sampleText = document.getElementById("pptx_sample_text");
  const applyBtn = document.getElementById("apply-sample-btn");
  const analyzeBtn = document.getElementById("analyze-image-prompts-btn");
  const modal = document.getElementById("image-prompts-modal");
  const modalCloseBtn = document.getElementById("close-image-prompts-modal");
  const modalConfirmBtn = document.getElementById("confirm-image-prompts-btn");
  const modalCopyBtn = document.getElementById("copy-image-prompts-btn");
  const preview = document.getElementById("image-prompts-preview");

  if (!form || !textInput || !sampleText || !applyBtn) {
    return;
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
        alert("複製失敗，請手動複製內容。");
      }
    });
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", async function () {
      const text = (textInput.value || "").trim();
      if (!text) {
        alert("請先輸入內容。");
        return;
      }

      const rawUrl = form.dataset.analyzePromptsUrl;
      if (!rawUrl) {
        alert("解析 API URL 未設定。");
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
          preview.value = resultText || "(沒有可用的提示詞輸出)";
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

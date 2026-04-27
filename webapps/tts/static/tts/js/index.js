// ---------------------------
  // Helpers (專案規範版)
  // ---------------------------
  const apiurlFn = (typeof window.apiurl === "function" && window.apiurl) || ((p) => p);
  const $ = (id) => document.getElementById(id);

  function setStatus(el, msg, ok=true) {
    el.className = "status " + (ok ? "ok" : "err");
    el.textContent = msg || "";
  }

  function safeJson(text) {
    try { return JSON.parse(text); } catch(e) { return null; }
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // ✅ 專案規範：所有 API 只走 apiUrl("node/path/")

  // ✅ 專案規範：把後端回的 media/static URL 統一轉為可用的「站內絕對路徑」
  // - 支援：完整 URL、/media/...、/comment/media/...、相對路徑 media/xxx 或 comment/media/xxx
  function absUrl(u){
    u = (u || "").trim();
    if(!u) return "";

    // already absolute URL
    if (/^https?:\/\//i.test(u)) return u;

    // normalize leading slash
    if (!u.startsWith("/")) u = "/" + u;

    const base = (document.body.dataset.baseUrl || "").trim(); // e.g. "" or "/comment"
    const prefix = base && base !== "/" ? base : "";

    // 如果後端已經回 /comment/... 就不要再加 /comment
    if (prefix && u.startsWith(prefix + "/")) return u;

    // 如果後端回 /media/... 或 /static/... 等，補上 prefix
    if (prefix) return prefix + u;

    return u;
  }

  // ---------------------------
  // TTS
  // ---------------------------
  const ttsText = $("ttsText");
  const ttsCount = $("ttsCount");
  const ttsModel = $("ttsModel");
  const btnTts = $("btnTts");
  const btnTtsClear = $("btnTtsClear");
  const ttsStatus = $("ttsStatus");
  const ttsResult = $("ttsResult");
  const audioPlayer = $("audioPlayer");

  const ttsFile = $("ttsFile");
  const btnTtsImport = $("btnTtsImport");
  const ttsFileName = $("ttsFileName");

  ttsText.addEventListener("input", () => {
    ttsCount.textContent = String(ttsText.value.length);
  });

  btnTtsClear.addEventListener("click", () => {
    ttsText.value = "";
    ttsCount.textContent = "0";
    ttsModel.value = "";
    ttsResult.textContent = "";
    ttsFile.value = "";
    ttsFileName.textContent = "";
    audioPlayer.style.display = "none";
    audioPlayer.removeAttribute("src");
    setStatus(ttsStatus, "");
  });

  btnTtsImport.addEventListener("click", () => ttsFile.click());

  // ✅ 匯入檔案 → 後端抽字 + 直接產生 wav
  ttsFile.addEventListener("change", async () => {
    const file = ttsFile.files && ttsFile.files[0];
    if (!file) return;

    ttsFileName.textContent = file.name;

    setStatus(ttsStatus, "上傳檔案並產生語音中…");
    ttsResult.textContent = "";
    audioPlayer.style.display = "none";
    audioPlayer.removeAttribute("src");

    btnTts.disabled = true;
    btnTtsImport.disabled = true;

    try {
      const form = new FormData();
      form.append("file", file);
      const model = (ttsModel.value || "").trim();
      if (model) form.append("model", model);

      const resp = await fetch(apiurlFn("tts/generate_from_file/"), {
        method: "POST",
        body: form,
      });

      const raw = await resp.text();
      const data = safeJson(raw);

      if (!data) {
        setStatus(ttsStatus, "回傳不是 JSON：\n" + raw, false);
        return;
      }

      if (!data.ok) {
        setStatus(ttsStatus, data.error || "匯入產生失敗", false);
        return;
      }

      if (data.text) {
        ttsText.value = data.text;
        ttsCount.textContent = String(ttsText.value.length);
      }

      const url = absUrl(data.wav_url || "");
      ttsResult.innerHTML = `
        <div>✅ 產生成功（由檔案匯入）</div>
        <div class="mono">wav_url: ${url ? `<a href="${url}" target="_blank" rel="noopener">${url}</a>` : "(無)"} </div>
        <div class="mono">bytes: ${data.bytes || ""}</div>
      `;

      if (url) {
        audioPlayer.src = url;
        audioPlayer.style.display = "block";
        audioPlayer.load();
        setStatus(ttsStatus, "完成 ✅");
      } else {
        setStatus(ttsStatus, "產生成功，但 wav_url 為空（請確認輸出目錄在 MEDIA_ROOT 之下）", false);
      }

    } catch (e) {
      setStatus(ttsStatus, "錯誤： " + (e?.message || String(e)), false);
    } finally {
      btnTts.disabled = false;
      btnTtsImport.disabled = false;
    }
  });

  // 原本文字直接產生
  btnTts.addEventListener("click", async () => {
    setStatus(ttsStatus, "產生中…");
    ttsResult.textContent = "";
    audioPlayer.style.display = "none";
    audioPlayer.removeAttribute("src");

    const text = (ttsText.value || "").trim();
    const model = (ttsModel.value || "").trim();

    if (!text) {
      setStatus(ttsStatus, "請先輸入文字", false);
      return;
    }

    btnTts.disabled = true;

    try {
      const resp = await fetch(apiurlFn("tts/generate/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, model }),
      });

      const raw = await resp.text();
      const data = safeJson(raw);

      if (!data) {
        setStatus(ttsStatus, "回傳不是 JSON：\n" + raw, false);
        return;
      }

      if (!data.ok) {
        setStatus(ttsStatus, data.error || "產生失敗", false);
        return;
      }

      const url = absUrl(data.wav_url || "");
      ttsResult.innerHTML = `
        <div>✅ 產生成功</div>
        <div class="mono">wav_url: ${url ? `<a href="${url}" target="_blank" rel="noopener">${url}</a>` : "(無)"} </div>
        <div class="mono">bytes: ${data.bytes || ""}</div>
      `;

      if (url) {
        audioPlayer.src = url;
        audioPlayer.style.display = "block";
        audioPlayer.load();
        setStatus(ttsStatus, "完成 ✅");
      } else {
        setStatus(ttsStatus, "產生成功，但 wav_url 為空（請確認輸出目錄在 MEDIA_ROOT 之下）", false);
      }

    } catch (e) {
      setStatus(ttsStatus, "錯誤： " + (e?.message || String(e)), false);
    } finally {
      btnTts.disabled = false;
    }
  });

  // ---------------------------
  // STT
  // ---------------------------
  const sttFile = $("sttFile");
  const btnStt = $("btnStt");
  const btnSttClear = $("btnSttClear");
  const sttText = $("sttText");
  const sttStatus = $("sttStatus");

  btnSttClear.addEventListener("click", () => {
    sttFile.value = "";
    sttText.value = "";
    setStatus(sttStatus, "");
  });

  btnStt.addEventListener("click", async () => {
    setStatus(sttStatus, "轉換中…");
    const file = sttFile.files && sttFile.files[0];
    if (!file) {
      setStatus(sttStatus, "請先選擇音檔", false);
      return;
    }

    btnStt.disabled = true;

    try {
      const form = new FormData();
      form.append("audio", file);

      const resp = await fetch(apiurlFn("tts/transcribe/"), {
        method: "POST",
        body: form,
      });

      const raw = await resp.text();
      const data = safeJson(raw);

      if (!data) {
        setStatus(sttStatus, "回傳不是 JSON：\n" + raw, false);
        return;
      }

      if (!data.ok) {
        setStatus(sttStatus, data.error || "轉換失敗", false);
        return;
      }

      sttText.value = data.text || "";
      setStatus(sttStatus, "完成 ✅");
    } catch (e) {
      setStatus(sttStatus, "錯誤： " + (e?.message || String(e)), false);
    } finally {
      btnStt.disabled = false;
    }
  });

  // ---------------------------
  // Export / Copy
  // ---------------------------
  const btnCopy = $("btnCopy");
  const btnExportTxt = $("btnExportTxt");
  const btnExportDocx = $("btnExportDocx");

  btnCopy.addEventListener("click", async () => {
    const text = (sttText.value || "").trim();
    if (!text) {
      setStatus(sttStatus, "沒有可複製的文字", false);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setStatus(sttStatus, "已複製到剪貼簿 ✅");
    } catch (e) {
      setStatus(sttStatus, "複製失敗（瀏覽器權限限制）", false);
    }
  });

  btnExportTxt.addEventListener("click", async () => {
    const text = (sttText.value || "").trim();
    if (!text) {
      setStatus(sttStatus, "沒有可匯出的文字", false);
      return;
    }
    setStatus(sttStatus, "匯出 TXT…");
    try {
      const resp = await fetch(apiurlFn("tts/export_txt/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      const blob = await resp.blob();
      downloadBlob(blob, "stt.txt");
      setStatus(sttStatus, "已下載 stt.txt ✅");
    } catch (e) {
      setStatus(sttStatus, "匯出失敗：" + (e?.message || String(e)), false);
    }
  });

  btnExportDocx.addEventListener("click", async () => {
    const text = (sttText.value || "").trim();
    if (!text) {
      setStatus(sttStatus, "沒有可匯出的文字", false);
      return;
    }
    setStatus(sttStatus, "匯出 DOCX…");
    try {
      const resp = await fetch(apiurlFn("tts/export_docx/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      const blob = await resp.blob();
      downloadBlob(blob, "stt.docx");
      setStatus(sttStatus, "已下載 stt.docx ✅");
    } catch (e) {
      setStatus(sttStatus, "匯出失敗：" + (e?.message || String(e)), false);
    }
  });

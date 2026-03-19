// webapps/doc/static/doc/js/doc_index_editor.js
// ============================================================
// 【專案規範註解】（Mandatory）
// 1) URL 組合：全專案唯一入口 apiurl_factory() → 只讀 document.body.dataset.baseUrl
// 2) JS 禁止寫死任何 proxy/node 前綴（例如 /djangoai）；禁止使用 window.__PROXY_PREFIX__ 等推導
// 3) Sybase/incoming 初始化需「只做一次」避免重複綁定與互相干擾
// 4) 本檔不得自行綁 DOMContentLoaded（避免重複初始化）；只允許 bootstrap 統一初始化
// 5) 所有 API URL 必須經過 apiurl_factory() 組合（由 bootstrap 注入 NS.api）
// ============================================================

(function () {
  "use strict";

  const NS = (window.DocDocApp = window.DocDocApp || {});
  NS.modules = NS.modules || {};

  const state = {
    __INITED__: false,
    saveModalSource: "reference",
    focusParsedItems: [],
    focusSummaryHeader: "",
  };

  function _ctx() {
    if (!NS || !NS.api || !NS.dom || !NS.utils || !NS.consts) throw new Error("DocDocApp context not ready.");
    return NS;
  }

  // =========================================================
  // ✅ Sybase incoming 初始化：只做一次（全域鎖）
  // - incoming_sybase.js 可能在其他地方也被引用，所以要用全域 lock
  // =========================================================
  function initIncomingSybaseOnce() {
    try {
      if (!window.initIncomingSybase) return;

      // ✅ 一次性鎖：避免同頁重複載入 / 重複綁定事件
      if (window.__DOC_INCOMING_SYBASE_INITED__) return;
      window.__DOC_INCOMING_SYBASE_INITED__ = true;

      const { dom, api } = _ctx();

      window.initIncomingSybase({
        dom,
        api: {
          lookupUrl: api.incoming_lookup,
          filesUrl: api.incoming_files,
          fileUrlPrefix: api.incoming_file_prefix,

          blobStashUrl: api.syb_blob_stash,
          blobDownloadPrefix: api.syb_blob_download_prefix,
        },
      });
    } catch (e) {
      console.error("initIncomingSybase failed:", e);
    }
  }

  // =========================================================
  // clipboard
  // =========================================================
  async function copyTextToClipboard(text, fallbackEl) {
    const t = (text || "").trim();
    if (!t) return false;

    try {
      await navigator.clipboard.writeText(t);
      return true;
    } catch (_e) {
      if (fallbackEl) {
        try {
          fallbackEl.focus();
          fallbackEl.select();
          document.execCommand("copy");
          return true;
        } catch (_e2) {
          return false;
        }
      }
      return false;
    }
  }

  async function copyPrompt() {
    const { dom } = _ctx();
    const ok = await copyTextToClipboard(dom.promptOut ? dom.promptOut.value : "", dom.promptOut);
    alert(ok ? "✅ 已複製 Prompt 到剪貼簿" : "❌ 複製失敗");
  }

  async function copyDraft() {
    const { dom } = _ctx();
    const ok = await copyTextToClipboard(dom.docResult ? dom.docResult.value : "", dom.docResult);
    alert(ok ? "✅ 已複製草稿到剪貼簿" : "❌ 複製失敗");
  }

  // =========================================================
  // download
  // =========================================================
  function downloadTxt(filenamePrefix, content) {
    const text = (content || "").trim();
    if (!text) return alert("沒有內容可下載");

    const withBom = "﻿" + text;
    const blob = new Blob([withBom], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `${filenamePrefix}_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // =========================================================
  // clear
  // =========================================================
  function clearAll() {
    const { dom, utils } = _ctx();
    if (!confirm("確定要清除輸入與輸出？")) return;

    if (dom.requirement) dom.requirement.value = "";
    if (dom.incomingText) dom.incomingText.value = "";
    if (dom.attachmentsText) dom.attachmentsText.value = "";
    if (dom.promptFocusOut) dom.promptFocusOut.value = "";
    if (dom.referenceText) dom.referenceText.value = "";
    if (dom.promptOut) dom.promptOut.value = "";
    if (dom.docResult) dom.docResult.value = "";
    if (dom.genMeta) dom.genMeta.textContent = "";

    document.querySelectorAll(".tplCk").forEach((ck) => (ck.checked = false));
    const templatesMod = NS.modules && NS.modules.templates;
    try {
      if (templatesMod && templatesMod.renderExamplePreview) templatesMod.renderExamplePreview();
    } catch (e) {
      console.warn("renderExamplePreview failed:", e);
    }

    utils.autoGrow(dom.requirement);

    // ✅ Sybase tokens 清空（incoming_sybase.js 會寫入）
    const tokenEl = document.getElementById("sybAttachTokens");
    if (tokenEl) {
      tokenEl.value = "";
      tokenEl.setAttribute("value", "");
    }
    resetFocusPick();
  }

  function clearPromptOnly() {
    const { dom } = _ctx();
    if (dom.promptOut) dom.promptOut.value = "";
  }

  function clearFocusPromptOnly() {
    const { dom } = _ctx();
    if (dom.promptFocusOut) dom.promptFocusOut.value = "";
  }

  function clearDraftOnly() {
    const { dom } = _ctx();
    if (dom.docResult) dom.docResult.value = "";
    if (dom.genMeta) dom.genMeta.textContent = "";
  }

  function resetFocusPick() {
    const { dom } = _ctx();
    state.focusParsedItems = [];
    state.focusSummaryHeader = "";
    if (dom.focusPickWrap) dom.focusPickWrap.style.display = "none";
    if (dom.focusPickList) dom.focusPickList.innerHTML = "";
    if (dom.focusPickHint) dom.focusPickHint.textContent = "";
    // ✅ 新增：清空附件解析文字框與進度顯示
    if (dom.attachmentsText) dom.attachmentsText.value = "";
    if (dom.attachStatus) dom.attachStatus.textContent = "";
    if (dom.promptFocusOut) dom.promptFocusOut.value = "";
  }

  function extractFocusSummaryHeader(text) {
    const lines = String(text || "")
      .split(/\r?\n/)
      .map((x) => String(x || "").trim())
      .filter(Boolean);
    return lines
      .filter((line) => /^(來文單位|受文者|受文單位|來文主旨)\s*[：:]/.test(line))
      .join("\n");
  }

  function parseFocusSummaryItems(text) {
    const lines = String(text || "").split(/\r?\n/);
    const items = [];
    let current = null;
    let seq = 1;

    function stripLeadingOrdinal(v) {
      return String(v || "")
        .replace(/^\s*\d+\s*[\.\、\)）:：]\s*/, "")
        .trim();
    }

    const pushCurrent = () => {
      if (!current) return;
      const body = String((current.lines || []).join("\n")).trim();
      if (!body) {
        current = null;
        return;
      }
      items.push({
        id: `focus_${items.length + 1}`,
        label: current.label || `重點${items.length + 1}`,
        text: body,
        checked: true,
      });
      current = null;
    };

    for (const rawLine of lines) {
      const line = String(rawLine || "").trim();
      if (!line) continue;

      const mDesc = line.match(/^來文說明\s*(\d+)\s*[：:]\s*(.*)$/);
      if (mDesc) {
        pushCurrent();
        current = {
          label: `來文說明${mDesc[1]}`,
          lines: [stripLeadingOrdinal(mDesc[2])].filter(Boolean),
        };
        continue;
      }

      const mIncoming = line.match(/^來文重點\s*(\d+)\s*[：:]\s*(.*)$/);
      if (mIncoming) {
        pushCurrent();
        current = {
          label: `來文重點${mIncoming[1]}`,
          lines: [stripLeadingOrdinal(mIncoming[2])].filter(Boolean),
        };
        continue;
      }

      const mAttach = line.match(/^附件重點\s*(\d+)\s*[：:]\s*(.*)$/);
      if (mAttach) {
        pushCurrent();
        current = {
          label: `附件重點${mAttach[1]}`,
          lines: [stripLeadingOrdinal(mAttach[2])].filter(Boolean),
        };
        continue;
      }

      const m1 = line.match(/^重點\s*(\d+)\s*[：:]\s*(.*)$/);
      if (m1) {
        pushCurrent();
        current = {
          label: `重點${m1[1]}`,
          lines: [stripLeadingOrdinal(m1[2])].filter(Boolean),
        };
        continue;
      }

      const m2 = line.match(/^(\d+)[\.\、]\s*(.*)$/);
      if (m2) {
        pushCurrent();
        current = {
          label: `重點${m2[1]}`,
          lines: [stripLeadingOrdinal(m2[2])].filter(Boolean),
        };
        continue;
      }

      if (current) {
        current.lines.push(stripLeadingOrdinal(line));
      } else {
        if (/^(來文單位|受文者|受文單位|來文主旨)\s*[：:]/.test(line)) continue;
        items.push({
          id: `focus_${items.length + 1}`,
          label: `重點${seq}`,
          text: stripLeadingOrdinal(line),
          checked: true,
        });
        seq += 1;
      }
    }
    pushCurrent();
    return items;
  }

  function selectedFocusItemsText() {
    const picked = (state.focusParsedItems || []).filter((x) => !!x.checked);
    const body = picked
      .map((x) => `${x.label}：${x.text}`.trim())
      .filter(Boolean)
      .join("\n");
    const header = String(state.focusSummaryHeader || "").trim();
    return header ? `${header}\n${body}`.trim() : body;
  }

  function selectedStage2Facts() {
    const picked = (state.focusParsedItems || []).filter((x) => !!x.checked);
    return picked
      .map((x) => String(x && x.text ? x.text : "").trim())
      .map((t) => t.replace(/^(?:重點|來文重點|來文說明|附件重點)\s*\d+\s*[:：]\s*/g, "").trim())
      .filter(Boolean)
      .filter((t) => !/^(擬辦|建議|請示|研處意見)\s*[:：]/.test(t))
      .filter((t) => !/^這是.+（層級|這是.+的[令函呈]/.test(t));
  }

  function syncDocTypeSelectors(nextValue, source) {
    const { dom } = _ctx();
    const v = String(nextValue || "").trim();
    if (!v) return;
    if (source === "right" && dom.docType && dom.docType.value !== v) dom.docType.value = v;
    if (source === "left" && dom.docTypeQuick && dom.docTypeQuick.value !== v) dom.docTypeQuick.value = v;
  }

  function syncFocusPickToTextarea() {
    const { dom } = _ctx();
    const total = (state.focusParsedItems || []).length;
    const picked = (state.focusParsedItems || []).filter((x) => !!x.checked).length;
    const out = selectedFocusItemsText();

    if (dom.attachmentsText) dom.attachmentsText.value = out;
    if (dom.focusPickHint) {
      dom.focusPickHint.textContent =
        total > 0 ? `已勾選 ${picked} / ${total} 項，生成時只納入勾選項目。` : "";
    }
  }

  function renderFocusPickList() {
    const { dom, utils } = _ctx();
    if (!dom.focusPickWrap || !dom.focusPickList) return;

    const items = state.focusParsedItems || [];
    if (!items.length) {
      resetFocusPick();
      return;
    }

    dom.focusPickWrap.style.display = "";
    dom.focusPickList.innerHTML = "";

    items.forEach((it, idx) => {
      const row = document.createElement("label");
      row.className = "focus-pick-item";
      row.innerHTML =
        `<input type="checkbox" class="focusPickCk" data-idx="${idx}" ${it.checked ? "checked" : ""}>` +
        `<span class="focus-pick-text"><b>${utils.escapeHtml(it.label)}：</b> ${utils.escapeHtml(it.text)}</span>`;
      dom.focusPickList.appendChild(row);
    });

    dom.focusPickList.querySelectorAll(".focusPickCk").forEach((ck) => {
      ck.addEventListener("change", (e) => {
        const n = Number.parseInt(e.currentTarget.getAttribute("data-idx"), 10);
        if (!Number.isFinite(n) || !state.focusParsedItems[n]) return;
        state.focusParsedItems[n].checked = !!e.currentTarget.checked;
        syncFocusPickToTextarea();
      });
    });

    syncFocusPickToTextarea();
  }

  function setAllFocusPicked(flag) {
    const { dom } = _ctx();
    if (!state.focusParsedItems.length) return;
    state.focusParsedItems.forEach((x) => {
      x.checked = !!flag;
    });
    if (dom.focusPickList) {
      dom.focusPickList.querySelectorAll(".focusPickCk").forEach((ck) => {
        ck.checked = !!flag;
      });
    }
    syncFocusPickToTextarea();
  }

  // =========================================================
  // attachments parse_focus (支援：本機檔 + Sybase stash tokens)
  // =========================================================
    async function parseAttachments() {
    const { dom, api } = _ctx();

    const files = dom.attachInput ? dom.attachInput.files : null;

    // ✅ 讀取 Sybase stash tokens（確保讀到最新狀態，不使用快取變數）
    const tokenEl = document.getElementById("sybAttachTokens");
    const sybTokens = tokenEl ? String(tokenEl.value || "").trim() : "";

    console.log("[parseAttachments] final tokens to send:", sybTokens);

    const hasUpload = !!(files && files.length > 0);
    const hasSyb = !!sybTokens;

    if (!hasUpload && !hasSyb) {
      const checkedIncoming = document.querySelectorAll(
        '#incomingSybase .incomingAttachCk:checked'
      );
      if (checkedIncoming && checkedIncoming.length > 0) {
        const btnStash = document.getElementById("btnStashIncomingAttachments");
        if (btnStash && !btnStash.disabled) {
          btnStash.click();
          return;
        }
      }
      alert("請先選擇附件檔案，或先勾選來文附件加入收納後再解析");
      return;
    }

    resetFocusPick();
    if (dom.attachStatus) dom.attachStatus.textContent = "⏳ 解析附件重點中...";
    if (dom.attachmentsText) dom.attachmentsText.value = "⏳ 解析附件重點中...";
    if (dom.promptFocusOut) dom.promptFocusOut.value = "⏳ 產生 Prompt 中...";

    try {
      const fd = new FormData();

      if (hasUpload) {
        for (const f of files) fd.append("attachments", f);
      }

      // ✅ 後端支援 syb_tokens / sybAttachTokens 皆可；這裡固定用 syb_tokens
      if (hasSyb) fd.append("syb_tokens", sybTokens);

      // ✅ 額外提示（沿用原行為）：把 promptOut 當 hint
      const extraHint = String(dom.promptOut && dom.promptOut.value ? dom.promptOut.value : "").trim();
      if (extraHint) fd.append("prompt", extraHint);

      const res = await fetch(api.parse_focus, { method: "POST", body: fd });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(`parse_focus api error: ${res.status} ${t}`);
      }

      const data = await res.json();
      const summaryText = String(data.summary_text || "").trim();
      const inferredDocType = String(data && data.inferred && data.inferred.doc_type ? data.inferred.doc_type : "").trim();
      const inferredKind = String(data && data.inferred && data.inferred.doc_kind ? data.inferred.doc_kind : "").trim();
      const inferredOrg = String(data && data.inferred && data.inferred.org ? data.inferred.org : "未辨識機關").trim();
      state.focusSummaryHeader = extractFocusSummaryHeader(summaryText);
      const parsedItems = parseFocusSummaryItems(summaryText);
      if (parsedItems.length > 0) {
        state.focusParsedItems = parsedItems;
        renderFocusPickList();
      } else {
        resetFocusPick();
        if (dom.attachmentsText) dom.attachmentsText.value = summaryText;
      }
      // 文別固定預設為簽呈；不得因來文自動改變文別，避免覆蓋使用者選擇。
      if (dom.promptFocusOut) dom.promptFocusOut.value = data.prompt || "";
      if (dom.attachStatus) {
        const kind = inferredKind || "函";
        dom.attachStatus.textContent = `✅ 重點完成（${(data.files || []).length} 檔）｜來文：${inferredOrg}｜文別：${kind}`;
      }
    } catch (e) {
      console.error(e);
      const msg = e && e.message ? e.message : String(e);
      if (dom.attachStatus) dom.attachStatus.textContent = "❌ 解析失敗";
      if (dom.attachmentsText) dom.attachmentsText.value = "❌ 解析失敗：" + msg;
      if (dom.promptFocusOut) dom.promptFocusOut.value = "";
      resetFocusPick();
    }
  }

  // =========================================================
  // generate doc
  // =========================================================
  async function generateDoc() {
    const { dom, api } = _ctx();
    const templatesMod = NS.modules && NS.modules.templates;

    const docType = dom.docTypeQuick
      ? String(dom.docTypeQuick.value || "").trim()
      : "sign_memo";
    if (dom.docType && dom.docType.value !== (docType || "sign_memo")) {
      dom.docType.value = (docType || "sign_memo");
    }
    const requirement = dom.requirement ? String(dom.requirement.value || "").trim() : "";
    const incomingLevel = dom.incomingLevel ? String(dom.incomingLevel.value || "").trim().toLowerCase() : "";
    const discretion = dom.discretion ? String(dom.discretion.value || "").trim().toLowerCase() : "";
    const risk = dom.risk ? String(dom.risk.value || "").trim().toLowerCase() : "";
    const exampleIds =
      templatesMod && templatesMod.getSelectedExampleIds ? templatesMod.getSelectedExampleIds() : [];

    if (!requirement) {
      alert("請先輸入需求描述！");
      return;
    }

    if (dom.promptOut) dom.promptOut.value = "⏳ 產生中...";
    if (dom.docResult) dom.docResult.value = "⏳ 生成公文中...";
    if (dom.genMeta) dom.genMeta.textContent = "";

    try {
      const res = await fetch(api.generate, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          doc_type: docType,
          requirement: requirement,
          example_ids: exampleIds,
          reference_text: (dom.referenceText && dom.referenceText.value ? dom.referenceText.value : "").trim(),
          incoming_text: (dom.incomingText && dom.incomingText.value ? dom.incomingText.value : "").trim(),
          incoming_level: incomingLevel,
          discretion: discretion,
          risk: risk,
          attachments_text:
            (state.focusParsedItems && state.focusParsedItems.length > 0
              ? selectedFocusItemsText()
              : (dom.attachmentsText && dom.attachmentsText.value ? dom.attachmentsText.value : "")
            ).trim(),
          stage2_facts: selectedStage2Facts(),
          save_as_template: false,
        }),
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`generate api error: ${res.status} ${t}`);
      }

      const data = await res.json();
      if (dom.promptOut) dom.promptOut.value = data.prompt || "";
      if (dom.docResult) dom.docResult.value = data.draft_text || "(未取得 draft_text；請確認後端回傳 draft_text 欄位)";

      const provider = data.provider ? `provider=${data.provider}` : "";
      const model = data.model ? `model=${data.model}` : "";
      const rag = data.rag_backend ? `rag=${data.rag_backend}` : "";
      if (dom.genMeta) dom.genMeta.textContent = [provider, model, rag].filter(Boolean).join("，");
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      if (dom.promptOut) dom.promptOut.value = "❌ 產生失敗：" + msg;
      if (dom.docResult) dom.docResult.value = "❌ 生成失敗：" + msg;
    }
  }

  // =========================================================
  // modal: save as template（用 templates module 的 postTemplate）
  // =========================================================
  function firstSubjectFromText(text) {
    const lines = String(text || "").split(/\r?\n/);
    for (const line of lines) {
      const t = line.trim();
      if (!t) continue;
      const m = t.match(/^主旨[:：]\s*(.+)$/);
      if (m) return m[1].trim();
    }
    return "";
  }

  function inferTagsFromTextFront(text) {
    // ✅ 這裡只推「TAG_GROUPS 既有羣組」；自訂 tags 由使用者輸入
    const t = String(text || "");
    const rules = [
      ["資訊", /系統|資安|弱點|帳號|權限|伺服器|備份|機房|端點|EDR|SOC|告警|監測|MES|IIoT/i],
      ["採購", /採購|招標|詢價|契約|廠商|決標|開標|比價|規格|驗收|開口|框架/i],
      ["主財", /預算|經費|核銷|報支|憑證|請款|撥款|付款|概算|決算/i],
      ["品保", /品質|檢驗|首件|不良|異常|RCA|稽核|改善|報廢/i],
      ["生產", /產線|稼動|排程|產能|備料|出貨|停線|試量產/i],
      ["設施供應", /修繕|空調|電力|消防|水電|工程|設備保養|維護|治具/i],
      ["人事", /人力|招募|派遣|約用|教育訓練|考績/i],
      ["行政", /會議|公告|制度|流程|總務|庶務|文書/i],
      ["研發", /研發|設計|驗證|試驗|專利|新產品/i],
      ["計劃", /計畫|專案|里程碑|年度計畫/i],
      ["職安衛", /職安|工安|環安|安全衛生|危害|風險/i],
      ["測情", /情資|研判|通報|預警|態勢|威脅|事件|告警|監測/i],
    ];
    const out = [];
    for (const [tag, re] of rules) if (re.test(t)) out.push(tag);
    return out.length ? out : ["行政"];
  }

  function modalSetVisible(visible) {
    const { dom } = _ctx();
    if (!dom.saveTplModalOverlay) return;
    dom.saveTplModalOverlay.style.display = visible ? "flex" : "none";
    dom.saveTplModalOverlay.setAttribute("aria-hidden", visible ? "false" : "true");
  }

  function buildTagPills(defaultSelected) {
    const { dom, consts } = _ctx();
    if (!dom.saveTplTagPills) return;
    const selected = Array.isArray(defaultSelected) ? defaultSelected : [];
    dom.saveTplTagPills.innerHTML = "";

    consts.TAG_GROUPS.forEach((tag) => {
      const pill = document.createElement("label");
      pill.className = "tag-pill";

      const ck = document.createElement("input");
      ck.type = "checkbox";
      ck.value = tag;
      ck.checked = selected.includes(tag);

      const text = document.createElement("span");
      text.textContent = tag;

      pill.appendChild(ck);
      pill.appendChild(text);

      function sync() {
        pill.classList.toggle("active", ck.checked);
      }
      ck.addEventListener("change", sync);
      sync();

      dom.saveTplTagPills.appendChild(pill);
    });
  }

  function getModalSelectedTags() {
    const { dom } = _ctx();

    const base = dom.saveTplTagPills
      ? Array.from(dom.saveTplTagPills.querySelectorAll('input[type="checkbox"]:checked'))
          .map((x) => x.value)
          .filter(Boolean)
      : [];

    const customRaw = String(dom.saveTplCustomTags && dom.saveTplCustomTags.value ? dom.saveTplCustomTags.value : "").trim();
    const custom = customRaw ? customRaw.split(";").map((s) => s.trim()).filter(Boolean) : [];

    const out = [];
    const seen = new Set();
    for (const x of [...base, ...custom]) {
      if (!x) continue;
      if (seen.has(x)) continue;
      seen.add(x);
      out.push(x);
    }
    return out;
  }

  function openSaveModalWithContent(source, contentText) {
    const { dom, consts, utils } = _ctx();

    const docType = dom.docType ? dom.docType.value : "";
    const content = (contentText || "").trim();

    if (!content) {
      alert(source === "draft" ? "草稿內容是空的，無法存為範例。" : "參考前案內容是空的，請先貼上內容再存為範例。");
      return;
    }

    state.saveModalSource = source;

    const subj = firstSubjectFromText(content) || (source === "draft" ? "草稿" : "前案參考");
    const suggestedTitle = `${consts.DOC_TYPE_LABEL[docType] || docType}—${subj.replace(/[。．\.]+$/, "")}範例`;

    const inferred = utils.mapTagsToGroups(inferTagsFromTextFront(content));
    const suggestedDesc = inferred.length
      ? `${inferred.slice(0, 4).join(" / ")} / ${source === "draft" ? "草稿" : "前案參考"}`
      : source === "draft"
      ? "草稿"
      : "前案參考";

    if (dom.saveTplModalSub) dom.saveTplModalSub.textContent = `doc_type：${consts.DOC_TYPE_LABEL[docType] || docType}（存入範例庫）`;
    if (dom.saveTplTitle) dom.saveTplTitle.value = suggestedTitle;
    if (dom.saveTplDesc) dom.saveTplDesc.value = suggestedDesc;

    if (dom.saveTplScope) dom.saveTplScope.value = "personal";
    if (dom.saveTplConflict) dom.saveTplConflict.value = "suffix";

    if (dom.saveTplCustomTags) dom.saveTplCustomTags.value = "";
    if (dom.saveTplContentPreview) dom.saveTplContentPreview.value = utils.normalizeContentText(content);

    buildTagPills(inferred);

    if (dom.saveTplHint) dom.saveTplHint.textContent = "提示：tags 可多選；也可在「自訂 tags」輸入（分號 ; 分隔）。";
    modalSetVisible(true);

    setTimeout(() => {
      if (dom.saveTplTitle) dom.saveTplTitle.focus();
    }, 30);
  }

  function openSaveReferenceModal() {
    const { dom } = _ctx();
    openSaveModalWithContent("reference", dom.referenceText ? dom.referenceText.value : "");
  }

  function openSaveDraftModal() {
    const { dom } = _ctx();
    openSaveModalWithContent("draft", dom.docResult ? dom.docResult.value : "");
  }

  function closeSaveModal() {
    modalSetVisible(false);
  }

  async function confirmSaveAsTemplate() {
    const { dom, utils } = _ctx();

    // ---- doc type (left/right selector sync) ----
    if (dom.docType) dom.docType.value = "sign_memo";
    if (dom.docTypeQuick) dom.docTypeQuick.value = "sign_memo";
    syncDocTypeSelectors("sign_memo", "init");
    // 左側「創案公文選製」文別僅供範例過濾，不回寫右側生成文別。
    if (dom.docTypeQuick) {
      dom.docTypeQuick.addEventListener("change", () => {
        syncDocTypeSelectors(dom.docTypeQuick.value, "right");
      });
    }
    const templatesMod = NS.modules && NS.modules.templates;

    if (!templatesMod || !templatesMod.postTemplate) {
      alert("❌ templates module 未載入，無法儲存範例。");
      return;
    }

    const docType = dom.docType ? dom.docType.value : "";
    const content = (dom.saveTplContentPreview && dom.saveTplContentPreview.value ? dom.saveTplContentPreview.value : "").trim();
    if (!content) return alert("內容空白，無法儲存。");

    const title = (dom.saveTplTitle && dom.saveTplTitle.value ? dom.saveTplTitle.value : "").trim();
    if (!title) return alert("請輸入標題（title）。");

    const tags = getModalSelectedTags();
    const description =
      (dom.saveTplDesc && dom.saveTplDesc.value ? dom.saveTplDesc.value : "").trim() ||
      (tags.length
        ? `${tags.slice(0, 4).join(" / ")} / ${state.saveModalSource === "draft" ? "草稿" : "前案參考"}`
        : state.saveModalSource === "draft"
        ? "草稿"
        : "前案參考");

    const scope = String(dom.saveTplScope && dom.saveTplScope.value ? dom.saveTplScope.value : "personal").trim();
    const on_conflict = String(dom.saveTplConflict && dom.saveTplConflict.value ? dom.saveTplConflict.value : "suffix").trim();

    try {
      if (dom.btnConfirmSaveTpl) {
        dom.btnConfirmSaveTpl.disabled = true;
        dom.btnConfirmSaveTpl.textContent = "儲存中...";
      }

      await templatesMod.postTemplate({
        title,
        doc_type: docType,
        tags,
        description,
        content_text: utils.normalizeContentText(content),
        scope,
        on_conflict,
      });

      closeSaveModal();
      alert("✅ 已存入範例庫");

      // ✅ 重新載入由 templates module 負責
      if (templatesMod.loadTemplates) await templatesMod.loadTemplates();
    } catch (err) {
      console.error(err);
      const msg = err && err.message ? err.message : String(err);
      alert("❌ 儲存失敗：" + msg);
    } finally {
      if (dom.btnConfirmSaveTpl) {
        dom.btnConfirmSaveTpl.disabled = false;
        dom.btnConfirmSaveTpl.textContent = "儲存為範例";
      }
    }
  }

  // =========================================================
  // init (only called by bootstrap)
  // =========================================================
  function init(appCtx) {
    // ✅ 本 module 不綁 DOMContentLoaded；只由 bootstrap 呼叫
    void appCtx;

    if (state.__INITED__) return;
    state.__INITED__ = true;

    const { dom, utils } = _ctx();

    // 防止快取版本不一致或例外中斷導致遮罩殘留，初始化時一律先關閉。
    if (dom.saveTplModalOverlay) {
      dom.saveTplModalOverlay.style.display = "none";
      dom.saveTplModalOverlay.setAttribute("aria-hidden", "true");
    }

    // ---- buttons ----
    if (dom.btnGenerate) dom.btnGenerate.addEventListener("click", generateDoc);

    if (dom.btnCopyPrompt) dom.btnCopyPrompt.addEventListener("click", copyPrompt);
    if (dom.btnCopyDraft) dom.btnCopyDraft.addEventListener("click", copyDraft);

    if (dom.btnClearAll) dom.btnClearAll.addEventListener("click", clearAll);
    if (dom.btnClearPrompt) dom.btnClearPrompt.addEventListener("click", clearPromptOnly);
    if (dom.btnClearFocusPrompt) dom.btnClearFocusPrompt.addEventListener("click", clearFocusPromptOnly);
    if (dom.btnClearDraft) dom.btnClearDraft.addEventListener("click", clearDraftOnly);

    if (dom.btnDownloadPromptTxt)
      dom.btnDownloadPromptTxt.addEventListener("click", () => downloadTxt("公文Prompt", dom.promptOut ? dom.promptOut.value : ""));
    if (dom.btnDownloadFocusPromptTxt)
      dom.btnDownloadFocusPromptTxt.addEventListener("click", () => downloadTxt("重點解析Prompt", dom.promptFocusOut ? dom.promptFocusOut.value : ""));
    if (dom.btnDownloadDraftTxt)
      dom.btnDownloadDraftTxt.addEventListener("click", () => downloadTxt("公文草稿", dom.docResult ? dom.docResult.value : ""));

    if (dom.btnParseAttach) dom.btnParseAttach.addEventListener("click", parseAttachments);
    if (dom.btnFocusPickAll) dom.btnFocusPickAll.addEventListener("click", () => setAllFocusPicked(true));
    if (dom.btnFocusPickNone) dom.btnFocusPickNone.addEventListener("click", () => setAllFocusPicked(false));

    // ---- autogrow ----
    utils.autoGrow(dom.requirement);
    if (dom.requirement) dom.requirement.addEventListener("input", () => utils.autoGrow(dom.requirement));

    // ---- save modal ----
    if (dom.btnSaveReferenceAsTemplate) dom.btnSaveReferenceAsTemplate.addEventListener("click", openSaveReferenceModal);
    if (dom.btnSaveDraftAsTemplate) dom.btnSaveDraftAsTemplate.addEventListener("click", openSaveDraftModal);

    if (dom.btnCloseSaveTplModal) dom.btnCloseSaveTplModal.addEventListener("click", closeSaveModal);
    if (dom.btnCancelSaveTpl) dom.btnCancelSaveTpl.addEventListener("click", closeSaveModal);
    if (dom.btnConfirmSaveTpl) dom.btnConfirmSaveTpl.addEventListener("click", confirmSaveAsTemplate);

    if (dom.saveTplModalOverlay) {
      dom.saveTplModalOverlay.addEventListener("click", (e) => {
        if (e.target === dom.saveTplModalOverlay) closeSaveModal();
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && dom.saveTplModalOverlay && dom.saveTplModalOverlay.style.display === "flex") {
        closeSaveModal();
      }
    });

    // ✅ Sybase incoming 初始化（只做一次）
    initIncomingSybaseOnce();
  }

  // 對外提供（bootstrap 會呼叫）
  NS.modules.editor = {
    init,
    resetFocusPick, // ✅ 暴露給其他模組（如 incoming_sybase）
    // 也提供給其他模組/除錯用
    initIncomingSybaseOnce,
    parseAttachments,
    generateDoc,
    openSaveReferenceModal,
    openSaveDraftModal,
  };
})();

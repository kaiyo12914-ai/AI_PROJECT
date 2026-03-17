// webapps/doc/static/doc/js/doc_index_bootstrap.js
// ============================================================
// 重要說明（必讀）
// 1) URL 組裝必須經由 apiurl_factory() 且依據 document.body.dataset.baseUrl
// 2) 反向代理前綴由 Django 注入（例如 /djangoai）
// 3) Sybase/incoming 相關 DOM 由 partial 產生，需確保 selector 正確
// 4) API URL 由 apiurl_factory() 統一組合，避免 proxy 路徑錯誤
// 5) DOMContentLoaded 後才可取得必要節點
// ============================================================

(function () {
  "use strict";

  // =========================================================
  // ✅ 全專案共用：apiurl_factory（由 portal/js/apiurl_factory.js 提供）
  // - 只讀 document.body.dataset.baseUrl (= request.script_name)
  // - 規範：不得自行推導 proxy prefix
  // =========================================================
  const apiurl_factory =
    window.apiurl_factory ||
    function (path) {
      const base = String((document.body && document.body.dataset && document.body.dataset.baseUrl) || "").trim();
      let p = String(path || "");
      if (p && p.charAt(0) !== "/") p = "/" + p;
      return base + p;
    };

  // =========================================================
  // ✅ 全域命名空間（避免污染 window）
  // =========================================================
  const NS = (window.DocDocApp = window.DocDocApp || {});
  NS.modules = NS.modules || {};
  NS.utils = NS.utils || {};

  // =========================================================
  // ✅ constants / shared utils（供 modules 使用）
  // =========================================================
  const DOC_TYPE_LABEL = {
  sign_memo: "簽呈",
  order_draft: "令",
  submit_draft: "呈",
  letter_draft: "函",
  note: "便簽",
};

  const TAG_GROUPS = [
  "資訊",
  "採購",
  "主財",
  "品保",
  "生產",
  "設施供應",
  "人事",
  "行政",
  "研發",
  "計劃",
  "職安衛",
  "測情",
];

const TAG_RULES = [
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

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function normalizeContentText(s) {
  let t = String(s || "");
  // Remove repeated ASCII question marks from legacy mojibake text.
  t = t.replace(/[?？]{2,}/g, "").replace(/�/g, "").trim();
  t = t.replace(/[:：]\s*$/, "");
  const pairs = [
    [/SLA/gi, "服務水準協議"],
    [/SOP/gi, "標準作業程序"],
    [/OEE/gi, "設備綜合效率"],
    [/MTTR/gi, "平均修復時間"],
    [/POC/gi, "概念驗證"],
    [/EDR/gi, "端點偵測回應"],
    [/MES/gi, "製造執行系統"],
    [/IIoT/gi, "工業物聯網"],
    [/SOC/gi, "資安監控中心"],
  ];
  for (const [re, rep] of pairs) t = t.replace(re, rep);
  return t;
}

  function mapTagsToGroups(tags) {
  const raw = (tags || [])
    .map((x) => String(x || "").trim())
    .filter(Boolean);

  const out = new Set();

  for (const tag of raw) {
    if (TAG_GROUPS.includes(tag)) {
      out.add(tag);
      continue;
    }
    for (const [group, re] of TAG_RULES) {
      if (re.test(tag)) {
        out.add(group);
        break;
      }
    }
  }

  if (out.size === 0 && raw.length) out.add("行政");
  return Array.from(out);
}

  function autoGrow(el) {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  // =========================================================
  // ✅ API endpoints（必須全部走 apiurl_factory）
  // ✅ 規範重點：baseUrl = request.script_name（例如 /doc 或 /comment/doc）
  //    所以這裡「不可再加 doc/」避免變成 /doc/doc/api/... 或 /comment/doc/doc/api/...
  // =========================================================
  const api = {
    // core
    templates: apiurl_factory("api/templates/"),
    generate: apiurl_factory("api/generate/"),
    draft_reply: apiurl_factory("api/draft_reply/"),
    parse: apiurl_factory("api/parse/"),
    parse_focus: apiurl_factory("api/parse_focus/"),

    // pages
    templates_manage: apiurl_factory("templates/"),

    // sybase template import（轉入範例） -> 這個是 doc 主系統功能，走 apiurl_factory OK
    syb_template_import: apiurl_factory("api/sybase/template/import/"),
    syb_import_file_template: apiurl_factory("api/sybase/import/file/__KEY__/"),
  };

  // =========================================================
  // ✅ DOM references（集中在 bootstrap 建立）
  // - 規範：incoming_sybase widget 內部 DOM 不做全域綁定（避免誤綁/重複綁定）
  // =========================================================
  function buildDomRefs() {
    return {
      docType: document.getElementById("docType"),
      docTypeQuick: document.getElementById("docTypeQuick"),
      tplScope: document.getElementById("tplScope"),
      tagFilter: document.getElementById("tagFilter"),
      tplList: document.getElementById("tplList"),
      requirement: document.getElementById("requirement"),

      incomingText: document.getElementById("incomingText"),
      incomingLevel: document.getElementById("incomingLevel"),
      discretion: document.getElementById("discretion"),
      risk: document.getElementById("risk"),
      attachmentsText: document.getElementById("attachmentsText"),
      promptFocusOut: document.getElementById("promptFocusOut"),
      referenceText: document.getElementById("referenceText"),

      promptOut: document.getElementById("promptOut"),
      docResult: document.getElementById("docResult"),
      examplePreview: document.getElementById("examplePreview"),
      genMeta: document.getElementById("genMeta"),

      btnReloadTemplates: document.getElementById("btnReloadTemplates"),
      btnGenerate: document.getElementById("btnGenerate"),
      btnCopyPrompt: document.getElementById("btnCopyPrompt"),
      btnCopyDraft: document.getElementById("btnCopyDraft"),
      btnClearAll: document.getElementById("btnClearAll"),

      btnClearPrompt: document.getElementById("btnClearPrompt"),
      btnClearFocusPrompt: document.getElementById("btnClearFocusPrompt"),
      btnClearDraft: document.getElementById("btnClearDraft"),
      btnDownloadPromptTxt: document.getElementById("btnDownloadPromptTxt"),
      btnDownloadFocusPromptTxt: document.getElementById("btnDownloadFocusPromptTxt"),
      btnDownloadDraftTxt: document.getElementById("btnDownloadDraftTxt"),

      btnSaveDraftAsTemplate: document.getElementById("btnSaveDraftAsTemplate"),

      importTplFileInput: document.getElementById("importTplFileInput"),
      btnImportTplFile: document.getElementById("btnImportTplFile"),

      // sybase template import（轉入範例）
      sybImportGrsno: document.getElementById("sybImportGrsno"),
      btnImportTplFromSybase: document.getElementById("btnImportTplFromSybase"),
      btnImportTplSelected: document.getElementById("btnImportTplSelected"),
      sybImportList: document.getElementById("sybImportList"),
      sybImportSummary: document.getElementById("sybImportSummary"),
      sybImportPreview: document.getElementById("sybImportPreview"),
      sybImportScope: document.getElementById("sybImportScope"),
      sybImportTag: document.getElementById("sybImportTag"),

      attachInput: document.getElementById("attachInput"),
      btnParseAttach: document.getElementById("btnParseAttach"),
      attachStatus: document.getElementById("attachStatus"),
      focusPickWrap: document.getElementById("focusPickWrap"),
      focusPickList: document.getElementById("focusPickList"),
      focusPickHint: document.getElementById("focusPickHint"),
      btnFocusPickAll: document.getElementById("btnFocusPickAll"),
      btnFocusPickNone: document.getElementById("btnFocusPickNone"),

      exampleHint: document.getElementById("exampleHint"),
      btnExportTplJson: document.getElementById("btnExportTplJson"),
      btnExportTplCsv: document.getElementById("btnExportTplCsv"),
      btnExportTplTxt: document.getElementById("btnExportTplTxt"),
      btnOpenSybImport: document.getElementById("btnOpenSybImport"),

      btnSaveReferenceAsTemplate: document.getElementById("btnSaveReferenceAsTemplate"),

      saveTplModalOverlay: document.getElementById("saveTplModalOverlay"),
      btnCloseSaveTplModal: document.getElementById("btnCloseSaveTplModal"),
      btnCancelSaveTpl: document.getElementById("btnCancelSaveTpl"),
      btnConfirmSaveTpl: document.getElementById("btnConfirmSaveTpl"),
      saveTplTitle: document.getElementById("saveTplTitle"),
      saveTplDesc: document.getElementById("saveTplDesc"),
      saveTplScope: document.getElementById("saveTplScope"),
      saveTplConflict: document.getElementById("saveTplConflict"),
      saveTplTagPills: document.getElementById("saveTplTagPills"),
      saveTplCustomTags: document.getElementById("saveTplCustomTags"),
      saveTplContentPreview: document.getElementById("saveTplContentPreview"),
      saveTplHint: document.getElementById("saveTplHint"),
      saveTplModalSub: document.getElementById("saveTplModalSub"),

      // incoming_sybase root（唯一需要的 widget DOM）
      incomingSybaseRoot: document.querySelector('#incomingSybase[data-module="incomingSybase"]'),

      // token field（在 partial；incoming_sybase.js 會讀）
      sybAttachTokens: document.getElementById("sybAttachTokens"),
    };
  }

  // =========================================================
  // ✅ 注入共享到 NS（modules 只讀這裡）
  // =========================================================
  NS.api = api;
  NS.consts = { DOC_TYPE_LABEL, TAG_GROUPS };
  NS.utils.escapeHtml = escapeHtml;
  NS.utils.normalizeContentText = normalizeContentText;
  NS.utils.mapTagsToGroups = mapTagsToGroups;
  NS.utils.autoGrow = autoGrow;

  // =========================================================
  // ✅ incoming_sybase init（規範：只做一次；端點由 template data-* 注入）
  // =========================================================
  function initIncomingSybaseOnce(dom) {
    if (NS.__INCOMING_SYBASE_INITED__) return;
    NS.__INCOMING_SYBASE_INITED__ = true;

    const root = dom && dom.incomingSybaseRoot;
    if (!root) {
      // fail-open：頁面可能未 include partial
      console.warn("[doc] incomingSybase root not found; skip init.");
      return;
    }

    if (typeof window.initIncomingSybase !== "function") {
      console.warn("[doc] window.initIncomingSybase missing; skip init.");
      return;
    }

    // 規範：端點由 template data-* 注入，bootstrap 只負責讀取並注入
    const ds = root.dataset || {};
    window.initIncomingSybase({
      dom: { root: root },
      api: {
        lookupUrl: ds.lookupUrl || "",
        filesUrl: ds.filesUrl || "",
        fileUrlTemplate: ds.fileUrlTemplate || "",
        blobStashUrl: ds.blobStashUrl || "",
        blobDownloadTemplate: ds.blobDownloadTemplate || "",
        todoUrl: ds.todoUrl || "",
      },
    });
  }

  // =========================================================
  // ✅ Bootstrap：本頁唯一初始化入口（只做一次）
  // =========================================================
  function bootstrapOnce() {
    if (NS.__BOOTSTRAP_INITED__) return;
    NS.__BOOTSTRAP_INITED__ = true;

    const dom = buildDomRefs();
    NS.dom = dom;

    const templatesMod = NS.modules && NS.modules.templates;
    const editorMod = NS.modules && NS.modules.editor;

    if (!templatesMod || !templatesMod.init) console.warn("[doc] templates module missing.");
    if (!editorMod || !editorMod.init) console.warn("[doc] editor module missing.");

    // 1) init modules（不互相綁 DOMContentLoaded）
    try {
      if (templatesMod && templatesMod.init) templatesMod.init(NS);
    } catch (e) {
      console.error("templates.init failed:", e);
    }

    try {
      if (editorMod && editorMod.init) editorMod.init(NS);
    } catch (e) {
      console.error("editor.init failed:", e);
    }

    // 2) init incoming_sybase（只一次；不阻擋主流程）
    try {
      initIncomingSybaseOnce(dom);
    } catch (e) {
      console.error("initIncomingSybaseOnce failed:", e);
    }

    // 3) 初次載入由 templates module 負責
    try {
      if (templatesMod && templatesMod.loadTemplates) templatesMod.loadTemplates();
    } catch (e) {
      console.error("loadTemplates failed:", e);
    }

    try {
      if (dom.btnOpenSybImport) {
        dom.btnOpenSybImport.addEventListener("click", () => {
          const url = api.templates_manage || apiurl_factory("templates/");
          // ensure aaa is appended when opening a new tab
          const finalUrl = (typeof window.apiurl === "function") ? window.apiurl(url) : url;
          window.open(finalUrl, "_blank", "noopener");
        });
      }
    } catch (e) {
      console.error("bind btnOpenSybImport failed:", e);
    }

    // 4) optional：autoGrow（避免初始高度很小）
    try {
      autoGrow(dom.incomingText);
      autoGrow(dom.attachmentsText);
      autoGrow(dom.promptFocusOut);
      autoGrow(dom.referenceText);
      autoGrow(dom.requirement);
      autoGrow(dom.docResult);
      autoGrow(dom.promptOut);
    } catch (e) {
      // fail-open
    }
  }

  // ✅ 全頁唯一 DOMContentLoaded（避免互相干擾）
  window.addEventListener("DOMContentLoaded", bootstrapOnce);
})();

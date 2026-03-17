// webapps/doc/static/doc/js/incoming_sybase.js
// ============================================================
// 規範重點（Mandatory）
// 1) 端點一律由 template data-* 注入，前端不可自行推導 prefix
// 2) API URL 只做 placeholder 置換（__KEY__/__TOKEN__），不推導路由
// 3) partial 內不得自行初始化或重複載入
// ============================================================

(function () {
  "use strict";

  // =========================
  // util
  // =========================
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function setStatus(el, msg, isErr) {
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("is-error", !!isErr);
  }

  function _asStr(x) {
    return String(x == null ? "" : x).trim();
  }

  function _pick(obj, keys, defVal) {
    obj = obj || {};
    for (var i = 0; i < keys.length; i++) {
      var k = keys[i];
      if (obj[k] != null && String(obj[k]).trim() !== "") return obj[k];
    }
    return defVal;
  }

  function _rootQuery(root, selector) {
    if (!root) return null;
    return root.querySelector(selector);
  }

  function _normSortText(v) {
    return String(v == null ? "" : v)
      .replace(/[\s　，,。．\.、:：;；\-_/]/g, "")
      .trim();
  }

  function _isCjkHead(v) {
    var t = String(v == null ? "" : v).trim();
    if (!t) return 1;
    return /^[\u4e00-\u9fff]/.test(t) ? 0 : 1;
  }

  function _hasCjk(v) {
    var t = String(v == null ? "" : v);
    return /[\u4e00-\u9fff]/.test(t) ? 0 : 1;
  }

  function _pinTodoRank(row) {
    var subj = _normSortText(_pick(row, ["subject", "TD_SUBJ", "td_subj"], ""));
    var grsno = _normSortText(_pick(row, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], ""));
    var kw = _normSortText("令發國防部通電資通報11500001號乙則");
    if (grsno === "1150002515") return 0;
    if (kw && subj.indexOf(kw) >= 0) return 0;
    return 1;
  }

  function _todoSortRows(rows) {
    var arr = Array.isArray(rows) ? rows.slice() : [];
    arr.sort(function (a, b) {
      var pa = _pinTodoRank(a);
      var pb = _pinTodoRank(b);
      if (pa !== pb) return pa - pb;

      var sa = String(_pick(a, ["subject", "TD_SUBJ", "td_subj"], ""));
      var sb = String(_pick(b, ["subject", "TD_SUBJ", "td_subj"], ""));
      var ca = _isCjkHead(sa);
      var cb = _isCjkHead(sb);
      if (ca !== cb) return ca - cb;

      var ga = String(_pick(a, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], "")).trim();
      var gb = String(_pick(b, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], "")).trim();
      var na = parseInt(ga, 10);
      var nb = parseInt(gb, 10);
      if (!isNaN(na) && !isNaN(nb) && na !== nb) return nb - na;

      var nsa = _normSortText(sa);
      var nsb = _normSortText(sb);
      if (nsa < nsb) return -1;
      if (nsa > nsb) return 1;
      return 0;
    });
    return arr;
  }

  function _sortAttachRows(rows) {
    var arr = Array.isArray(rows) ? rows.slice() : [];
    arr.sort(function (a, b) {
      var na = _asStr(_pick(a, ["filename", "name", "EF_NAME"], ""));
      var nb = _asStr(_pick(b, ["filename", "name", "EF_NAME"], ""));
      var ca = _hasCjk(na);
      var cb = _hasCjk(nb);
      if (ca !== cb) return ca - cb; // 只要含中文即優先

      var pa = parseInt(_asStr(_pick(a, ["page", "EF_PAGE", "ef_page"], "")), 10);
      var pb = parseInt(_asStr(_pick(b, ["page", "EF_PAGE", "ef_page"], "")), 10);
      if (!isNaN(pa) && !isNaN(pb) && pa !== pb) return pa - pb;

      var sa = _normSortText(na);
      var sb = _normSortText(nb);
      if (sa < sb) return -1;
      if (sa > sb) return 1;
      return 0;
    });
    return arr;
  }

  function _findPinnedTodoIndex(rows) {
    var arr = Array.isArray(rows) ? rows : [];
    for (var i = 0; i < arr.length; i++) {
      if (_pinTodoRank(arr[i]) === 0) return i;
    }
    return -1;
  }

  // only allow placeholder replacement on injected templates
  function _tplReplace(tpl, placeholder, value) {
    var s = String(tpl || "").trim();
    if (!s) return "";
    var p = String(placeholder || "").trim();
    if (!p) return s;
    return s.split(p).join(String(value == null ? "" : value));
  }

  // ============================================================
  // tokens storage (MUST exist in template; do not auto-create)
  // ============================================================
  function _getHiddenTokensEl() {
    var el = document.getElementById("sybAttachTokens");
    if (!el) {
      console.warn(
        "[incoming_sybase] #sybAttachTokens missing. Please add <input type='hidden' id='sybAttachTokens'> in template."
      );
      return null;
    }
    return el;
  }

  function _parseTokens(raw) {
    var s = String(raw || "").trim();
    if (!s) return [];
    var out = [];
    var seen = new Set();
    s.split(",")
      .map(function (x) {
        return x.trim();
      })
      .filter(Boolean)
      .forEach(function (t) {
        if (seen.has(t)) return;
        seen.add(t);
        out.push(t);
      });
    return out;
  }

    function _writeTokens(nextTokens) {
      var el = _getHiddenTokensEl();
      if (!el) return;

      var uniq = [];
      var seen = new Set();
      (nextTokens || []).forEach(function (t) {
        var x = String(t || "").trim();
        if (!x) return;
        if (seen.has(x)) return;
        seen.add(x);
        uniq.push(x);
      });
      el.value = uniq.join(",");
      // ✅ 物理同步：確保 input 與 DOM value 100% 一致
      el.setAttribute("value", el.value);
    }

  // ============================================================
  // encoding policy (path segment)
  // ============================================================
  function _encodePathSeg(v) {
    return encodeURIComponent(String(v == null ? "" : v).trim());
  }

  // ============================================================
  // aaa passthrough for links (download links are <a href>)
  // ============================================================
  function _withAaa(url) {
    if (!url) return url;

    // prefer global apiurl helper if available
    if (typeof window.apiurl === "function") return window.apiurl(url);

    var aaa = "";
    try {
      aaa =
        (typeof window.getAaa === "function" && window.getAaa()) ||
        new URLSearchParams(window.location.search).get("aaa") ||
        "";
    } catch (e) {
      // ignore
    }
    if (!aaa) {
      try {
        aaa = window.localStorage.getItem("aaa") || "";
      } catch (e) {
        // ignore
      }
    }
    if (!aaa) return url;

    try {
      var u = new URL(url, window.location.origin);
      if (u.origin !== window.location.origin) return url;
      if (!u.searchParams.get("aaa")) u.searchParams.set("aaa", aaa);
      return u.pathname + u.search + u.hash;
    } catch (e) {
      if (String(url).includes("aaa=")) return String(url);
      return String(url).includes("?")
        ? url + "&aaa=" + encodeURIComponent(aaa)
        : url + "?aaa=" + encodeURIComponent(aaa);
    }
  }

  // ============================================================
  // Public API: called by bootstrap
  // window.initIncomingSybase({ dom, api })
  // ============================================================
  window.initIncomingSybase = function initIncomingSybase(cfg) {
    cfg = cfg || {};
    var dom = cfg.dom || {};
    var api = cfg.api || {};

    var root = dom.root || null;
    if (!root) {
      console.warn("[incoming_sybase] missing cfg.dom.root; init aborted.");
      return;
    }

    // per-root init guard
    if (root.dataset && root.dataset.initedIncomingSybase === "1") return;
    if (root.dataset) root.dataset.initedIncomingSybase = "1";

    // endpoints must be injected; do not derive
    var lookupUrl = _asStr(api.lookupUrl);
    var filesUrl = _asStr(api.filesUrl);
    var fileUrlTemplate = _asStr(api.fileUrlTemplate || "");
    var blobStashUrl = _asStr(api.blobStashUrl);
    var blobDownloadTemplate = _asStr(api.blobDownloadTemplate || "");
    var todoUrl = _asStr(api.todoUrl);

    if (!lookupUrl) console.warn("[incoming_sybase] missing lookupUrl");
    if (!filesUrl) console.warn("[incoming_sybase] missing filesUrl");
    if (!blobStashUrl) console.warn("[incoming_sybase] missing blobStashUrl");
    if (!fileUrlTemplate) console.warn("[incoming_sybase] missing fileUrlTemplate");
    if (!blobDownloadTemplate) console.warn("[incoming_sybase] missing blobDownloadTemplate");
    if (!todoUrl) console.warn("[incoming_sybase] missing todoUrl");

    // DOM refs (SCOPED inside root)
    var elGrsno = dom.qEmGrsno || _rootQuery(root, "#qEmGrsno");
    var elBtnLookup = dom.btnLookupIncoming || _rootQuery(root, "#btnLookupIncoming");
    var elStatus = dom.incomingLookupStatus || _rootQuery(root, "#incomingLookupStatus");
    var elPick = dom.incomingPick || _rootQuery(root, "#incomingPick");
    var elTodoPick = _rootQuery(root, "#todoPick");
    var elTodoStatus = _rootQuery(root, "#todoStatus");
    var elTodoFilter = _rootQuery(root, "#qTodoFilter");
    var btnTodoLoad = _rootQuery(root, "#btnTodoLoad");
    var btnTodoUse = _rootQuery(root, "#btnTodoUse");

    var elAttachBox = dom.incomingAttachBox || _rootQuery(root, "#incomingAttachBox");
    var elAttachList = dom.incomingAttachList || _rootQuery(root, "#incomingAttachList");
    var btnStash = _rootQuery(root, "#btnStashIncomingAttachments");

    // state
    var _lookupRows = [];
    var _busyLookup = false;
    var _busyFiles = false;
    var _busyStash = false;
    var _todoRows = [];
    var _busyTodo = false;
    var _activeGrsno = "";

    // URL builders (ONLY placeholder replacement on injected template)
    function _buildFileUrl(attachKey, hintName) {
      if (!fileUrlTemplate) return "";
      var key = _encodePathSeg(attachKey);
      var u = _withAaa(_tplReplace(fileUrlTemplate, "__KEY__", key));
      var h = _asStr(hintName);
      if (h) {
        u += (u.indexOf("?") >= 0 ? "&" : "?") + "hint_name=" + encodeURIComponent(h);
      }
      return u;
    }

    function _normalizeAttachKey(raw) {
      var k = _asStr(raw);
      if (!k) return "";
      if (k.indexOf("EF:") === 0 || k.indexOf("DF:") === 0) return k;
      return "EF:" + k;
    }

    function _isAttachKeySafe(raw) {
      var k = _normalizeAttachKey(raw);
      if (!k) return false;
      if (k.length > 200) return false;
      if (/[\r\n\t]/.test(k)) return false;
      if (k.indexOf("%PDF") >= 0 || k.indexOf("stream") >= 0) return false;
      if (/^EF:[^@]+(@\d{1,6})?$/.test(k)) return true;
      if (/^DF:[A-Za-z0-9._\-\/]{1,200}$/.test(k)) return true;
      if (/^DF:[A-Za-z0-9_-]{1,300}$/.test(k)) return true;
      return false;
    }

    function _buildBlobDownloadUrl(token) {
      if (!blobDownloadTemplate) return "";
      var t = _encodePathSeg(token);
      return _withAaa(_tplReplace(blobDownloadTemplate, "__TOKEN__", t));
    }

    function _setAttachBoxVisible(flag) {
      if (!elAttachBox) return;
      elAttachBox.style.display = flag ? "" : "none";
    }

    function _clearStashedTokens() {
      _writeTokens([]);
    }

    function _clearEditorContextHard() {
      // Clear parse/generate artifacts to avoid cross-todo contamination.
      var idsToClear = [
        "incomingText",
        "attachmentsText",
        "promptFocusOut",
        "promptOut",
        "docResult",
        "referenceText",
      ];
      idsToClear.forEach(function (id) {
        var el = document.getElementById(id);
        if (el && "value" in el) el.value = "";
      });

      var metaEl = document.getElementById("genMeta");
      if (metaEl) metaEl.textContent = "";

      try {
        if (window.DocDocApp && window.DocDocApp.modules && window.DocDocApp.modules.editor) {
          if (typeof window.DocDocApp.modules.editor.resetFocusPick === "function") {
            window.DocDocApp.modules.editor.resetFocusPick();
          }
        }
      } catch (e) {
        console.warn("resetFocusPick failed:", e);
      }
    }

    function renderTodoOptions(rows) {
      if (!elTodoPick) return;
      elTodoPick.innerHTML = "";

      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "（請選擇）";
      elTodoPick.appendChild(opt0);

      (rows || []).forEach(function (r, idx) {
        var opt = document.createElement("option");
        opt.value = String(idx);

        var grsno = _asStr(_pick(r, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], ""));
        var subj = _asStr(_pick(r, ["subject", "TD_SUBJ", "td_subj"], ""));
        var fromOrg = _asStr(_pick(r, ["from_org", "FROM_ORG"], ""));
        var docType = _asStr(_pick(r, ["doc_type", "DOC_TYPE"], ""));
        var label = String(idx + 1) + ". " + grsno;
        if (subj) label += "｜" + subj;
        if (fromOrg) label += "｜" + fromOrg;
        if (docType) label += "｜" + docType;
        opt.textContent = label;
        elTodoPick.appendChild(opt);
      });
    }

    // renderers
    function renderPickOptions(rows) {
      if (!elPick) return;
      elPick.innerHTML = "";

      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "（請選擇）";
      elPick.appendChild(opt0);

      (rows || []).forEach(function (r, idx) {
        var opt = document.createElement("option");
        opt.value = String(idx);

        var subj = _asStr(_pick(r, ["subject", "TD_SUBJ", "td_subj"], ""));
        var grsno = _asStr(_pick(r, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], ""));
        var label = String(idx + 1) + ". " + grsno;
        label += "｜" + (subj || "（無主旨）");
        opt.textContent = label;
        elPick.appendChild(opt);
      });
    }

    function renderAttachList(rows) {
      if (!elAttachList) return;
      elAttachList.innerHTML = "";

      if (!rows || !rows.length) {
        elAttachList.innerHTML = '<div class="muted">尚無附件</div>';
        return;
      }

      rows.forEach(function (r, i) {
        var attachKeyRaw = _asStr(
          _pick(r, ["attach_key", "attachKey", "key", "ATTACH_KEY", "EF_ID", "EF_KEY"], "")
        );
        var attachKey = _normalizeAttachKey(attachKeyRaw);
        var keySafe = _isAttachKeySafe(attachKey);
        var name = _asStr(_pick(r, ["filename", "name", "EF_NAME"], "")) ||
          "未命名附件_" + String(i + 1);
        var size = _asStr(_pick(r, ["size", "bytes", "EF_SIZE"], ""));
        var hintName = _asStr(_pick(r, ["raw_filename", "rawName", "hint_name", "filename", "name", "EF_NAME"], ""));

        var href = keySafe ? _buildFileUrl(attachKey, hintName || name) : "";

        var row = document.createElement("div");
        row.className = "incoming-attach-row";

        var sizeHtml = size ? ' <span class="muted">(' + escapeHtml(size) + ")</span>" : "";

        row.innerHTML =
          '<label class="incoming-attach-ck">' +
          '<input type="checkbox" class="incomingAttachCk" value="' +
          escapeHtml(attachKey) +
          '" data-hint-name="' + escapeHtml(hintName || name) +
          (keySafe ? '"' : '" disabled') +
          (keySafe ? "" : ' title="附件鍵值異常，請重新查詢"') +
          ">" +
          "<span>" +
          escapeHtml(name) +
          sizeHtml +
          "</span></label>" +
          '<div class="incoming-attach-actions">' +
          (href
            ? '<a class="link" href="' +
              escapeHtml(href) +
              '" target="_blank" rel="noopener">下載原檔</a>'
            : '<span class="muted">' + (keySafe ? "未設定檔案下載連結" : "附件鍵值異常") + "</span>") +
          "</div>";

        elAttachList.appendChild(row);
      });
    }

    function _triggerParseAttachments() {
      try {
        if (window.DocDocApp && window.DocDocApp.modules && window.DocDocApp.modules.editor) {
          if (typeof window.DocDocApp.modules.editor.parseAttachments === "function") {
            window.DocDocApp.modules.editor.parseAttachments();
          }
        }
      } catch (e) {
        console.warn("parseAttachments failed:", e);
      }
    }

    // ------------------------------------------------------------
    // actions
    // ------------------------------------------------------------
    async function loadTodoList() {
      if (_busyTodo) return;
      if (!todoUrl) {
        setStatus(elTodoStatus, "未設定 todoUrl（由入口頁注入）", true);
        return;
      }

      _busyTodo = true;
      if (btnTodoLoad) btnTodoLoad.disabled = true;
      setStatus(elTodoStatus, "載入待辦中…", false);

      try {
        var q = elTodoFilter ? String(elTodoFilter.value || "").trim() : "";
        var url = todoUrl + (q ? ("?q=" + encodeURIComponent(q)) : "");
        var res = await fetch(url, { method: "GET" });
        if (!res.ok) {
          var t = await res.text();
          throw new Error("todo api error: " + res.status + " " + t);
        }
        var data = await res.json();
        _todoRows = _todoSortRows(data.items || data.rows || []);
        renderTodoOptions(_todoRows);
        setStatus(
          elTodoStatus,
          "您有" + _todoRows.length + "筆待辦公文，請擇一筆進行來文重點解析",
          false
        );
        if (_todoRows.length > 0) {
          var pinnedIdx = _findPinnedTodoIndex(_todoRows);
          var pickIdx = pinnedIdx >= 0 ? pinnedIdx : 0;
          if (elTodoPick && elTodoPick.options && elTodoPick.options.length > 1) {
            elTodoPick.selectedIndex = pickIdx + 1;
            applyTodoToLookup({
              silent: true,
              index: pickIdx,
              grsno: _asStr(_pick(_todoRows[pickIdx], ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], "")),
            });
          }
        }
      } catch (e) {
        console.error(e);
        setStatus(elTodoStatus, "載入失敗：" + (e && e.message ? e.message : String(e)), true);
      } finally {
        _busyTodo = false;
        if (btnTodoLoad) btnTodoLoad.disabled = false;
      }
    }

    function applyTodoToLookup(opts) {
      var silent = !!(opts && opts.silent);
      var grsno = _asStr(opts && opts.grsno);
      var idx = NaN;

      if (!grsno) {
        idx = elTodoPick ? parseInt(String(elTodoPick.value || ""), 10) : NaN;
        if (isNaN(idx) && opts && typeof opts.index === "number") {
          idx = opts.index;
        }
        
        var picked = _todoRows[idx] || {};
        grsno = _asStr(_pick(picked, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], ""));
      }
      
      if (!grsno) {
        if (!silent) alert("待辦資料缺少相關號");
        return;
      }
      
      // ✅ 物理鎖定：切換待辦時，必須立刻執行「深度清理」
      // 1. 清空前端附件 Token 緩存
      _clearStashedTokens();
      
      // 2. 清空 Editor 內解析與生成上下文
      _clearEditorContextHard();
      // 額外物理清空 Editor 的 sybAttachTokens
      var editorTokensEl = document.querySelector('[name="sybAttachTokens"]');
      if (editorTokensEl) {
        editorTokensEl.value = "";
        editorTokensEl.setAttribute("value", "");
      }

      // ✅ 更新 GRSNO 輸入框
      if (elGrsno) {
        elGrsno.value = grsno;
        elGrsno.dispatchEvent(new Event('input', { bubbles: true }));
      }
      
      // 執行查詢
      doLookup(grsno);
    }

    async function doLookup(grsnoOverride) {
      if (_busyLookup) return;

      var grsno = "";
      if (typeof grsnoOverride === "string" || typeof grsnoOverride === "number") {
        grsno = String(grsnoOverride).trim();
      }
      if (!grsno) {
        grsno = elGrsno ? String(elGrsno.value || "").trim() : "";
      }
      if (!grsno) {
        setStatus(elStatus, "請先輸入收文號", true);
        return;
      }
      
      // ✅ 修正：只要執行查詢，就視為視角切換，必須清空先前的緩存
      _activeGrsno = grsno;
      _clearStashedTokens();
      _clearEditorContextHard();

      if (!lookupUrl) {
        setStatus(elStatus, "未設定 lookupUrl（由入口頁注入）", true);
        return;
      }

      _busyLookup = true;
      setStatus(elStatus, "查詢中…", false);
      if (elPick) elPick.disabled = true;
      if (elBtnLookup) elBtnLookup.disabled = true;

      try {
      var res = await fetch(lookupUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ grsno: grsno }),
      });

        if (!res.ok) {
          var t = await res.text();
          throw new Error("lookup api error: " + res.status + " " + t);
        }

        var data = await res.json();
        _lookupRows = data.items || data.rows || data.data || [];
        renderPickOptions(_lookupRows);

        if (elPick && _lookupRows.length > 0) {
          elPick.value = "0";
        }
        setStatus(elStatus, "查到 " + _lookupRows.length + " 筆", false);

        if (_lookupRows.length > 0) {
          await doLoadAttachments();
        } else {
          _setAttachBoxVisible(false);
          if (elAttachList) elAttachList.innerHTML = "";
        }
      } catch (e) {
        console.error(e);
        setStatus(elStatus, "查詢失敗：" + (e && e.message ? e.message : String(e)), true);
      } finally {
        _busyLookup = false;
        if (elPick) elPick.disabled = false;
        if (elBtnLookup) elBtnLookup.disabled = false;
      }
    }

    async function doLoadAttachments() {
      if (_busyFiles) return;

      var idx = elPick ? parseInt(String(elPick.value || ""), 10) : NaN;
      if (isNaN(idx)) {
        alert("請先選擇一筆查詢結果");
        return;
      }

      var picked = _lookupRows[idx] || {};
      var grsno = _asStr(_pick(picked, ["grsno", "im_grsno", "tm_grsno", "IM_GRSNO", "TM_GRSNO"], ""));
      if (!grsno) {
        alert("查詢結果缺少 grsno，請重新查詢");
        return;
      }
      if (_activeGrsno !== grsno) {
        _activeGrsno = grsno;
        _clearStashedTokens();
      }

      if (!filesUrl) {
        if (elAttachList) {
          elAttachList.innerHTML = '<div class="err">未設定 filesUrl（由入口頁注入）</div>';
        }
        return;
      }

      _busyFiles = true;
      _setAttachBoxVisible(true);
      if (elAttachList) elAttachList.innerHTML = "載入附件清單…";

      try {
        var res = await fetch(filesUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ grsno: grsno }),
        });

        if (!res.ok) {
          var t = await res.text();
          throw new Error("incoming_files api error: " + res.status + " " + t);
        }

        var data = await res.json();
        var rows = _sortAttachRows(data.attachments || data.files || data.rows || []);
        renderAttachList(rows);
      } catch (e) {
        console.error(e);
        if (elAttachList) {
          elAttachList.innerHTML =
            '<div class="err">載入附件清單失敗：' +
            escapeHtml(e && e.message ? e.message : String(e)) +
            "</div>";
        }
      } finally {
        _busyFiles = false;
      }
    }

    async function stashSelectedBlobs() {
      if (_busyStash) return;

      if (!blobStashUrl) {
        alert("缺少 blobStashUrl（由入口頁注入）");
        return;
      }
      if (!elAttachList) return;

      var checkedEls = Array.from(elAttachList.querySelectorAll(".incomingAttachCk:checked"));
      var picked = checkedEls
        .map(function (x) {
          return {
            key: String(x.value || "").trim(),
            hintName: String(x.getAttribute("data-hint-name") || "").trim(),
          };
        })
        .filter(function (it) {
          return !!it.key && _isAttachKeySafe(it.key);
        });

      if (!picked.length) {
        alert("請至少勾選 1 個附件");
        return;
      }

      _busyStash = true;
      if (btnStash) btnStash.disabled = true;
      
      // ✅ 關鍵修正：在執行任何網路請求前，先徹底清空先前的 Token 與 視角狀態
      _clearStashedTokens();
      try {
        if (window.DocDocApp && window.DocDocApp.modules && window.DocDocApp.modules.editor) {
          if (typeof window.DocDocApp.modules.editor.resetFocusPick === "function") {
            window.DocDocApp.modules.editor.resetFocusPick();
          }
        }
      } catch (e) {}

      var canBuildDownload = !!blobDownloadTemplate;
      var results = [];

      for (var i = 0; i < picked.length; i++) {
        var k = picked[i].key;
        var hintName = picked[i].hintName;
        try {
          var res = await fetch(blobStashUrl, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ attach_key: k, hint_name: hintName }),
          });

          if (!res.ok) {
            var t = await res.text();
            throw new Error("stash failed: " + res.status + " " + t);
          }

          var data = await res.json();
          if (!data.ok) throw new Error(data.error || "stash not ok");

          var token = _asStr(data.token);
          var filename = _asStr(data.filename || data.name || k);
          if (!token) throw new Error("missing token");

          var url = canBuildDownload ? _buildBlobDownloadUrl(token) : "";
          results.push({ attach_key: k, hint_name: hintName, token: token, filename: filename, url: url });
        } catch (e) {
          console.error(e);
          results.push({ attach_key: k, hint_name: hintName, error: e && e.message ? e.message : String(e) });
        }
      }

      // write tokens (overwrite by current picked set; do NOT accumulate history)
      var next = [];
      results.forEach(function (r) {
        if (r && r.token && !r.error) next.push(r.token);
      });
      if (next.length > 0) {
        _writeTokens(next);
      } else {
        _clearStashedTokens();
      }

      // auto parse after stash (one-click flow)
      _triggerParseAttachments();

      _busyStash = false;
      if (btnStash) btnStash.disabled = false;
    }

    // ------------------------------------------------------------
    // bind
    // ------------------------------------------------------------
    if (elBtnLookup) {
      elBtnLookup.addEventListener("click", function () {
        doLookup();
      });
    }
    if (elPick) {
      elPick.addEventListener("change", function () {
        if (_lookupRows.length > 0) doLoadAttachments();
      });
    }
    if (btnStash) btnStash.addEventListener("click", stashSelectedBlobs);
    if (btnTodoLoad) btnTodoLoad.addEventListener("click", loadTodoList);
    if (elTodoPick) {
      elTodoPick.addEventListener("change", function () {
        applyTodoToLookup({ silent: true });
      });
    }
    if (elTodoFilter) {
      elTodoFilter.addEventListener("keydown", function (e) {
        if (e.key === "Enter") loadTodoList();
      });
    }
  };
})();

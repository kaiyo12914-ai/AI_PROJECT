(function () {
  "use strict";

  var TEXT = {
    ALL: "全部",
    EMPTY_LIST: "目前沒有影片資料。",
    LOADING: "載入中...",
    LIST_LOAD_FAIL: "影片清單載入失敗。",
    SELECT_FILE_FIRST: "請先選擇影片檔案。",
    UPLOADING: "上傳中...",
    UPLOAD_FAIL: "上傳失敗。",
    UPLOAD_DONE: "上傳完成，已填入影片路徑。",
    TITLE_REQUIRED: "標題不可空白。",
    FILE_PATH_REQUIRED: "請提供影片路徑。可先上傳檔案。",
    DURATION_INVALID: "時長必須大於或等於 0 的整數。",
    CREATING: "建立中...",
    CREATE_FAIL: "建立失敗。",
    CREATE_DONE: "建立完成。",
    YOUTUBE_URL_REQUIRED: "請輸入 YouTube 網址。",
    PROCESSING: "處理中",
    YOUTUBE_FAIL: "YouTube 匯入失敗。",
    YOUTUBE_DONE: "YouTube 匯入完成，已建立影片。",
    MP3_DONE_PREFIX: "MP3 轉檔完成：",
    DETAIL_LOAD_FAIL: "影片載入失敗。",
    QUALITY_PREFIX: "畫質：",
    LABEL_CATEGORY: "分類：",
    LABEL_TAGS: "標籤："
  };

  function setText(id, msg) {
    var el = document.getElementById(id);
    if (el) el.textContent = msg || "";
  }

  function getCookie(name) {
    var parts = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < parts.length; i += 1) {
      var c = parts[i].trim();
      if (c.indexOf(name + "=") === 0) return decodeURIComponent(c.substring(name.length + 1));
    }
    return "";
  }

  function getCsrfToken() {
    var byInput = document.querySelector("input[name='csrfmiddlewaretoken']");
    if (byInput && byInput.value) return byInput.value;
    var byMeta = document.querySelector("meta[name='csrf-token']");
    if (byMeta && byMeta.content) return byMeta.content;
    return getCookie("csrftoken");
  }

  function csrfHeaders(extra) {
    var token = getCsrfToken();
    var base = { "X-Requested-With": "XMLHttpRequest" };
    if (token) base["X-CSRFToken"] = token;
    if (!extra) return base;
    for (var k in extra) base[k] = extra[k];
    return base;
  }

  async function fetchJson(url, opts) {
    var res = await fetch(url, opts || {});
    var data = await res.json();
    return { res: res, data: data };
  }

  function toTagLine(tags) {
    return (tags || []).map(function (t) { return t.name; }).join(", ") || "-";
  }

  function toCategory(video) {
    return (video.category && video.category.name) ? video.category.name : "-";
  }

  var _allVideos = [];
  var _activeCategory = TEXT.ALL;

  function canDeleteVideo() {
    var body = document.body || {};
    var v = String((body.dataset && body.dataset.canDeleteVideo) || "");
    if (v === "1") return true;
    var isAdmin = String((body.dataset && body.dataset.isAdmin) || "");
    return isAdmin === "1";
  }

  async function deleteVideoById(videoId) {
    var ok = window.confirm("確定要刪除這部影片嗎？");
    if (!ok) return;
    try {
      var out = await fetchJson(apiurl("/videolearning/api/videos/" + String(videoId) + "/delete/"), {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: "{}"
      });
      if (!out.res.ok || !out.data || !out.data.ok) {
        window.alert((out.data && out.data.error && out.data.error.message) || "刪除失敗");
        return;
      }
      await loadVideoList();
    } catch (_err) {
      window.alert("刪除失敗");
    }
  }

  function renderVideoList(videos) {
    var listEl = document.getElementById("video-list");
    if (!listEl) return;
    listEl.innerHTML = "";

    if (!videos.length) {
      setText("video-list-text", TEXT.EMPTY_LIST);
      return;
    }
    setText("video-list-text", "");

    videos.forEach(function (v) {
      var li = document.createElement("li");
      li.className = "vl-video-card";

      var thumbContainer = document.createElement("div");
      thumbContainer.className = "vl-video-thumb-container";
      var img = document.createElement("img");
      img.className = "vl-video-thumb";
      img.src = v.thumbnail_path || apiurl("/static/videolearning/img/placeholder.png");
      img.alt = v.title;
      thumbContainer.appendChild(img);
      li.appendChild(thumbContainer);

      var body = document.createElement("div");
      body.className = "vl-video-card-body";

      var titleLink = document.createElement("a");
      titleLink.href = apiurl("/videolearning/videos/" + v.id + "/");
      titleLink.className = "vl-video-card-title";
      titleLink.textContent = v.title;
      body.appendChild(titleLink);

      var meta = document.createElement("div");
      meta.className = "vl-video-card-meta";
      meta.innerHTML = TEXT.LABEL_CATEGORY + toCategory(v) + " <br> " + TEXT.LABEL_TAGS + toTagLine(v.tags) + "<br>" + (v.quality_text || "");
      body.appendChild(meta);

      if (canDeleteVideo()) {
        var actions = document.createElement("div");
        actions.className = "vl-actions";
        var delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "vl-danger";
        delBtn.textContent = "刪除";
        delBtn.addEventListener("click", function () {
          deleteVideoById(v.id);
        });
        actions.appendChild(delBtn);
        body.appendChild(actions);
      }

      li.appendChild(body);
      listEl.appendChild(li);
    });
  }

  function renderFilterBar() {
    var filterEl = document.getElementById("category-filter");
    if (!filterEl) return;

    var categories = [TEXT.ALL];
    _allVideos.forEach(function (v) {
      var cat = toCategory(v);
      if (cat !== "-" && categories.indexOf(cat) === -1) categories.push(cat);
    });

    filterEl.innerHTML = "";
    categories.forEach(function (cat) {
      var pill = document.createElement("div");
      pill.className = "vl-filter-pill" + (cat === _activeCategory ? " is-active" : "");
      pill.textContent = cat;
      pill.addEventListener("click", function () {
        _activeCategory = cat;
        renderFilterBar();
        var filtered = cat === TEXT.ALL ? _allVideos : _allVideos.filter(function (v) { return toCategory(v) === cat; });
        renderVideoList(filtered);
      });
      filterEl.appendChild(pill);
    });
  }

  async function loadVideoList() {
    setText("video-list-text", TEXT.LOADING);
    try {
      var out = await fetchJson(apiurl("/videolearning/api/videos/"), { headers: csrfHeaders() });
      if (!out.res.ok || !out.data || !out.data.ok) {
        setText("video-list-text", TEXT.LIST_LOAD_FAIL);
        return;
      }
      _allVideos = (out.data.data && out.data.data.videos) || [];
      _activeCategory = TEXT.ALL;
      renderFilterBar();
      renderVideoList(_allVideos);
    } catch (_err) {
      setText("video-list-text", TEXT.LIST_LOAD_FAIL);
    }
  }

  async function uploadVideoFile() {
    var fileInput = document.getElementById("f-video-file");
    var pathInput = document.getElementById("f-file-path");
    if (!fileInput || !pathInput) return;
    var f = fileInput.files && fileInput.files[0];
    if (!f) return setText("upload-message", TEXT.SELECT_FILE_FIRST);

    var form = new FormData();
    form.append("file", f);
    setText("upload-message", TEXT.UPLOADING);
    try {
      var res = await fetch(apiurl("/videolearning/api/videos/upload/"), {
        method: "POST",
        headers: csrfHeaders(),
        body: form
      });
      var data = await res.json();
      if (!res.ok || !data || !data.ok) {
        setText("upload-message", (data && data.error && data.error.message) || TEXT.UPLOAD_FAIL);
        return;
      }
      pathInput.value = (data.data && data.data.upload && data.data.upload.file_path) || "";
      setText("upload-message", TEXT.UPLOAD_DONE);
    } catch (_err) {
      setText("upload-message", TEXT.UPLOAD_FAIL);
    }
  }

  async function createVideo(evt) {
    evt.preventDefault();
    var title = (document.getElementById("f-title").value || "").trim();
    var filePath = (document.getElementById("f-file-path").value || "").trim();
    var description = (document.getElementById("f-description").value || "").trim();
    var category = (document.getElementById("f-category").value || "").trim();
    var tagsRaw = (document.getElementById("f-tags").value || "").trim();
    var duration = parseInt(document.getElementById("f-duration").value || "0", 10);
    var visibility = document.getElementById("f-visibility").value;
    var status = document.getElementById("f-status").value;
    var tags = tagsRaw ? tagsRaw.split(",").map(function (x) { return x.trim(); }).filter(Boolean) : [];

    if (!title) return setText("form-message", TEXT.TITLE_REQUIRED);
    if (!filePath) return setText("form-message", TEXT.FILE_PATH_REQUIRED);
    if (isNaN(duration) || duration < 0) return setText("form-message", TEXT.DURATION_INVALID);

    setText("form-message", TEXT.CREATING);
    try {
      var out = await fetchJson(apiurl("/videolearning/api/videos/create/"), {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          title: title,
          file_path: filePath,
          description: description,
          category_name: category,
          tag_names: tags,
          duration_seconds: duration,
          visibility: visibility,
          status: status
        })
      });
      if (!out.res.ok || !out.data || !out.data.ok) {
        setText("form-message", (out.data && out.data.error && out.data.error.message) || TEXT.CREATE_FAIL);
        return;
      }
      setText("form-message", TEXT.CREATE_DONE);
      document.getElementById("create-video-form").reset();
      setText("upload-message", "");
      await loadVideoList();
    } catch (_err) {
      setText("form-message", TEXT.CREATE_FAIL);
    }
  }

  function bindYoutubeModeTabs() {
    var tabs = document.querySelectorAll(".vl-subtab[data-yt-mode]");
    var hidden = document.getElementById("y-output-format");
    var hint = document.getElementById("y-mode-hint");
    if (!tabs.length || !hidden) return;

    function applyMode(mode) {
      hidden.value = mode;
      tabs.forEach(function (btn) {
        var active = btn.getAttribute("data-yt-mode") === mode;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (hint) {
        if (mode === "mp3") hint.textContent = "MP3：僅轉檔輸出至 H:\\Mp3，不寫入影片清單。";
        else hint.textContent = "MP4：維持原功能，寫入影片清單。";
      }
    }

    tabs.forEach(function (btn) {
      btn.addEventListener("click", function () {
        applyMode(btn.getAttribute("data-yt-mode") || "mp4");
      });
    });

    applyMode(hidden.value || "mp4");
  }

  async function importYoutube(evt) {
    evt.preventDefault();
    var youtubeUrl = (document.getElementById("y-url").value || "").trim();
    if (!youtubeUrl) return setText("youtube-message", TEXT.YOUTUBE_URL_REQUIRED);

    var title = (document.getElementById("y-title").value || "").trim();
    var outputFormatEl = document.getElementById("y-output-format");
    var outputFormat = outputFormatEl ? String(outputFormatEl.value || "mp4").toLowerCase() : "mp4";
    var category = (document.getElementById("y-category").value || "").trim();
    var tagsRaw = (document.getElementById("y-tags").value || "").trim();
    var tags = tagsRaw ? tagsRaw.split(",").map(function (x) { return x.trim(); }).filter(Boolean) : [];
    var submitBtn = document.getElementById("y-submit");
    var msgEl = document.getElementById("youtube-message");
    var progress = 0;
    var progressTimer = null;

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.classList.add("vl-is-loading");
    }
    if (msgEl) msgEl.classList.add("vl-loading-text");

    function renderProgress(pct) {
      setText("youtube-message", TEXT.PROCESSING + " " + String(pct) + "%");
    }

    renderProgress(progress);
    progressTimer = setInterval(function () {
      if (progress < 95) {
        progress += (progress < 70 ? 3 : 1);
        if (progress > 95) progress = 95;
        renderProgress(progress);
      }
    }, 350);

    try {
      var out = await fetchJson(apiurl("/videolearning/api/videos/import-youtube/"), {
        method: "POST",
        headers: csrfHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          youtube_url: youtubeUrl,
          output_format: outputFormat,
          title: title,
          category_name: category,
          tag_names: tags,
          visibility: "private",
          status: "ready"
        })
      });
      if (!out.res.ok || !out.data || !out.data.ok) {
        setText("youtube-message", (out.data && out.data.error && out.data.error.message) || TEXT.YOUTUBE_FAIL);
        return;
      }

      if (outputFormat === "mp3") {
        var mp3Path = out.data && out.data.data && out.data.data.import ? out.data.data.import.file_path : "";
        setText("youtube-message", TEXT.MP3_DONE_PREFIX + mp3Path);
      } else {
        setText("youtube-message", TEXT.YOUTUBE_DONE);
      }

      document.getElementById("youtube-import-form").reset();
      bindYoutubeModeTabs();
      if (outputFormat !== "mp3") await loadVideoList();
    } catch (_err) {
      setText("youtube-message", TEXT.YOUTUBE_FAIL);
    } finally {
      if (progressTimer) clearInterval(progressTimer);
      if (progress < 100) renderProgress(100);
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove("vl-is-loading");
      }
      if (msgEl) msgEl.classList.remove("vl-loading-text");
    }
  }

  async function loadVideoDetail(videoId) {
    if (!videoId) return;
    try {
      var out = await fetchJson(apiurl("/videolearning/api/videos/" + videoId + "/"), { headers: csrfHeaders() });
      if (!out.res.ok || !out.data || !out.data.ok || !out.data.data.video) return;

      var v = out.data.data.video;
      setText("detail-title", v.title || "");
      setText("detail-category", toCategory(v));
      setText("detail-tags", toTagLine(v.tags));
      setText("detail-meta", TEXT.QUALITY_PREFIX + (v.quality_text || "-"));

      var player = document.getElementById("detail-player");
      if (player) {
        player.src = apiurl("/videolearning/api/videos/" + String(videoId) + "/stream/");
        player.load();
      }
    } catch (_err) {
      setText("detail-meta", TEXT.DETAIL_LOAD_FAIL);
    }
  }

  function bindEvents() {
    var refreshBtn = document.getElementById("refresh-list");
    if (refreshBtn) refreshBtn.addEventListener("click", loadVideoList);

    var uploadBtn = document.getElementById("f-upload");
    if (uploadBtn) uploadBtn.addEventListener("click", uploadVideoFile);

    var createForm = document.getElementById("create-video-form");
    if (createForm) createForm.addEventListener("submit", createVideo);

    var ytForm = document.getElementById("youtube-import-form");
    if (ytForm) ytForm.addEventListener("submit", importYoutube);

    bindYoutubeModeTabs();
  }

  function bindDetailPlayerControls() {
    var player = document.getElementById("detail-player");
    var progress = document.getElementById("detail-progress");
    var timeText = document.getElementById("detail-time");
    var fullscreenBtn = document.getElementById("detail-fullscreen-btn");
    if (!player || !progress || !timeText || !fullscreenBtn) return;

    var isSeeking = false;
    var pendingSeekRatio = null;

    function pad2(n) {
      return String(n).padStart(2, "0");
    }

    function formatTime(sec) {
      if (!isFinite(sec) || sec < 0) return "00:00";
      var s = Math.floor(sec);
      var m = Math.floor(s / 60);
      var r = s % 60;
      return pad2(m) + ":" + pad2(r);
    }

    function syncProgressFromPlayer() {
      if (isSeeking) return;
      if (player.duration && isFinite(player.duration) && player.duration > 0) {
        progress.value = String((player.currentTime / player.duration) * 100);
      } else {
        progress.value = "0";
      }
      timeText.textContent = formatTime(player.currentTime) + " / " + formatTime(player.duration);
    }

    function seekByProgressValue() {
      if (!player.duration || !isFinite(player.duration) || player.duration <= 0) {
        pendingSeekRatio = Math.max(0, Math.min(1, Number(progress.value || 0) / 100));
        return;
      }
      var pct = Number(progress.value || 0) / 100;
      player.currentTime = Math.max(0, Math.min(player.duration, pct * player.duration));
      timeText.textContent = formatTime(player.currentTime) + " / " + formatTime(player.duration);
    }

    function setProgressFromClientX(clientX) {
      var rect = progress.getBoundingClientRect();
      if (!rect || rect.width <= 0) return;
      var ratio = (clientX - rect.left) / rect.width;
      ratio = Math.max(0, Math.min(1, ratio));
      progress.value = String(ratio * 100);
      seekByProgressValue();
    }

    player.addEventListener("loadedmetadata", function () {
      if (pendingSeekRatio !== null && isFinite(player.duration) && player.duration > 0) {
        player.currentTime = Math.max(0, Math.min(player.duration, pendingSeekRatio * player.duration));
        pendingSeekRatio = null;
      }
      syncProgressFromPlayer();
    });
    player.addEventListener("timeupdate", syncProgressFromPlayer);
    player.addEventListener("durationchange", syncProgressFromPlayer);

    progress.addEventListener("mousedown", function (evt) {
      isSeeking = true;
      setProgressFromClientX(evt.clientX);
    });
    progress.addEventListener("touchstart", function () { isSeeking = true; }, { passive: true });
    progress.addEventListener("input", seekByProgressValue);
    progress.addEventListener("click", seekByProgressValue);
    progress.addEventListener("mousemove", function (evt) {
      if (!isSeeking) return;
      setProgressFromClientX(evt.clientX);
    });
    document.addEventListener("mousemove", function (evt) {
      if (!isSeeking) return;
      setProgressFromClientX(evt.clientX);
    });

    function finishSeek() {
      isSeeking = false;
      seekByProgressValue();
      syncProgressFromPlayer();
    }

    progress.addEventListener("change", finishSeek);
    progress.addEventListener("mouseup", finishSeek);
    progress.addEventListener("touchend", finishSeek, { passive: true });

    fullscreenBtn.addEventListener("click", function () {
      var doc = document;
      var isFs = !!(doc.fullscreenElement || doc.webkitFullscreenElement || doc.msFullscreenElement);
      if (isFs) {
        if (doc.exitFullscreen) doc.exitFullscreen();
        else if (doc.webkitExitFullscreen) doc.webkitExitFullscreen();
        else if (doc.msExitFullscreen) doc.msExitFullscreen();
        return;
      }

      var target = player;
      try {
        var p = null;
        if (target.requestFullscreen) p = target.requestFullscreen();
        else if (target.webkitRequestFullscreen) p = target.webkitRequestFullscreen();
        else if (target.msRequestFullscreen) p = target.msRequestFullscreen();
        else if (player.webkitEnterFullscreen) p = player.webkitEnterFullscreen();
        if (p && typeof p.catch === "function") {
          p.catch(function () { setText("detail-meta", "全螢幕切換失敗，請用播放器右下角按鈕。"); });
        }
      } catch (_err) {
        setText("detail-meta", "全螢幕切換失敗，請用播放器右下角按鈕。");
      }
    });
  }

  function bootstrap() {
    bindEvents();
    bindDetailPlayerControls();
    var videoId = document.body.dataset.videoId;
    if (videoId) {
      loadVideoDetail(videoId);
    } else if (document.getElementById("video-list")) {
      loadVideoList();
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootstrap);
  else bootstrap();
})();

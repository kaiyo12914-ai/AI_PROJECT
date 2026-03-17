/* =========================================================
 * ✅ 專案規範：
 * - URL 統一由 apiurl_factory() 組合
 * - baseUrl = body.dataset.baseUrl (= request.script_name)
 * - 不得硬寫 /...（proxy prefix）
 * - ✅ 各子系統 API 必須帶 node 前綴：comment/api/...
 * ========================================================= */

(function () {
  "use strict";

  

  // ✅ 全專案共用：apiurl_factory（由 portal/js/apiurl_factory.js 提供）
  var apiurl_factory = window.apiurl_factory || function(path){
    var base = String((document.body && document.body.dataset && document.body.dataset.baseUrl) || "").trim();
    var p = String(path || "");
    if (p && p.charAt(0) !== "/") p = "/" + p;
    return base + p;
  };

// ✅ CSRF：即使目前 API 可能 csrf_exempt，也先做滿（未來改回 CSRF 不會炸）
  function getCookie(name) {
    const cookieStr = document.cookie || "";
    const cookies = cookieStr.split(";").map(c => c.trim()).filter(Boolean);
    for (const c of cookies) {
      if (c.startsWith(name + "=")) return decodeURIComponent(c.substring(name.length + 1));
    }
    return "";
  }

  // 維度數據
  const thoughtCharacteristics = [
    { name: "聰敏機靈", color: "#3b82f6" },
    { name: "個性均衡", color: "#3b82f6" },
    { name: "任事積極", color: "#3b82f6" },
    { name: "思維活絡", color: "#3b82f6" },
    { name: "樂觀進取", color: "#3b82f6" },
    { name: "進取心強", color: "#3b82f6" },
    { name: "主動向上", color: "#3b82f6" },
    { name: "主動積極", color: "#3b82f6" },
    { name: "具企圖心與朝氣活力", color: "#3b82f6" },
    { name: "思慮周深", color: "#3b82f6" },
    { name: "處事保守", color: "#f43f5e" }
  ];

  const characterCharacteristics = [
    { name: "服從命令", color: "#3b82f6" },
    { name: "貫徹命令", color: "#3b82f6" },
    { name: "遵守規範", color: "#3b82f6" },
    { name: "職業操守佳", color: "#3b82f6" },
    { name: "人際關係佳", color: "#3b82f6" },
    { name: "服從紀律", color: "#3b82f6" },
    { name: "誠信與奉獻", color: "#3b82f6" },
    { name: "負責盡職", color: "#3b82f6" },
    { name: "謹守本份", color: "#3b82f6" },
    { name: "為人忠厚木訥", color: "#3b82f6" },
    { name: "認真負責", color: "#3b82f6" },
    { name: "奉公守法", color: "#3b82f6" },
    { name: "任勞任怨", color: "#3b82f6" },
    { name: "待人誠懇踏實", color: "#3b82f6" },
    { name: "和藹親切", color: "#3b82f6" },
    { name: "個性剛直", color: "#f43f5e" },
    { name: "主觀意識稍強", color: "#f43f5e" },
    { name: "安份守己", color: "#3b82f6" },
    { name: "遇事沉著", color: "#3b82f6" },
    { name: "缺乏擔當", color: "#f43f5e" }
  ];

  const performanceCharacteristics = [
    { name: "成果表現佳", color: "#3b82f6" },
    { name: "績效卓越", color: "#3b82f6" },
    { name: "工作效率高", color: "#3b82f6" },
    { name: "圓滿達成任務", color: "#3b82f6" },
    { name: "對命令全力貫徹", color: "#3b82f6" },
    { name: "成效優異", color: "#3b82f6" },
    { name: "本職學能優異", color: "#3b82f6" },
    { name: "處事主動積極", color: "#3b82f6" },
    { name: "作事態度欠積極", color: "#f43f5e" },
    { name: "表現待加強", color: "#f43f5e" },
    { name: "工作效率待加強", color: "#f43f5e" }
  ];

  const abilityCharacteristics = [
    { name: "本職才能精湛", color: "#3b82f6" },
    { name: "專業技術強", color: "#3b82f6" },
    { name: "溝通能力佳", color: "#3b82f6" },
    { name: "表達能力佳", color: "#3b82f6" },
    { name: "解決問題能力", color: "#3b82f6" },
    { name: "說服力強", color: "#3b82f6" },
    { name: "參謀作業能力佳", color: "#3b82f6" },
    { name: "業務嫻熟", color: "#3b82f6" },
    { name: "思維縝密", color: "#3b82f6" },
    { name: "反應敏捷", color: "#3b82f6" },
    { name: "表達伶俐", color: "#3b82f6" },
    { name: "協調能力佳", color: "#3b82f6" },
    { name: "思慮清晰", color: "#3b82f6" },
    { name: "個性較保守", color: "#f43f5e" },
    { name: "表達能力待加強", color: "#f43f5e" },
    { name: "應變能力待加強", color: "#f43f5e" },
    { name: "協調能力欠圓融", color: "#f43f5e" },
    { name: "體能待加強", color: "#f43f5e" }
  ];

  const knowledgeCharacteristics = [
    { name: "學習能力佳", color: "#3b82f6" },
    { name: "知識淵博", color: "#3b82f6" },
    { name: "專業素養高", color: "#3b82f6" },
    { name: "專業學養豐富", color: "#3b82f6" },
    { name: "業務法律嫻熟", color: "#3b82f6" },
    { name: "學有專長", color: "#3b82f6" },
    { name: "主動學習進取", color: "#3b82f6" },
    { name: "思維邏輯清晰", color: "#3b82f6" },
    { name: "學習能力不足", color: "#f43f5e" },
    { name: "專業素養不足", color: "#f43f5e" },
    { name: "個人學識待精進", color: "#f43f5e" },
    { name: "學習領域待拓展", color: "#f43f5e" },
    { name: "理論與實務需更平衡", color: "#f43f5e" },
    { name: "思維邏輯待加強", color: "#f43f5e" }
  ];

  const specialNotes = [
    { name: "缺乏運動", color: "#f43f5e" },
    { name: "應注意身心健康", color: "#f43f5e" },
    { name: "應多安排休閒活動", color: "#3b82f6" },
    { name: "缺乏生涯規劃", color: "#f43f5e" }
  ];

  const performanceGrades = [
    { name: "特優", color: "#3b82f6" },
    { name: "優等", color: "#536dfa" },
    { name: "甲上", color: "#22c55e" },
    { name: "甲等", color: "#10b981" },
    { name: "乙上", color: "#f43f5e" },
    { name: "乙等", color: "#ef4444" },
    { name: "丙等", color: "#ef4444" }
  ];

  const state = {
    traits: [],
    selectedTraits: new Set(),
    customTraits: [],
    comments: [],
    currentStudent: null,
    activeTab: "all",
    performanceGrade: null,
    // ✅ 避免連點造成多次請求堆疊（符合穩定性）
    generating: false
  };

  // elements
  let traitListEl, selectedTraitsEl, customTraitListEl, customTraitInputEl, customTraitCountEl;
  let studentListEl, studentButtonsEl, commentPreviewEl;

  function initElements() {
    traitListEl = document.getElementById("traitList");
    selectedTraitsEl = document.getElementById("selectedTraits");
    customTraitListEl = document.getElementById("customTraitList");
    customTraitInputEl = document.getElementById("customTraitInput");
    customTraitCountEl = document.getElementById("customTraitCount");
    studentListEl = document.getElementById("studentList");
    studentButtonsEl = document.getElementById("studentButtons");
    commentPreviewEl = document.getElementById("commentPreview");
  }

  function initState() {
    state.traits = [
      ...thoughtCharacteristics,
      ...characterCharacteristics,
      ...performanceCharacteristics,
      ...abilityCharacteristics,
      ...knowledgeCharacteristics,
      ...specialNotes
    ];
  }

  function bindEvents() {
    document.getElementById("btnResetAll").addEventListener("click", resetAll);
    document.getElementById("btnGenerateStudents").addEventListener("click", () => generateStudentButtons({ silentEmpty: false }));
    document.getElementById("btnAddCustomTrait").addEventListener("click", addCustomTrait);
    document.getElementById("btnClearCustomTraits").addEventListener("click", clearCustomTraits);
    document.getElementById("btnResetTraits").addEventListener("click", resetTraits);
    document.getElementById("btnGenerateComment").addEventListener("click", generateComment);

    document.getElementById("btnDownloadTxt").addEventListener("click", downloadTxt);
    document.getElementById("btnDownloadCsv").addEventListener("click", downloadCsv);

    document.getElementById("btnImportFile").addEventListener("click", importFile);
    document.getElementById("importFileInput").addEventListener("change", handleFileUpload);

    document.getElementById("btnClearSelectedTraits").addEventListener("click", clearSelectedTraits);
    document.getElementById("btnResetPerformance").addEventListener("click", resetPerformanceGrades);
    document.getElementById("btnClearComments").addEventListener("click", clearComments);

    customTraitInputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") addCustomTrait();
    });

    document.querySelectorAll("#tabs button").forEach(btn => {
      btn.addEventListener("click", () => toggleTab(btn.getAttribute("data-tab")));
    });
  }

  function toggleTab(tab) {
    document.querySelectorAll("#tabs button").forEach(btn => btn.classList.remove("active"));
    const active = document.querySelector(`#tabs button[data-tab="${tab}"]`);
    if (active) active.classList.add("active");
    state.activeTab = tab || "all";
    renderTraits();
  }

  function renderTraits() {
    traitListEl.innerHTML = "";
    let traitsToRender;

    switch (state.activeTab) {
      case "thought": traitsToRender = thoughtCharacteristics; break;
      case "character": traitsToRender = characterCharacteristics; break;
      case "performance": traitsToRender = performanceCharacteristics; break;
      case "ability": traitsToRender = abilityCharacteristics; break;
      case "knowledge": traitsToRender = knowledgeCharacteristics; break;
      case "special": traitsToRender = specialNotes; break;
      default: traitsToRender = state.traits;
    }

    traitsToRender.forEach(trait => {
      const btn = document.createElement("button");
      btn.className = "pill";

      if (state.selectedTraits.has(trait.name)) {
        btn.style.backgroundColor =
          trait.color === "#3b82f6" ? "#536dfa" :
          trait.color === "#f43f5e" ? "#ef4444" : "#2563eb";
        btn.style.color = "white";
      } else {
        btn.style.backgroundColor = trait.color + "1A";
        btn.style.borderColor = trait.color;
      }

      btn.textContent = trait.name;

      if (trait.color === "#3b82f6") {
        btn.title = "正面特質";
        btn.classList.add("passitive");
      } else if (trait.color === "#f43f5e") {
        btn.title = "負面特質，需注意改進";
        btn.classList.add("negitive");
      }

      btn.addEventListener("click", () => toggleTrait(trait.name));
      traitListEl.appendChild(btn);
    });
  }

  function toggleTrait(traitName) {
    if (state.selectedTraits.has(traitName)) state.selectedTraits.delete(traitName);
    else state.selectedTraits.add(traitName);
    renderTraits();
    renderSelectedTraits();
  }

  function renderSelectedTraits() {
    selectedTraitsEl.innerHTML = "";
    if (state.selectedTraits.size === 0) {
      const p = document.createElement("p");
      p.textContent = "未選擇任何指標";
      p.style.color = "#6b7280";
      selectedTraitsEl.appendChild(p);
      return;
    }

    Array.from(state.selectedTraits).forEach(traitName => {
      const span = document.createElement("span");
      span.className = "pill selected";
      span.textContent = traitName;
      span.style.marginRight = "8px";
      selectedTraitsEl.appendChild(span);
    });
  }

  function renderPerformanceGrades() {
    const performanceListEl = document.getElementById("performanceGradeList");
    performanceListEl.innerHTML = "";

    performanceGrades.forEach(grade => {
      const btn = document.createElement("button");
      btn.className = "pill performance-grade";
      btn.textContent = grade.name;

      const selected = state.performanceGrade === grade.name;
      btn.style.backgroundColor = selected ? "#2563eb" : (grade.color + "20");
      btn.style.color = selected ? "white" : "";

      if (selected) btn.classList.add("selected");

      btn.addEventListener("click", () => {
        state.performanceGrade = grade.name;
        renderPerformanceGrades();
      });

      performanceListEl.appendChild(btn);
    });
  }

  function resetPerformanceGrades() {
    state.performanceGrade = null;
    renderPerformanceGrades();
  }

  function addCustomTrait() {
    const value = customTraitInputEl.value.trim();
    if (!value) return;

    if (state.customTraits.length >= 10) {
      alert("自訂指標最多 10 個！");
      return;
    }

    if (state.traits.some(t => t.name === value)) {
      alert("此指標已存在，請選擇其他特質！");
      return;
    }

    state.customTraits.push({ name: value, color: "#2563eb" });
    state.traits.push({ name: value, color: "#2563eb" });

    customTraitInputEl.value = "";
    customTraitCountEl.textContent = String(state.customTraits.length);
    renderCustomTraits();
    renderTraits();
  }

  function clearCustomTraits() {
    const customNames = new Set(state.customTraits.map(ct => ct.name));
    Array.from(state.selectedTraits).forEach(t => {
      if (customNames.has(t)) state.selectedTraits.delete(t);
    });

    state.traits = state.traits.filter(t => !customNames.has(t.name));
    state.customTraits = [];

    customTraitCountEl.textContent = "0";
    renderCustomTraits();
    renderTraits();
    renderSelectedTraits();
  }

  function renderCustomTraits() {
    customTraitListEl.innerHTML = "";
    if (state.customTraits.length === 0) return;

    state.customTraits.forEach((trait, index) => {
      const span = document.createElement("span");
      span.className = "pill";
      span.textContent = trait.name;
      span.title = `第 ${index + 1} 個自訂指標`;
      customTraitListEl.appendChild(span);
    });
  }

  function generateStudentButtons(opts) {
    const silentEmpty = !!(opts && opts.silentEmpty);

    const lines = studentListEl.value.split("\n").map(l => l.trim()).filter(Boolean);
    studentButtonsEl.innerHTML = "";
    state.currentStudent = null;

    if (lines.length === 0) {
      if (!silentEmpty) alert("請輸入人員列表！");
      return;
    }

    lines.forEach(line => {
      const btn = document.createElement("button");
      btn.className = "student-btn";
      btn.textContent = line;
      btn.addEventListener("click", () => {
        Array.from(studentButtonsEl.children).forEach(b => b.classList.remove("active"));
        state.currentStudent = line;
        btn.classList.add("active");
      });
      studentButtonsEl.appendChild(btn);
    });

    const firstBtn = studentButtonsEl.firstElementChild;
    if (firstBtn) {
      state.currentStudent = lines[0];
      firstBtn.classList.add("active");
    }
  }

  // ✅ 生成評語：依規範 반드시 comment node 前綴 → comment/api/generate_comment/
  async function generateComment() {
    if (state.generating) return; // ✅ 避免連點
    if (!state.currentStudent) {
      alert("請先選擇人員！");
      return;
    }
    if (state.selectedTraits.size === 0 && !state.performanceGrade) {
      alert("請至少選擇一個維度或評等！");
      return;
    }

    state.generating = true;

    const namePart = state.currentStudent.split(".")[1] || state.currentStudent;

    const loadingItem = {
      student: state.currentStudent,
      comment: "⏳ 生成中，請稍候..."
    };
    state.comments.unshift(loadingItem);
    renderComments();

    try {
      const traitsArr = Array.from(state.selectedTraits);
      const grade = state.performanceGrade || "";
      const csrftoken = getCookie("csrftoken");

      const response = await fetch(apiurl_factory("comment/api/generate_comment/"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrftoken ? { "X-CSRFToken": csrftoken } : {})
        },
        body: JSON.stringify({
          student_name: namePart,
          traits: traitsArr,
          performance_grade: grade,
          max_chars: 80,
          temperature: 0.7,
          timeout: 30
        })
      });

      let payload = null;
      try { payload = await response.json(); } catch { payload = null; }

      if (!response.ok) {
        const detail = payload && (payload.detail || payload.error) ? `\n${payload.detail || payload.error}` : "";
        throw new Error(`伺服器錯誤: ${response.status}${detail}`);
      }

      if (!payload || payload.ok !== true) {
        throw new Error((payload && (payload.error || payload.detail)) || "生成失敗");
      }

      loadingItem.comment = payload.reply || payload.result || "(empty)";
      renderComments();
    } catch (error) {
      // eslint-disable-next-line no-console
      console.error("生成評語失敗:", error);
      loadingItem.comment = `❌ 生成失敗: ${error.message || error}`;
      renderComments();
    } finally {
      state.generating = false;
    }
  }

  function renderComments() {
    commentPreviewEl.innerHTML = "";

    if (state.comments.length === 0) {
      const empty = document.createElement("div");
      empty.textContent = "目前尚無記錄";
      empty.style.color = "#6b7280";
      commentPreviewEl.appendChild(empty);
      return;
    }

    state.comments.forEach(({ student, comment }) => {
      const div = document.createElement("div");
      div.className = "preview-item";

      const header = document.createElement("header");
      header.textContent = student;
      header.style.fontWeight = "500";
      header.style.marginBottom = "6px";

      const content = document.createElement("pre");
      content.textContent = comment;
      content.style.whiteSpace = "pre-wrap";
      content.style.maxWidth = "100%";
      content.style.overflowX = "auto";

      div.appendChild(header);
      div.appendChild(content);
      commentPreviewEl.appendChild(div);
    });
  }

  function downloadTxt() {
    if (state.comments.length === 0) return alert("無記錄可匯出");
    const lines = state.comments.map(c => `${c.student}\t${c.comment}`);
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = `人員考核評語_${new Date().toISOString().slice(0,10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function downloadCsv() {
    if (state.comments.length === 0) return alert("無記錄可匯出");

    const csvHeader = "\uFEFF";
    const header = ["人員", "考核意見"];
    const rows = state.comments.map(c => [
      `"${String(c.student).replace(/"/g, '""')}"`,
      `"${String(c.comment).replace(/"/g, '""').replace(/\n/g, ' ')}"`
    ].join(","));

    const csvContent = [csvHeader, header.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });

    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `人員考核評語_${new Date().toISOString().slice(0,10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function resetAll() {
    if (!confirm("確定要清除所有設定？")) return;

    initState();
    state.selectedTraits = new Set();
    state.customTraits = [];
    state.comments = [];
    state.currentStudent = null;
    state.performanceGrade = null;
    state.generating = false;

    studentListEl.value = "";
    customTraitCountEl.textContent = "0";

    renderCustomTraits();
    renderTraits();
    renderSelectedTraits();
    renderPerformanceGrades();
    generateStudentButtons({ silentEmpty: true });
    renderComments();
  }

  function resetTraits() {
    state.selectedTraits = new Set();
    renderTraits();
    renderSelectedTraits();
  }

  function clearSelectedTraits() {
    state.selectedTraits = new Set();
    renderTraits();
    renderSelectedTraits();
  }

  function importFile() {
    document.getElementById("importFileInput").click();
  }

  function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    let contentType = "";

    const ext = file.name.split(".").pop().toLowerCase();
    if (ext === "txt") contentType = "text/plain";
    else if (ext === "csv") {
      contentType = "text/csv";
      if (!confirm("建議使用TXT格式檔案，是否繼續？")) return;
    } else {
      alert("不支援的檔案類型，請選擇.txt或.csv文件");
      return;
    }

    reader.onload = function (e) {
      const content = String(e.target.result || "");
      if (contentType === "text/csv") {
        const lines = content.split("\n")
          .map(line => line.trim())
          .filter(line => line.length > 0)
          .filter(line => !line.startsWith("座號"));
        studentListEl.value = lines.join("\n");
      } else {
        studentListEl.value = content;
      }
      generateStudentButtons({ silentEmpty: true });
    };

    reader.onerror = function () {
      alert("讀取檔案時出錯");
    };

    reader.readAsText(file);
  }

  function clearComments() {
    if (!confirm("確定要清除所有評語記錄？")) return;
    state.comments = [];
    renderComments();
  }

  function boot() {
    initElements();
    initState();
    bindEvents();

    renderTraits();
    renderSelectedTraits();
    renderPerformanceGrades();
    renderComments();
  }

  window.addEventListener("DOMContentLoaded", boot);
})();

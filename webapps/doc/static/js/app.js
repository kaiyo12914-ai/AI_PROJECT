// 維度數據
const thoughtCharacteristics = [
  "聰敏機靈", "個性均衡", "任事積極",
  "思維活絡", "樂觀進取", "進取心強",
  "主動向上", "主動積極", "具企圖心與朝氣活力",
  "思慮周深", "參謀作業能力佳", "開創性較不足",
  "決斷力稍待加強", "處事保守", "應變能力待加強"
];

const characterCharacteristics = [
  "服從命令", "貫徹命令", "遵守規範",
  "職業操守佳", "人際關係佳", "服從紀律",
  "誠信與奉獻", "負責盡職", "謹守本份",
  "為人忠厚木訥", "認真負責", "奉公守法",
  "任勞任怨", "待人誠懇踏實", "和藹親切",
  "個性剛直", "主觀意識稍強", "安份守己",
  "遇事沉著", "缺乏擔當"
];

const performanceCharacteristics = [
  "成果表現佳", "績效卓越", "工作效率高",
  "圓滿達成任務", "對命令全力貫徹", "成效優異",
  "本職學能優異", "處事主動積極",
  "作事態度欠積極",
  "表現待加強", "工作效率待加強"
];

const abilityCharacteristics = [
  "本職才能精湛", "專業技術強", "溝通能力佳",
  "表達能力佳", "解決問題能力", "說服力強",
  "參謀作業能力佳", "業務嫻熟", "思維縝密",
  "反應敏捷", "表達伶俐", "協調能力佳",
  "思慮清晰", "個性較保守", "表達能力待加強",
  "應變能力待加強", "協調能力欠圓融", "體能待加強"
];

const knowledgeCharacteristics = [
  "學習能力佳", "知識淵博", "專業素養高",
  "專業學養豐富", "業務法律嫻熟", "學有專長",
  "主動學習進取", "思維邏輯清晰",
  "學習能力不足", "專業素養不足", "個人學識待精進",
  "學習領域待拓展", "理論與實務需更平衡", "思維邏輯待加強"
];

const specialNotes = [
  "缺乏運動", "應注意身心健康", "應多安排休閒活動",
  "缺乏生涯規劃"
];

// 績效評等選項
const performanceGrades = [
  { name: "特優", color: "#22c55e" },
  { name: "優等", color: "#10b981" },
  { name: "甲上", color: "#3b82f6" },
  { name: "甲等", color: "#536dfa" },
  { name: "乙上", color: "#f43f5e" },
  { name: "乙等", color: "#ef4444" }
];

// ✅ 統一負面特質判定（你原本寫了「作事精神稍欠積極」但清單是「作事態度欠積極」）
const NEGATIVE_TRAITS = new Set([
  ...specialNotes,
  "作事態度欠積極",
  "表現待加強",
  "工作效率待加強",
  "學習能力不足",
  "專業素養不足",
  "個人學識待精進",
  "學習領域待拓展",
  "理論與實務需更平衡",
  "思維邏輯待加強",
  "決斷力稍待加強",
  "開創性較不足",
  "處事保守",
  "應變能力待加強",
  "協調能力欠圓融",
  "體能待加強",
  "缺乏擔當"
]);

// 狀態管理
const state = {
  traits: [
    ...thoughtCharacteristics,
    ...characterCharacteristics,
    ...performanceCharacteristics,
    ...abilityCharacteristics,
    ...knowledgeCharacteristics,
    ...specialNotes
  ],
  selectedTraits: new Set(),
  customTraits: [],
  comments: [],
  currentStudent: null,
  previewVisible: true,
  activeTab: "all",
  performanceGrade: null
};

// DOM 元素
const traitListEl = document.getElementById("traitList");
const selectedTraitsEl = document.getElementById("selectedTraits");
const customTraitListEl = document.getElementById("customTraitList");
const customTraitInputEl = document.getElementById("customTraitInput");
const customTraitCountEl = document.getElementById("customTraitCount");
const studentListEl = document.getElementById("studentList");
const studentButtonsEl = document.getElementById("studentButtons");
const commentPreviewEl = document.getElementById("commentPreview");

// ============================================================
// ✅ 反向代理安全：取得 prefix + 組 API URL
// 你可以在 template 注入任一種：
// 1) window.__PROXY_PREFIX__ = "/mpc/ai";
// 2) <meta name="proxy-prefix" content="/mpc/ai">
// 3) <html data-proxy-prefix="/mpc/ai">
// ============================================================
function getProxyPrefix() {
  // 1) window 變數
  if (typeof window.__PROXY_PREFIX__ === "string" && window.__PROXY_PREFIX__) {
    return normalizePrefix(window.__PROXY_PREFIX__);
  }
  // 2) meta
  const meta = document.querySelector('meta[name="proxy-prefix"]');
  if (meta && meta.getAttribute("content")) {
    return normalizePrefix(meta.getAttribute("content"));
  }
  // 3) html dataset
  const html = document.documentElement;
  const dp = html && (html.getAttribute("data-proxy-prefix") || html.dataset.proxyPrefix);
  if (dp) return normalizePrefix(dp);

  // 沒提供 prefix → 回空字串
  return "";
}

function normalizePrefix(p) {
  p = (p || "").trim();
  if (!p) return "";
  if (!p.startsWith("/")) p = "/" + p;
  if (p.length > 1 && p.endsWith("/")) p = p.slice(0, -1);
  return p;
}

function resolveApiUrl(path) {
  // path like "/api/chat/"
  path = (path || "").trim();
  if (!path.startsWith("/")) path = "/" + path;

  const prefix = getProxyPrefix();
  return prefix ? (prefix + path) : path;
}

// ============================================================
// 小工具
// ============================================================
function hexToRgba(hex, alpha) {
  const h = (hex || "").replace("#", "").trim();
  if (h.length !== 6) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// 初始化
function init() {
  renderTraits();
  renderSelectedTraits();
  renderCustomTraits();
  renderPerformanceGrades();

  // 綁定事件
  const el = (id) => document.getElementById(id);

  el("btnResetAll")?.addEventListener("click", resetAll);
  el("btnGenerateStudents")?.addEventListener("click", generateStudentButtons);
  el("btnAddCustomTrait")?.addEventListener("click", addCustomTrait);
  el("btnClearCustomTraits")?.addEventListener("click", clearCustomTraits);
  el("btnResetTraits")?.addEventListener("click", resetTraits);
  el("btnGenerateComment")?.addEventListener("click", async () => { await generateComment(); });
  el("btnDownloadTxt")?.addEventListener("click", downloadTxt);
  el("btnDownloadCsv")?.addEventListener("click", downloadCsv);
  el("btnImportFile")?.addEventListener("click", importFile);
  el("importFileInput")?.addEventListener("change", handleFileUpload);

  customTraitInputEl?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") addCustomTrait();
  });

  document.querySelectorAll("#tabs button").forEach((btn) => {
    btn.addEventListener("click", () => toggleTab(btn.getAttribute("data-tab")));
  });

  renderComments();
}

// 切換分頁
function toggleTab(tab) {
  document.querySelectorAll("#tabs button").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.querySelector(`#tabs button[data-tab="${tab}"]`);
  if (activeBtn) activeBtn.classList.add("active");
  state.activeTab = tab;
  renderTraits();
}

// 渲染特質按鈕
function renderTraits() {
  if (!traitListEl) return;
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

  traitsToRender.forEach((trait) => {
    const btn = document.createElement("button");
    btn.className = "pill";
    if (state.selectedTraits.has(trait)) {
      btn.classList.add("selected");
      if (NEGATIVE_TRAITS.has(trait)) btn.classList.add("negative-trait");
    }
    btn.textContent = trait;
    btn.addEventListener("click", () => toggleTrait(trait));
    traitListEl.appendChild(btn);
  });
}

// 切換特質選取
function toggleTrait(trait) {
  if (state.selectedTraits.has(trait)) state.selectedTraits.delete(trait);
  else state.selectedTraits.add(trait);

  renderTraits();
  renderSelectedTraits();
}

// 渲染已選特質
function renderSelectedTraits() {
  if (!selectedTraitsEl) return;
  selectedTraitsEl.innerHTML = "";

  if (state.selectedTraits.size === 0) {
    const p = document.createElement("p");
    p.textContent = "未選擇任何指標";
    p.style.color = "#6b7280";
    selectedTraitsEl.appendChild(p);
    return;
  }

  Array.from(state.selectedTraits).forEach((trait) => {
    const span = document.createElement("span");
    span.className = "pill selected";
    if (NEGATIVE_TRAITS.has(trait)) span.classList.add("negative-trait");
    span.textContent = trait;
    span.style.marginRight = "8px";
    selectedTraitsEl.appendChild(span);
  });
}

// 渲染績效評等按鈕
function renderPerformanceGrades() {
  const performanceListEl = document.getElementById("performanceGradeList");
  if (!performanceListEl) return;

  performanceListEl.innerHTML = "";
  performanceGrades.forEach((grade) => {
    const btn = document.createElement("button");
    btn.className = "pill performance-grade";
    btn.textContent = grade.name;

    // ✅ 修正：不要 grade.color + 20（不是合法色碼）
    btn.style.backgroundColor = hexToRgba(grade.color, 0.15);
    btn.style.border = `1px solid ${hexToRgba(grade.color, 0.45)}`;

    if (state.performanceGrade === grade.name) btn.classList.add("selected");

    btn.addEventListener("click", () => {
      state.performanceGrade = grade.name;
      renderPerformanceGrades();
    });

    performanceListEl.appendChild(btn);
  });
}

// 重置績效評等
function resetPerformanceGrades() {
  state.performanceGrade = null;
  renderPerformanceGrades();
}

// 自訂特質功能
function addCustomTrait() {
  const value = (customTraitInputEl?.value || "").trim();
  if (!value) return;

  if (state.customTraits.length >= 10) {
    alert("自訂指標最多 10 個！");
    return;
  }

  if (state.traits.includes(value)) {
    alert("此指標已存在，請選擇其他特質！");
    return;
  }

  state.customTraits.push(value);
  state.traits.push(value);

  if (customTraitInputEl) customTraitInputEl.value = "";
  if (customTraitCountEl) customTraitCountEl.textContent = String(state.customTraits.length);

  renderCustomTraits();
  renderTraits();
}

function clearCustomTraits() {
  // ✅ 修正：先找出要移除的 selected，再清空 customTraits
  const toRemoveSelected = Array.from(state.selectedTraits).filter(t => state.customTraits.includes(t));

  // 從主特質列表移除所有自訂特質
  state.traits = state.traits.filter(t => !state.customTraits.includes(t));
  state.customTraits = [];

  // 清空已選中的自訂特質
  toRemoveSelected.forEach(t => state.selectedTraits.delete(t));

  if (customTraitCountEl) customTraitCountEl.textContent = "0";
  renderCustomTraits();
  renderTraits();
  renderSelectedTraits();
}

// 顯示自訂特質
function renderCustomTraits() {
  if (!customTraitListEl) return;
  customTraitListEl.innerHTML = "";
  if (state.customTraits.length === 0) return;

  state.customTraits.forEach((trait, index) => {
    const span = document.createElement("span");
    span.className = "pill";
    span.textContent = trait;
    span.title = `第 ${index + 1} 個自訂指標`;
    customTraitListEl.appendChild(span);
  });
}

// 人員按鈕功能
function generateStudentButtons() {
  const raw = (studentListEl?.value || "");
  const lines = raw.split("\n").map(l => l.trim()).filter(Boolean);

  if (lines.length === 0) {
    alert("請輸入人員列表！");
    return;
  }

  if (studentButtonsEl) studentButtonsEl.innerHTML = "";
  state.currentStudent = null;

  lines.forEach((line) => {
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

  const firstBtn = studentButtonsEl?.firstElementChild;
  if (firstBtn) {
    state.currentStudent = lines[0];
    firstBtn.classList.add("active");
  }
}

// 生成評語（整合 LLM API）
async function generateComment() {
  if (!state.currentStudent) {
    alert("請先選擇人員！");
    return;
  }
  if (state.selectedTraits.size === 0 && !state.performanceGrade) {
    alert("請至少選擇一個維度或評等！");
    return;
  }

  const namePart = (state.currentStudent.split(".")[1] || state.currentStudent).trim();
  const traitsArr = Array.from(state.selectedTraits);
  const grade = state.performanceGrade;

  // 顯示 loading 狀態
  const loadingItem = { student: state.currentStudent, comment: "⏳ 生成中，請稍候..." };
  state.comments.unshift(loadingItem);
  renderComments();

  try {
    const performanceInfo = grade ? `績效評等: ${grade}` : "未指定績效評等";
    const prompt = [
      `同仁姓名: ${namePart}`,
      `${performanceInfo}`,
      `以下是同仁表現特質:`,
      ...traitsArr.map(t => `- ${t}`),
      `請將上述同仁表現以軍事風格撰寫評語，字數嚴格限制不得超過80中文字。`
    ].join("\n");

    // ✅ 反向代理安全：用 resolveApiUrl
    const apiUrl = resolveApiUrl("/api/chat/");

    const response = await fetch(apiUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        max_tokens: 80,
        temperature: 0.7,
        presence_penalty: 1.2,
        frequency_penalty: 1.5
      })
    });

    if (!response.ok) {
      throw new Error(`伺服器錯誤: ${response.status}`);
    }

    const data = await response.json();
    loadingItem.comment = (data && data.reply) ? data.reply : "（無回應內容）";
    renderComments();

  } catch (error) {
    console.error("生成評語失敗:", error);
    loadingItem.comment = `❌ 生成失敗: ${error.message || String(error)}`;
    renderComments();
  }
}

// 渲染評語預覽
function renderComments() {
  if (!commentPreviewEl) return;
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

// 文件匯出功能 - TXT
function downloadTxt() {
  if (state.comments.length === 0) return alert("無記錄可匯出");

  const lines = state.comments.map(c => `${c.student}\t${c.comment}`);
  const blob = new Blob([lines.join("\n")], { type: "text/plain" });
  const url = URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = `人員考核評語_${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// 文件匯出功能 - CSV
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
  a.download = `人員考核評語_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// 重置所有功能
function resetAll() {
  if (!confirm("確定要清除所有設定？")) return;

  state.traits = [
    ...thoughtCharacteristics,
    ...characterCharacteristics,
    ...performanceCharacteristics,
    ...abilityCharacteristics,
    ...knowledgeCharacteristics,
    ...specialNotes
  ];
  state.selectedTraits = new Set();
  state.customTraits = [];
  state.comments = [];
  state.currentStudent = null;
  state.performanceGrade = null;

  if (studentListEl) studentListEl.value = "";
  if (customTraitCountEl) customTraitCountEl.textContent = "0";

  renderCustomTraits();
  renderTraits();
  renderSelectedTraits();
  renderPerformanceGrades();
  if (studentButtonsEl) studentButtonsEl.innerHTML = "";
  renderComments();
}

// 重置維度選擇
function resetTraits() {
  state.selectedTraits = new Set();
  renderTraits();
  renderSelectedTraits();
}

// 匯入人員名單功能
function importFile() {
  document.getElementById("importFileInput")?.click();
}

function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  let contentType = "";

  switch (file.name.split(".").pop().toLowerCase()) {
    case "txt": contentType = "text/plain"; break;
    case "csv":
      contentType = "text/csv";
      if (!confirm("建議使用TXT格式檔案，是否繼續？")) return;
      break;
    default:
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

      if (studentListEl) studentListEl.value = lines.join("\n");
    } else {
      if (studentListEl) studentListEl.value = content;
    }
    generateStudentButtons();
  };

  reader.onerror = function () {
    alert("讀取檔案時出錯");
  };

  reader.readAsText(file);
}

// 清除記錄功能
function clearComments() {
  if (!confirm("確定要清除所有評語記錄？")) return;
  state.comments = [];
  renderComments();
}

// 當頁面載入時初始化
window.addEventListener("DOMContentLoaded", init);

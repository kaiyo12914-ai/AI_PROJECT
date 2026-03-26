const API_FETCH = apiurl("fetch/");
const API_PLAN = apiurl("plan/");

const $ = (id) => document.getElementById(id);

const refs = {
  sourceUrl: $("sourceUrl"),
  todos: $("todos"),
  availableSlots: $("availableSlots"),
  userPreferences: $("userPreferences"),
  currentDate: $("currentDate"),
  planOut: $("planOut"),
  fetchStatus: $("fetchStatus"),
  planStatus: $("planStatus"),
  btnFetch: $("btnFetch"),
  btnPlan: $("btnPlan"),
  btnCopy: $("btnCopy"),
  btnDownload: $("btnDownload"),
};

function setFetchStatus(msg, level = "") {
  refs.fetchStatus.classList.remove("ok", "err");
  if (level) refs.fetchStatus.classList.add(level);
  refs.fetchStatus.textContent = msg || "";
}

function setPlanStatus(msg, level = "") {
  refs.planStatus.classList.remove("ok", "err");
  if (level) refs.planStatus.classList.add(level);
  refs.planStatus.textContent = msg || "";
}

async function fetchTodos() {
  const sourceUrl = (refs.sourceUrl.value || "").trim();
  if (!sourceUrl) {
    alert("請先輸入待辦來源 URL");
    return;
  }

  refs.btnFetch.disabled = true;
  setFetchStatus("讀取中...");
  try {
    const qs = new URLSearchParams({ source_url: sourceUrl });
    const resp = await fetch(`${API_FETCH}?${qs.toString()}`, { method: "GET" });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    refs.todos.value = data.todos_text || "";
    setFetchStatus(`取得完成，共 ${data.count || 0} 筆`, "ok");
  } catch (err) {
    setFetchStatus(`讀取失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.btnFetch.disabled = false;
  }
}

async function planTasks() {
  const todos = (refs.todos.value || "").trim();
  if (!todos) {
    alert("請先取得或填入待辦事項");
    return;
  }

  refs.btnPlan.disabled = true;
  setPlanStatus("分析中...");
  refs.planOut.value = "";
  try {
    const payload = {
      todos,
      available_slots: (refs.availableSlots.value || "").trim(),
      user_preferences: (refs.userPreferences.value || "").trim(),
      current_date: (refs.currentDate.value || "").trim(),
    };
    const resp = await fetch(API_PLAN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    refs.planOut.value = data.plan_text || "";
    setPlanStatus(data.fallback ? "分析完成（備援模式）" : "分析完成", "ok");
  } catch (err) {
    setPlanStatus(`分析失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.btnPlan.disabled = false;
  }
}

async function copyOut() {
  const text = refs.planOut.value || "";
  if (!text.trim()) {
    alert("目前沒有可複製的內容");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    setPlanStatus("已複製到剪貼簿", "ok");
  } catch {
    refs.planOut.focus();
    refs.planOut.select();
    document.execCommand("copy");
    setPlanStatus("已複製到剪貼簿", "ok");
  }
}

function downloadOut() {
  const text = refs.planOut.value || "";
  if (!text.trim()) {
    alert("目前沒有可下載的內容");
    return;
  }

  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `todo_plan_${Date.now()}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 800);
}

refs.btnFetch?.addEventListener("click", fetchTodos);
refs.btnPlan?.addEventListener("click", planTasks);
refs.btnCopy?.addEventListener("click", copyOut);
refs.btnDownload?.addEventListener("click", downloadOut);


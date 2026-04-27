const API_FETCH = apiurl("fetch/");
const API_PLAN = apiurl("plan/");

const $ = (id) => document.getElementById(id);

const refs = {
  todos: $("todos"),
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

function normalizeTodosText(data) {
  if (typeof data.todos_text === "string" && data.todos_text.trim()) {
    return data.todos_text;
  }
  if (Array.isArray(data.todos_raw)) {
    return JSON.stringify(data.todos_raw, null, 2);
  }
  return "[]";
}

async function fetchTodos() {
  refs.btnFetch.disabled = true;
  setFetchStatus("讀取中...");
  try {
    const resp = await fetch(API_FETCH, { method: "GET" });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }

    refs.todos.value = normalizeTodosText(data);
    refs.planOut.value = data.warning_text || "";
    setFetchStatus(`讀取完成，共 ${data.count || 0} 筆（已排除宣教宣導）`, "ok");
    setPlanStatus(`已產生 ${data.warning_count || 0} 筆到期警示`, "ok");
  } catch (err) {
    setFetchStatus(`讀取失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.btnFetch.disabled = false;
  }
}

async function planTasks() {
  const todos = (refs.todos.value || "").trim();
  if (!todos) {
    alert("請先取得待辦 JSON。");
    return;
  }

  refs.btnPlan.disabled = true;
  setPlanStatus("產生中...");
  refs.planOut.value = "";
  try {
    // Validate JSON in client side first for quick feedback.
    JSON.parse(todos);

    const resp = await fetch(API_PLAN, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ todos_json: todos }),
    });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }

    refs.planOut.value = data.plan_text || "";
    setPlanStatus(`完成，共 ${data.warning_count || 0} 筆到期警示`, "ok");
  } catch (err) {
    setPlanStatus(`產生失敗：${err.message || "未知錯誤"}`, "err");
  } finally {
    refs.btnPlan.disabled = false;
  }
}

async function copyOut() {
  const text = refs.planOut.value || "";
  if (!text.trim()) {
    alert("目前沒有可複製內容。");
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
    alert("目前沒有可下載內容。");
    return;
  }

  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `todo_warning_${Date.now()}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 800);
}

refs.btnFetch?.addEventListener("click", fetchTodos);
refs.btnPlan?.addEventListener("click", planTasks);
refs.btnCopy?.addEventListener("click", copyOut);
refs.btnDownload?.addEventListener("click", downloadOut);

import re

with open('webapps/projectnotes/static/projectnotes/js/index.js', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace uploadSource()
old_upload_source = """  async function uploadSource() {
    if (!state.isManagePage || !state.canManageProjects) return;
    if (!state.projectId || state.busy || !els.sourceFile || !els.sourceTitle) return;

    const file = els.sourceFile.files[0];
    if (!file) {
      setStatus("沒有選擇檔案", true);
      return;
    }

    const title = (els.sourceTitle.value || "").trim() || file.name;
    setBusy(true);

    const fd = new FormData();
    fd.append("project_id", String(state.projectId));
    fd.append("title", title);
    fd.append("file", file);

    const resp = await fetch(url("/projectnotes/sources/"), { method: "POST", body: fd });
    const data = await parseJsonSafe(resp);

    setBusy(false);

    if (!data.ok) {
      setStatus(data.error || "Upload failed.", true);
      return;
    }

    els.sourceFile.value = "";
    els.sourceTitle.value = "";

    await loadSources();
    await loadOverview();
    await loadConversations(state.conversationId);

    if (data.is_non_utf8 && data.detected_encoding) {
      setStatus(`Upload complete. Detected encoding: ${data.detected_encoding}`, false);
    } else {
      setStatus("Upload complete.", false);
    }
  }"""

new_upload_source = """  async function uploadSource() {
    if (!state.isManagePage || !state.canManageProjects) return;
    if (!state.projectId || state.busy || !els.sourceFile || !els.sourceTitle) return;

    const file = els.sourceFile.files[0];
    if (!file) {
      setStatus("沒有選擇檔案", true);
      return;
    }

    const title = (els.sourceTitle.value || "").trim() || file.name;
    setBusy(true);

    const fd = new FormData();
    fd.append("project_id", String(state.projectId));
    fd.append("title", title);
    fd.append("file", file);

    setStatus("上傳中...", false);
    const resp = await fetch(url("/projectnotes/sources/"), { method: "POST", body: fd });
    const data = await parseJsonSafe(resp);

    if (!data.ok) {
      setBusy(false);
      setStatus(data.error || "Upload failed.", true);
      return;
    }

    els.sourceFile.value = "";
    els.sourceTitle.value = "";

    if (data.job_id) {
      pollJobStatus(data.job_id);
    } else {
      setBusy(false);
      await loadSources();
      await loadOverview();
      await loadConversations(state.conversationId);
      setStatus("Upload complete.", false);
    }
  }

  async function pollJobStatus(jobId) {
    if (!jobId) return;
    try {
      const resp = await fetch(url(`/projectnotes/jobs/${jobId}/`));
      const data = await parseJsonSafe(resp);
      
      if (!data.ok) {
        setBusy(false);
        setStatus(data.error || "Failed to get job status.", true);
        return;
      }
      
      if (data.status === "failed") {
        setBusy(false);
        setStatus("背景處理失敗: " + data.error_message, true);
        return;
      }
      
      if (data.status === "completed") {
        setBusy(false);
        setStatus("處理完成！", false);
        await loadSources();
        await loadOverview();
        await loadConversations(state.conversationId);
        return;
      }
      
      // Still processing
      setStatus("處理中: " + data.progress_info, false);
      setTimeout(() => pollJobStatus(jobId), 1500);
      
    } catch (e) {
      setBusy(false);
      setStatus("Polling error: " + e, true);
    }
  }"""

if old_upload_source in content:
    content = content.replace(old_upload_source, new_upload_source)
    with open('webapps/projectnotes/static/projectnotes/js/index.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced uploadSource successfully.")
else:
    print("Could not find old_upload_source in index.js")

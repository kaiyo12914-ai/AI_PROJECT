import re

with open('webapps/projectnotes/static/projectnotes/js/index.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add auditLogPanel to els
content = content.replace(
    'chunkLogPanel: document.getElementById("chunkLogPanel"),',
    'chunkLogPanel: document.getElementById("chunkLogPanel"),\n    auditLogPanel: document.getElementById("auditLogPanel"),'
)

# 2. Add loadAuditLogs function before loadProjects or similar
audit_log_js = """  async function loadAuditLogs() {
    if (!state.isManagePage || !els.auditLogPanel) return;
    const resp = await fetch(url("/projectnotes/audit_logs/"));
    const data = await parseJsonSafe(resp);
    if (!data.ok) {
      els.auditLogPanel.textContent = "無法讀取日誌。";
      return;
    }
    const rows = Array.isArray(data.rows) ? data.rows : [];
    if (!rows.length) {
      els.auditLogPanel.textContent = "尚無操作日誌。";
      return;
    }
    els.auditLogPanel.innerHTML = rows.map(r => {
      const dt = r.created_at ? r.created_at.replace("T", " ").split(".")[0] : "-";
      return `<div style="border-bottom:1px solid #eee; padding:4px 0; font-size:12px;">` +
             `[${dt}] <b>${r.user_id}</b>: ${r.action} (${r.target_type}#${r.target_id || ""}) - ${r.status}</div>`;
    }).join("");
  }
"""

if "async function loadProjects()" in content:
    content = content.replace("async function loadProjects()", audit_log_js + "\n  async function loadProjects()")

# 3. Call loadAuditLogs in loadProjects success
if "setStatus(\"讀取專案清單成功\", false);" in content:
    content = content.replace("setStatus(\"讀取專案清單成功\", false);", "setStatus(\"讀取專案清單成功\", false);\n      if (state.isManagePage) loadAuditLogs();")

with open('webapps/projectnotes/static/projectnotes/js/index.js', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated index.js with Audit Logs logic")

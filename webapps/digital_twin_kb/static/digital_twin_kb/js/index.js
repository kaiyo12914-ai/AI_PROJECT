/* webapps/digital_twin_kb/static/digital_twin_kb/js/index.js */
document.addEventListener("DOMContentLoaded", () => {
  // 基礎變數與 UI 綁定
  const csrfToken = document.getElementById("csrf_token")?.value || "";
  const chatInput = document.getElementById("chat-input");
  const btnSendChat = document.getElementById("btn-send-chat");
  const btnDirectIngest = document.getElementById("btn-direct-ingest");
  const chatFlow = document.getElementById("chat-flow");
  const btnToggleConfig = document.getElementById("btn-toggle-config");
  const chatConfigPanel = document.getElementById("chat-config-panel");
  const topKSelect = document.getElementById("top_k_select");
  const topKValue = document.getElementById("top_k_value");
  const secLevelSelect = document.getElementById("sec_level_select");
  const secLevelValue = document.getElementById("sec_level_value");
  const topicFilter = document.getElementById("topic_filter");

  // Ingest 與管理綁定
  const btnIngestFolder = document.getElementById("btn-ingest-folder");
  const uploadForm = document.getElementById("upload-form");
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");
  const selectedFileInfo = document.getElementById("selected-file-info");
  const fileNameDisplay = document.getElementById("file-name-display");
  const btnCancelFile = document.getElementById("btn-cancel-file");
  const btnSubmitUpload = document.getElementById("btn-submit-upload");
  const uploadTopic = document.getElementById("upload-topic");
  const uploadSecLevel = document.getElementById("upload-sec-level");

  // Job 狀態與資料表綁定
  const jobStatusPanel = document.getElementById("job-status-panel");
  const jobProgressBar = document.getElementById("job-progress-bar");
  const jobStatusBadge = document.getElementById("job-status-badge");
  const jobProgressDesc = document.getElementById("job-progress-desc");
  const categoriesContainer = document.getElementById("categories-container");
  const documentsTableBody = document.getElementById("documents-table-body");
  const btnRefreshDocs = document.getElementById("btn-refresh-docs");

  // 歷史 RAG 問答紀錄綁定
  const qaLogsTableBody = document.getElementById("qa-logs-table-body");
  const btnRefreshQa = document.getElementById("btn-refresh-qa");

  // Modal 綁定
  const chunksModal = document.getElementById("chunks-modal");
  const btnCloseModal = document.getElementById("btn-close-modal");
  const modalDocTitle = document.getElementById("modal-doc-title");
  const modalChunksContainer = document.getElementById("modal-chunks-container");

  let activePollInterval = null;

  // apiurl helper (基於 apiurl_factory.js 提供的 base-url)
  function getApiUrl(path) {
    if (typeof window.apiurl === "function") {
      return window.apiurl(path);
    }
    // Fallback: 讀取 dataset
    const base = document.body.dataset.baseUrl || "";
    const cleanPath = path.startsWith("/") ? path : "/" + path;
    return base + cleanPath;
  }

  // ==========================================
  // 1. UI 互動與配置展開
  // ==========================================
  btnToggleConfig.addEventListener("click", () => {
    chatConfigPanel.classList.toggle("hidden");
  });

  topKSelect.addEventListener("input", (e) => {
    topKValue.textContent = e.target.value;
  });

  secLevelSelect.addEventListener("input", (e) => {
    secLevelValue.textContent = e.target.value;
  });

  // 自動調整 Textarea 高度
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
  });

  // ==========================================
  // 2. RAG 智能問答
  // ==========================================
  function appendMessage(content, type, sources = []) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${type}-message`;

    let sourcesHtml = "";
    // 依使用者要求，依據來源 (Chunks) 均免列出，避免佔過多版面

    bubble.innerHTML = `
      <div class="bubble-content">
        ${formatMarkdown(content)}
        ${sourcesHtml}
      </div>
      <span class="bubble-time">${type === "user" ? "使用者" : "AI 助手"}</span>
    `;

    chatFlow.appendChild(bubble);
    chatFlow.scrollTop = chatFlow.scrollHeight;
  }

  function handleSendChat() {
    const question = chatInput.value.trim();
    if (!question) return;

    chatInput.value = "";
    chatInput.style.height = "auto";

    // 1. 渲染使用者對話泡泡
    appendMessage(question, "user");

    // 2. 渲染等待狀態
    const waitingBubble = document.createElement("div");
    waitingBubble.className = "chat-bubble bot-message";
    waitingBubble.innerHTML = `
      <div class="bubble-content">
        <div class="loading-spinner">檢索 RAG知識庫中</div>
      </div>
      <span class="bubble-time">AI 助手</span>
    `;
    chatFlow.appendChild(waitingBubble);
    chatFlow.scrollTop = chatFlow.scrollHeight;

    // 3. 發送 API 請求
    const payload = {
      question: question,
      top_k: parseInt(topKSelect.value),
      user_security_level: parseInt(secLevelSelect.value),
      filters: {}
    };

    const topicVal = topicFilter.value.trim();
    if (topicVal) {
      payload.filters.topic = topicVal;
    }

    fetch(getApiUrl("digital-twin-kb/api/ask/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      },
      body: JSON.stringify(payload)
    })
      .then((res) => {
        if (!res.ok) throw new Error("對話 API 錯誤");
        return res.json();
      })
      .then((data) => {
        waitingBubble.remove();
        appendMessage(data.answer, "bot", data.sources || []);
        // 對話完畢後自動重新載入歷史問答紀錄
        loadQaLogs();
      })
      .catch((err) => {
        waitingBubble.remove();
        appendMessage("檢索失敗或連線逾時，請檢查環境設定是否支援 LLM。", "bot");
      });
  }

  btnSendChat.addEventListener("click", handleSendChat);
  btnDirectIngest.addEventListener("click", handleDirectIngest);
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendChat();
    }
  });

  // ==========================================
  // 3. 一鍵批量匯入預設資料夾
  // ==========================================
  btnIngestFolder.addEventListener("click", () => {
    if (!confirm("確定要掃描伺服器預設資料夾並執行 pgvector Ingestion 嗎？這需要數十秒至數分鐘。")) {
      return;
    }

    btnIngestFolder.disabled = true;
    btnIngestFolder.innerHTML = `<span class="loading-spinner">匯入處理中...</span>`;

    fetch(getApiUrl("digital-twin-kb/api/ingest/"), {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken
      }
    })
      .then((res) => {
        if (!res.ok) throw new Error("匯入觸發失敗");
        return res.json();
      })
      .then((data) => {
        alert("已經成功建立後台 Ingestion 工作！您可以隨時監控進度。");
        // 開始輪詢進度
        showJobProgress(data.job_id);
      })
      .catch((err) => {
        alert("批量匯入失敗：" + err.message);
      })
      .finally(() => {
        btnIngestFolder.disabled = false;
        btnIngestFolder.innerHTML = `
          <svg viewBox="0 0 24 24" class="btn-icon"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" fill="none" stroke="currentColor" stroke-width="2"/></svg>
          一鍵批量匯入資料夾
        `;
      });
  });

  // ==========================================
  // 4. 單檔上傳互動與 API 上傳
  // ==========================================
  dropZone.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) {
      handleSelectedFile(file);
    }
  });

  // 拖拽事件
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    }, false);
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    }, false);
  });

  dropZone.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    const file = dt.files[0];
    if (file && file.name.endsWith(".pdf")) {
      fileInput.files = dt.files;
      handleSelectedFile(file);
    } else {
      alert("只支援上傳 PDF 格式的文件！");
    }
  });

  function handleSelectedFile(file) {
    fileNameDisplay.textContent = `${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB)`;
    selectedFileInfo.classList.remove("hidden");
    dropZone.classList.add("hidden");
    btnSubmitUpload.disabled = false;
  }

  btnCancelFile.addEventListener("click", () => {
    fileInput.value = "";
    selectedFileInfo.classList.add("hidden");
    dropZone.classList.remove("hidden");
    btnSubmitUpload.disabled = true;
  });

  uploadForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) return;

    btnSubmitUpload.disabled = true;
    btnSubmitUpload.textContent = "上傳並解析中...";

    const formData = new FormData();
    formData.append("file", file);
    formData.append("topic", uploadTopic.value.trim());
    formData.append("security_level", parseInt(uploadSecLevel.value));
    formData.append("uploaded_by", "管理者");

    fetch(getApiUrl("digital-twin-kb/api/upload/"), {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken
      },
      body: formData
    })
      .then((res) => {
        if (!res.ok) throw new Error("文件上傳失敗");
        return res.json();
      })
      .then((data) => {
        alert("文件上傳並切割 Ingest 成功！");
        // 恢復上傳表單
        btnCancelFile.click();
        uploadTopic.value = "";
        // 重新載入統計與文檔列表
        loadStats();
        loadDocuments();
      })
      .catch((err) => {
        alert("上傳失敗：" + err.message);
      })
      .finally(() => {
        btnSubmitUpload.disabled = false;
        btnSubmitUpload.textContent = "確認並解析文件";
      });
  });

  // ==========================================
  // 5. 後台工作狀態輪詢 (Job Polling)
  // ==========================================
  function showJobProgress(jobId) {
    if (activePollInterval) clearInterval(activePollInterval);

    jobStatusPanel.classList.remove("hidden");

    function poll() {
      fetch(getApiUrl(`digital-twin-kb/api/ingestion-jobs/${jobId}/`))
        .then((res) => res.json())
        .then((data) => {
          const status = data.status.toLowerCase();
          const progress = data.progress || 0;

          jobProgressBar.style.width = `${progress}%`;
          jobStatusBadge.className = `badge ${status}`;
          jobStatusBadge.textContent = data.status;

          let desc = `目前進度: ${progress}% - ${data.error_message || "正在提取文字並寫入 pgvector 向量..."}`;
          jobProgressDesc.textContent = desc;

          if (status === "completed" || status === "failed") {
            clearInterval(activePollInterval);
            setTimeout(() => {
              jobStatusPanel.classList.add("hidden");
              loadStats();
              loadDocuments();
            }, 3000);
          }
        })
        .catch(() => {
          clearInterval(activePollInterval);
        });
    }

    poll();
    activePollInterval = setInterval(poll, 2000);
  }

  // 檢查是否有正在進行的 active jobs
  function checkActiveJobs() {
    fetch(getApiUrl("digital-twin-kb/api/ingestion-jobs/"))
      .then((res) => res.json())
      .then((data) => {
        if (data && data.length > 0) {
          // 尋找處理中的第一個 job
          const running = data.find(j => j.status === "PROCESSING" || j.status === "PENDING");
          if (running) {
            showJobProgress(running.job_id);
          }
        }
      });
  }

  // ==========================================
  // 6. 統計、文檔庫、歷史紀錄加載
  // ==========================================
  function loadStats() {
    fetch(getApiUrl("digital-twin-kb/api/categories/"))
      .then((res) => res.json())
      .then((data) => {
        categoriesContainer.innerHTML = "";
        if (!data || data.length === 0) {
          categoriesContainer.innerHTML = `<div class="font-muted text-center" style="grid-column:1/-1;">尚無層級統計資料</div>`;
          return;
        }

        data.forEach((cat) => {
          const card = document.createElement("div");
          card.className = "category-mini-card";
          card.innerHTML = `
            <div class="cat-level">LEVEL ${cat.twin_level}</div>
            <div class="cat-count">${cat.doc_count || 0}</div>
            <div class="cat-desc">${escapeHtml(cat.name)}</div>
          `;
          categoriesContainer.appendChild(card);
        });
      })
      .catch(() => {
        categoriesContainer.innerHTML = `<div class="text-center font-muted">加載統計失敗</div>`;
      });
  }

  function loadDocuments() {
    documentsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted">載入中...</td></tr>`;

    fetch(getApiUrl("digital-twin-kb/api/documents/"))
      .then((res) => res.json())
      .then((data) => {
        documentsTableBody.innerHTML = "";
        if (!data || data.length === 0) {
          documentsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted">知識庫目前是空的</td></tr>`;
          return;
        }

        data.forEach((doc) => {
          const tr = document.createElement("tr");

          const dateStr = doc.created_at ? new Date(doc.created_at).toLocaleString() : "未知";
          const scoreLevel = doc.security_level || 1;
          const displayTitle = doc.original_file_name || doc.file_name || "無標題";

          tr.innerHTML = `
            <td>
              <a class="dt-table-link doc-title-btn" data-id="${doc.document_id}" data-title="${escapeHtml(displayTitle)}">
                ${escapeHtml(displayTitle)}
              </a>
            </td>
            <td>${escapeHtml(doc.topic || "一般")}</td>
            <td>等級 ${scoreLevel}</td>
            <td>Level ${doc.twin_level || "未分類"}</td>
            <td>${dateStr}</td>
          `;
          documentsTableBody.appendChild(tr);
        });

        // 綁定查看 Chunks 彈窗事件
        document.querySelectorAll(".doc-title-btn").forEach((btn) => {
          btn.addEventListener("click", (e) => {
            const docId = btn.getAttribute("data-id");
            const docTitle = btn.getAttribute("data-title");
            openChunksModal(docId, docTitle);
          });
        });
      })
      .catch(() => {
        documentsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted" style="color:#ff5252">載入文檔庫失敗</td></tr>`;
      });
  }

  // 載入歷史 RAG 問答紀錄
  function loadQaLogs() {
    qaLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted">載入問答紀錄中...</td></tr>`;

    fetch(getApiUrl("digital-twin-kb/api/qa-logs/"))
      .then((res) => res.json())
      .then((data) => {
        qaLogsTableBody.innerHTML = "";
        if (!data || data.length === 0) {
          qaLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted">尚無歷史問答紀錄</td></tr>`;
          return;
        }

        data.forEach((log) => {
          const tr = document.createElement("tr");
          const dateStr = log.created_at ? new Date(log.created_at).toLocaleString() : "未知";
          const shortQ = log.user_question.length > 22 ? log.user_question.substring(0, 22) + "..." : log.user_question;
          const chunksCount = log.retrieved_chunks ? log.retrieved_chunks.length : 0;

          tr.innerHTML = `
            <td>
              <a class="dt-table-link qalog-review-btn" data-id="${log.query_id}" title="點擊載入此次對話歷史">
                ${escapeHtml(shortQ)}
              </a>
            </td>
            <td>${escapeHtml(log.asker_id || "anonymous")}</td>
            <td>${chunksCount} 個 Chunks</td>
            <td>${dateStr}</td>
            <td class="text-center">
              <button class="btn-ingest-qa-row" data-id="${log.query_id}" title="手動將此問答存入知識庫">
                📥 存入 RAG
              </button>
              <button class="btn-delete-qa-row" data-id="${log.query_id}" title="刪除此筆問答紀錄">
                🗑️ 刪除
              </button>
            </td>
          `;
          qaLogsTableBody.appendChild(tr);
        });

        // 綁定歷史對話載入事件
        document.querySelectorAll(".qalog-review-btn").forEach((btn) => {
          btn.addEventListener("click", (e) => {
            const logId = btn.getAttribute("data-id");
            reviewQaLog(logId);
          });
        });

        // 綁定手動回存知識庫事件
        document.querySelectorAll(".btn-ingest-qa-row").forEach((btn) => {
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const logId = btn.getAttribute("data-id");
            ingestQaLogToKb(logId, btn);
          });
        });

        // 綁定刪除紀錄事件
        document.querySelectorAll(".btn-delete-qa-row").forEach((btn) => {
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const logId = btn.getAttribute("data-id");
            if (confirm("確定要刪除此筆問答紀錄嗎？")) {
              deleteQaLog(logId, btn);
            }
          });
        });
      })
      .catch(() => {
        qaLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-center font-muted" style="color:#ff5252">載入歷史紀錄失敗</td></tr>`;
      });
  }

  // 手動回存問答紀錄至 RAG 知識庫
  function ingestQaLogToKb(logId, btn) {
    btn.disabled = true;
    const oldText = btn.innerHTML;
    btn.innerHTML = "⏳ 處理中...";

    fetch(getApiUrl("digital-twin-kb/api/ingest-qa-log/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      },
      body: JSON.stringify({ query_id: logId })
    })
      .then((res) => {
        if (!res.ok) throw new Error("回存失敗");
        return res.json();
      })
      .then((data) => {
        alert(data.message || "成功將對話紀錄手動回存至知識庫！");
        // 重新載入文檔庫與統計
        loadDocuments();
        loadStats();
      })
      .catch((err) => {
        alert("回存知識庫失敗：" + err.message);
      })
      .finally(() => {
        btn.disabled = false;
        btn.innerHTML = oldText;
      });
  }

  // 刪除問答紀錄
  function deleteQaLog(logId, btn) {
    btn.disabled = true;
    const oldText = btn.innerHTML;
    btn.innerHTML = "🗑️ 刪除中...";

    fetch(getApiUrl(`digital-twin-kb/api/qa-logs/${logId}/`), {
      method: "DELETE",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      }
    })
      .then((res) => {
        if (res.ok || res.status === 204) {
          alert("成功刪除該筆問答紀錄！");
          loadQaLogs();
        } else {
          throw new Error("刪除失敗");
        }
      })
      .catch((err) => {
        alert("刪除問答紀錄失敗：" + err.message);
        btn.disabled = false;
        btn.innerHTML = oldText;
      });
  }

  // 回溯與還原歷史對話
  function reviewQaLog(logId) {
    fetch(getApiUrl(`digital-twin-kb/api/qa-logs/${logId}/`))
      .then((res) => res.json())
      .then((data) => {
        // 清空對話流並渲染歷史對話標記
        chatFlow.innerHTML = `
          <div class="chat-bubble bot-message">
            <div class="bubble-content">
              已成功載入歷史問答紀錄 (ID: #${data.query_id}，提問者: **${escapeHtml(data.asker_id || "anonymous")}**)。
              <br><br>
              這是該次檢索對話的還原狀態。
            </div>
            <span class="bubble-time">AI 助手 (歷史回溯)</span>
          </div>
        `;

        // 還原使用者當時的提問
        appendMessage(data.user_question, "user");

        // 還原當時的回答與引用的 Chunks 來源
        appendMessage(data.answer, "bot", data.cited_sources || []);
      })
      .catch(() => {
        alert("無法載入該筆歷史問答記錄，請確認資料是否依然存在！");
      });
  }

  btnRefreshDocs.addEventListener("click", () => {
    loadStats();
    loadDocuments();
  });

  btnRefreshQa.addEventListener("click", () => {
    loadQaLogs();
  });

  // ==========================================
  // 7. Chunks 彈窗模態框 (Modal)
  // ==========================================
  function openChunksModal(docId, docTitle) {
    modalDocTitle.textContent = `文檔切片：《${docTitle}》`;
    modalChunksContainer.innerHTML = `<div class="loading-spinner">載入 Chunk 切片中...</div>`;
    chunksModal.classList.remove("hidden");

    fetch(getApiUrl(`digital-twin-kb/api/documents/${docId}/chunks/`))
      .then((res) => res.json())
      .then((data) => {
        modalChunksContainer.innerHTML = "";
        if (!data || data.length === 0) {
          modalChunksContainer.innerHTML = `<div class="text-center font-muted">此文檔無任何 Chunk 切片</div>`;
          return;
        }

        data.forEach((chunk) => {
          const card = document.createElement("div");
          card.className = "modal-chunk-card";
          card.innerHTML = `
            <div class="chunk-card-meta">
              <span>切片索引: #${chunk.chunk_index}</span>
              <span>雙生層級: Level ${chunk.twin_level || "未分類"}</span>
            </div>
            <div class="chunk-card-content">${escapeHtml(chunk.content)}</div>
          `;
          modalChunksContainer.appendChild(card);
        });
      })
      .catch(() => {
        modalChunksContainer.innerHTML = `<div class="text-center font-muted" style="color:#ff5252">載入 Chunks 失敗</div>`;
      });
  }

  btnCloseModal.addEventListener("click", () => {
    chunksModal.classList.add("hidden");
  });

  window.addEventListener("click", (e) => {
    if (e.target === chunksModal) {
      chunksModal.classList.add("hidden");
    }
  });

  // ==========================================
  // 8. 輔助函數 (Escape & Markdown)
  // ==========================================
  function escapeHtml(text) {
    if (!text) return "";
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatMarkdown(text) {
    if (!text) return "";
    let formatted = escapeHtml(text);
    // 粗體
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    // 換行
    formatted = formatted.replace(/\n/g, "<br>");
    return formatted;
  }

  // 直接將輸入框文字存入 RAG 知識庫
  function handleDirectIngest() {
    const text = chatInput.value.trim();
    if (!text) {
      alert("請先在對話框中輸入您想要直接寫入 RAG 知識庫的內容！");
      return;
    }

    if (!confirm("確定要將輸入框中的這段文字，計算向量並「直接存入 RAG 知識庫」中嗎？\n\n(此操作不會呼叫 LLM 進行問答)")) {
      return;
    }

    btnDirectIngest.disabled = true;
    const oldText = btnDirectIngest.innerHTML;
    btnDirectIngest.innerHTML = "⏳ 正在直接存入 RAG...";

    fetch(getApiUrl("digital-twin-kb/api/direct-ingest-text/"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken
      },
      body: JSON.stringify({ text: text })
    })
      .then((res) => {
        if (!res.ok) throw new Error("存入失敗");
        return res.json();
      })
      .then((data) => {
        alert(data.message || "成功將內容直接存入 RAG 知識庫！");
        chatInput.value = ""; // 清空輸入框
        chatInput.style.height = "auto";
        loadDocuments();
        loadStats();
      })
      .catch((err) => {
        alert("存入失敗：" + err.message);
      })
      .finally(() => {
        btnDirectIngest.disabled = false;
        btnDirectIngest.innerHTML = oldText;
      });
  }

  // ==========================================
  // 初始化加載
  // ==========================================
  loadStats();
  loadDocuments();
  loadQaLogs(); // 👈 初始化加載歷史問答紀錄
  checkActiveJobs();
});

(function () {
  "use strict";

  const state = {
    topic: "",
    level: "beginner",
    mode: "chat",
    messages: [],
    quiz: null,
    reorder: null,
    reorderPicked: [],
    translation: null,
    attempts: [],
    seenQuestionIds: {
      quiz: [],
      reorder: [],
      translate: [],
    },
    lastSpeakText: "",
    recognition: null,
    listening: false,
  };

  const topicSelect = document.getElementById("topicSelect");
  const customTopic = document.getElementById("customTopic");
  const levelSelect = document.getElementById("levelSelect");
  const startBtn = document.getElementById("startBtn");
  const sendBtn = document.getElementById("sendBtn");
  const stuckBtn = document.getElementById("stuckBtn");
  const nextQuizBtn = document.getElementById("nextQuizBtn");
  const nextReorderBtn = document.getElementById("nextReorderBtn");
  const clearReorderBtn = document.getElementById("clearReorderBtn");
  const checkReorderBtn = document.getElementById("checkReorderBtn");
  const nextTranslateBtn = document.getElementById("nextTranslateBtn");
  const checkTranslateBtn = document.getElementById("checkTranslateBtn");
  const refreshSummaryBtn = document.getElementById("refreshSummaryBtn");
  const speakBtn = document.getElementById("speakBtn");
  const dictateBtn = document.getElementById("dictateBtn");
  const stopSpeechBtn = document.getElementById("stopSpeechBtn");
  const speechStatus = document.getElementById("speechStatus");
  const modeButtons = Array.from(document.querySelectorAll(".mode-tab"));
  const userInput = document.getElementById("userInput");
  const chatLog = document.getElementById("chatLog");
  const starterBox = document.getElementById("starterBox");
  const hintBox = document.getElementById("hintBox");
  const correctionBox = document.getElementById("correctionBox");
  const quizPanel = document.getElementById("quizPanel");
  const quizQuestion = document.getElementById("quizQuestion");
  const quizChoices = document.getElementById("quizChoices");
  const quizResult = document.getElementById("quizResult");
  const reorderPanel = document.getElementById("reorderPanel");
  const reorderPrompt = document.getElementById("reorderPrompt");
  const reorderAnswer = document.getElementById("reorderAnswer");
  const reorderWords = document.getElementById("reorderWords");
  const reorderResult = document.getElementById("reorderResult");
  const translatePanel = document.getElementById("translatePanel");
  const translatePrompt = document.getElementById("translatePrompt");
  const translateInput = document.getElementById("translateInput");
  const translateResult = document.getElementById("translateResult");
  const translatePatterns = document.getElementById("translatePatterns");
  const summaryStats = document.getElementById("summaryStats");
  const summaryAdvice = document.getElementById("summaryAdvice");
  const composer = document.querySelector(".composer");

  function url(path) {
    if (typeof window.apiurl === "function") return window.apiurl(path);
    return path;
  }

  function currentTopic() {
    return (customTopic.value || "").trim() || topicSelect.value;
  }

  function currentLevel() {
    return levelSelect.value || "beginner";
  }

  function setSpeechStatus(text) {
    speechStatus.textContent = text || "";
  }

  function canSpeak() {
    return Boolean(window.EnglishChatSpeech && window.EnglishChatSpeech.canUseBrowserTts());
  }

  function speechRecognitionCtor() {
    return window.SpeechRecognition || window.webkitSpeechRecognition || null;
  }

  function rememberSpeakText(text) {
    const s = (text || "").trim();
    if (s) state.lastSpeakText = s;
  }

  function currentSpeakText() {
    if (state.mode === "chat") return state.lastSpeakText;
    if (state.mode === "quiz" && state.quiz) return state.quiz.question || state.lastSpeakText;
    if (state.mode === "reorder" && state.reorder) {
      if (reorderResult.textContent && state.reorder.answer) return state.reorder.answer;
      return state.reorder.prompt || (state.reorder.words || []).join(" ");
    }
    if (state.mode === "translate" && state.translation) return state.translation.sample_answer || translateInput.value || state.lastSpeakText;
    return state.lastSpeakText;
  }

  async function speakText(text) {
    const s = (text || "").trim();
    if (!s) {
      setSpeechStatus("沒有可朗讀的內容。");
      return;
    }
    if (!window.EnglishChatSpeech) {
      setSpeechStatus("語音模組尚未載入。");
      return;
    }
    try {
      await window.EnglishChatSpeech.speak(s, {
        rate: state.level === "beginner" ? 0.82 : state.level === "intermediate" ? 0.92 : 1,
        onstart: () => setSpeechStatus("正在播放語音..."),
        onend: () => setSpeechStatus(""),
      });
    } catch (e) {
      setSpeechStatus("語音播放失敗，瀏覽器與內網後端都無法使用。");
    }
  }

  function applyDictation(text) {
    const s = (text || "").trim();
    if (!s) return;
    if (state.mode === "translate") {
      translateInput.value = s;
      translateInput.focus();
      return;
    }
    if (state.mode === "chat") {
      userInput.value = s;
      userInput.focus();
      return;
    }
    if (state.mode === "reorder") {
      setSpeechStatus("重組題請用字詞按鈕作答；口說檢查會在下一階段加入。");
      return;
    }
    userInput.value = s;
  }

  function startDictation() {
    if (state.mode === "reorder") {
      setSpeechStatus("重組題暫停語音輸入，請用字詞按鈕作答。");
      return;
    }
    const Recognition = speechRecognitionCtor();
    if (state.listening && state.recognition) {
      state.recognition.stop();
      return;
    }
    if (!Recognition || !window.EnglishChatSpeech) {
      startBackendDictation();
      return;
    }
    try {
      state.recognition = window.EnglishChatSpeech.startBrowserDictation({
        onstart: () => {
          state.listening = true;
          dictateBtn.classList.add("active");
          setSpeechStatus("正在聽你說...");
        },
        onresult: (text) => {
          applyDictation(text);
          setSpeechStatus(text ? `辨識結果：${text}` : "沒有偵測到語音。");
        },
        onerror: () => setSpeechStatus("語音辨識失敗。"),
        onend: () => {
          state.listening = false;
          dictateBtn.classList.remove("active");
          if (speechStatus.textContent === "正在聽你說...") setSpeechStatus("");
        },
      });
    } catch (e) {
      setSpeechStatus("語音辨識啟動失敗。");
    }
  }

  function startBackendDictation() {
    if (!window.EnglishChatSpeech || !window.EnglishChatSpeech.startBackendDictation) {
      setSpeechStatus("此瀏覽器不支援語音辨識，也無法啟用內網錄音備援。");
      return;
    }
    window.EnglishChatSpeech.startBackendDictation({
      onstart: (controller) => {
        state.recognition = controller;
        state.listening = true;
        dictateBtn.classList.add("active");
        setSpeechStatus("正在錄音，按 Stop 後送內網辨識...");
      },
      onresult: (text) => {
        applyDictation(text);
        setSpeechStatus(text ? `內網辨識結果：${text}` : "內網辨識沒有取得文字。");
      },
      onerror: () => setSpeechStatus("內網語音辨識失敗。"),
      onend: () => {
        state.listening = false;
        dictateBtn.classList.remove("active");
      },
    }).catch(() => {
      setSpeechStatus("無法啟用麥克風或內網語音辨識。");
    });
  }

  function stopSpeechTools() {
    if (window.EnglishChatSpeech && window.EnglishChatSpeech.stopPlayback) {
      window.EnglishChatSpeech.stopPlayback();
    } else if (canSpeak()) {
      window.speechSynthesis.cancel();
    }
    if (state.recognition) {
      try {
        state.recognition.stop();
      } catch (e) {
        // Ignore stopped recognizer errors.
      }
    }
    state.listening = false;
    dictateBtn.classList.remove("active");
    setSpeechStatus("");
  }

  function showOnlyPanel(mode) {
    const isChat = mode === "chat";
    chatLog.classList.toggle("hidden", !isChat);
    starterBox.classList.toggle("hidden", !isChat);
    correctionBox.classList.toggle("hidden", !isChat);
    composer.classList.toggle("hidden", !isChat);
    quizPanel.classList.toggle("hidden", mode !== "quiz");
    reorderPanel.classList.toggle("hidden", mode !== "reorder");
    translatePanel.classList.toggle("hidden", mode !== "translate");
  }

  function renderSummary(summary) {
    const total = summary.total || 0;
    summaryStats.textContent = `Questions: ${total} | Correct: ${summary.correct || 0} | Accuracy: ${summary.accuracy || 0}% | Avg score: ${summary.average_score || 0}`;
    summaryAdvice.innerHTML = "";
    const recommendations = Array.isArray(summary.recommendations) ? summary.recommendations : [];
    recommendations.forEach((item) => {
      const div = document.createElement("div");
      div.textContent = item;
      summaryAdvice.appendChild(div);
    });
    const weakPatterns = Array.isArray(summary.weak_patterns) ? summary.weak_patterns : [];
    if (weakPatterns.length) {
      const div = document.createElement("div");
      div.textContent = `Weak patterns: ${weakPatterns.join(", ")}`;
      summaryAdvice.appendChild(div);
    }
  }

  async function updateSummary() {
    const resp = await fetch(url("/englishchat/practice/summary/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attempts: state.attempts }),
    });
    const data = await resp.json();
    if (!data.ok) return;
    renderSummary(data);
  }

  function recordAttempt(attempt) {
    state.attempts.push({
      mode: attempt.mode,
      correct: Boolean(attempt.correct),
      score: attempt.score,
      pattern: attempt.pattern || "",
    });
    updateSummary().catch(() => {
      renderSummary({
        total: state.attempts.length,
        correct: state.attempts.filter((x) => x.correct).length,
        accuracy: 0,
        average_score: 0,
        recommendations: ["Summary service unavailable. Keep practicing."],
      });
    });
  }

  function setMode(mode) {
    state.mode = mode;
    modeButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
    showOnlyPanel(mode);
    if (mode === "quiz" && !state.quiz) loadFillBlankQuiz().catch(showQuizLoadError);
    if (mode === "reorder" && !state.reorder) loadReorderQuiz().catch(showReorderLoadError);
    if (mode === "translate" && !state.translation) loadTranslationQuiz().catch(showTranslateLoadError);
  }

  function addMessage(role, text) {
    state.messages.push({ role, text });
    const div = document.createElement("div");
    div.className = `msg ${role === "user" ? "user" : "ai"}`;
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    if (role === "ai") rememberSpeakText(text);
  }

  function setStarters(list) {
    starterBox.innerHTML = "";
    if (!Array.isArray(list) || list.length === 0) return;
    const title = document.createElement("div");
    title.textContent = "Try one of these:";
    starterBox.appendChild(title);
    list.forEach((s) => {
      if (!s) return;
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "starter-item";
      chip.textContent = s;
      chip.addEventListener("click", () => {
        userInput.value = s;
        userInput.focus();
      });
      starterBox.appendChild(chip);
    });
  }

  function setCorrection(correction) {
    correctionBox.innerHTML = "";
    if (!correction || !correction.improved) return;
    correctionBox.textContent = `Original: ${correction.original || ""} | Better: ${correction.improved || ""} | Why: ${correction.why || ""}`;
  }

  async function startChat() {
    state.topic = currentTopic();
    state.level = currentLevel();
    state.messages = [];
    state.quiz = null;
    state.reorder = null;
    state.translation = null;
    state.attempts = [];
    state.seenQuestionIds = { quiz: [], reorder: [], translate: [] };
    chatLog.innerHTML = "";
    correctionBox.textContent = "";
    hintBox.textContent = "";
    starterBox.innerHTML = "";

    if (state.mode === "quiz") return loadFillBlankQuiz();
    if (state.mode === "reorder") return loadReorderQuiz();
    if (state.mode === "translate") return loadTranslationQuiz();

    const resp = await fetch(url("/englishchat/start/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicSelect.value,
        custom_topic: (customTopic.value || "").trim(),
        level: state.level,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      addMessage("ai", "I could not start the chat. Please try again.");
      return;
    }

    addMessage("ai", data.opening || "Hi! Let's start.");
    hintBox.textContent = data.zh_hint || "";
    setStarters(data.starter_sentences || []);
    rememberSpeakText(data.opening || "Hi! Let's start.");
  }

  async function sendUserMessage(text) {
    const msg = (text || "").trim();
    if (!msg) return;
    addMessage("user", msg);
    userInput.value = "";

    const resp = await fetch(url("/englishchat/chat/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: state.topic || currentTopic(),
        level: state.level || currentLevel(),
        user_text: msg,
        messages: state.messages.slice(-12),
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      addMessage("ai", "I hit an error. Please try once more.");
      return;
    }

    addMessage("ai", data.ai_reply || "Nice. Keep going.");
    hintBox.textContent = data.zh_hint || "";
    setCorrection(data.correction || {});
    setStarters(data.suggestions || []);
    rememberSpeakText(data.ai_reply || "");
  }

  function showQuizLoadError() {
    quizQuestion.textContent = "Could not load a quiz. Please try again.";
  }

  function renderQuiz(quiz) {
    state.quiz = quiz;
    if (quiz.question_id && !state.seenQuestionIds.quiz.includes(quiz.question_id)) {
      state.seenQuestionIds.quiz.push(quiz.question_id);
    }
    quizQuestion.textContent = quiz.question || "";
    rememberSpeakText(quiz.question || "");
    quizChoices.innerHTML = "";
    quizResult.textContent = "";
    (quiz.choices || []).forEach((choice) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz-choice";
      btn.textContent = choice;
      btn.addEventListener("click", () => {
        checkFillBlankAnswer(choice).catch(() => {
          quizResult.textContent = "Could not check the answer. Please try again.";
        });
      });
      quizChoices.appendChild(btn);
    });
  }

  async function loadFillBlankQuiz() {
    state.topic = currentTopic();
    state.level = currentLevel();
    quizQuestion.textContent = "Loading question...";
    quizChoices.innerHTML = "";
    quizResult.textContent = "";

    const resp = await fetch(url("/englishchat/quiz/fill_blank/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicSelect.value,
        custom_topic: customTopic.value.trim(),
        level: state.level,
        seen_question_ids: state.seenQuestionIds.quiz,
      }),
    });
    const data = await resp.json();
    if (!data.ok) return showQuizLoadError();
    renderQuiz(data);
  }

  async function checkFillBlankAnswer(selected) {
    if (!state.quiz) return;
    const resp = await fetch(url("/englishchat/quiz/check/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        selected,
        answer: state.quiz.answer,
        explanation_zh: state.quiz.explanation_zh,
        pattern: state.quiz.pattern,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      quizResult.textContent = "Could not check the answer.";
      return;
    }
    quizChoices.querySelectorAll("button").forEach((btn) => {
      btn.disabled = true;
      btn.classList.toggle("correct", btn.textContent === data.answer);
      btn.classList.toggle("wrong", btn.textContent === data.selected && !data.correct);
    });
    quizResult.textContent = data.correct
      ? `Correct. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`
      : `Not quite. Answer: ${data.answer}. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`;
    recordAttempt({
      mode: "fill_blank",
      correct: data.correct,
      score: data.correct ? 100 : 0,
      pattern: data.pattern,
    });
  }

  function showReorderLoadError() {
    reorderPrompt.textContent = "Could not load a reorder question.";
  }

  function refreshReorderAnswer() {
    reorderAnswer.textContent = state.reorderPicked.join(" ");
  }

  function renderReorder(quiz) {
    state.reorder = quiz;
    if (quiz.question_id && !state.seenQuestionIds.reorder.includes(quiz.question_id)) {
      state.seenQuestionIds.reorder.push(quiz.question_id);
    }
    state.reorderPicked = [];
    reorderPrompt.textContent = quiz.prompt || "Put the words in order.";
    rememberSpeakText(quiz.answer || "");
    reorderAnswer.textContent = "";
    reorderResult.textContent = "";
    reorderWords.innerHTML = "";
    (quiz.words || []).forEach((word) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "word-chip";
      chip.textContent = word;
      chip.addEventListener("click", () => {
        chip.disabled = true;
        state.reorderPicked.push(word);
        refreshReorderAnswer();
      });
      reorderWords.appendChild(chip);
    });
  }

  async function loadReorderQuiz() {
    state.topic = currentTopic();
    state.level = currentLevel();
    reorderPrompt.textContent = "Loading reorder question...";
    reorderAnswer.textContent = "";
    reorderWords.innerHTML = "";
    reorderResult.textContent = "";

    const resp = await fetch(url("/englishchat/quiz/reorder/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicSelect.value,
        custom_topic: customTopic.value.trim(),
        level: state.level,
        seen_question_ids: state.seenQuestionIds.reorder,
      }),
    });
    const data = await resp.json();
    if (!data.ok) return showReorderLoadError();
    renderReorder(data);
  }

  async function checkReorderAnswer() {
    if (!state.reorder) return;
    const userAnswer = state.reorderPicked.join(" ");
    const resp = await fetch(url("/englishchat/quiz/reorder/check/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_answer: userAnswer,
        answer: state.reorder.answer,
        explanation_zh: state.reorder.explanation_zh,
        pattern: state.reorder.pattern,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      reorderResult.textContent = "Please build a sentence first.";
      return;
    }
    reorderResult.textContent = data.correct
      ? `Correct. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`
      : `Not quite. Answer: ${data.answer}. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`;
    recordAttempt({
      mode: "reorder",
      correct: data.correct,
      score: data.correct ? 100 : 0,
      pattern: data.pattern,
    });
  }

  function clearReorderAnswer() {
    state.reorderPicked = [];
    reorderWords.querySelectorAll("button").forEach((btn) => {
      btn.disabled = false;
    });
    reorderResult.textContent = "";
    refreshReorderAnswer();
  }

  function showTranslateLoadError() {
    translatePrompt.textContent = "Could not load a translation question.";
  }

  function renderTranslation(quiz) {
    state.translation = quiz;
    if (quiz.question_id && !state.seenQuestionIds.translate.includes(quiz.question_id)) {
      state.seenQuestionIds.translate.push(quiz.question_id);
    }
    translatePrompt.textContent = quiz.zh_prompt || "";
    rememberSpeakText(quiz.sample_answer || "");
    translateInput.value = "";
    translateResult.textContent = "";
    translatePatterns.innerHTML = "";
    (quiz.patterns || []).forEach((pattern) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "starter-item";
      chip.textContent = pattern;
      translatePatterns.appendChild(chip);
    });
  }

  async function loadTranslationQuiz() {
    state.topic = currentTopic();
    state.level = currentLevel();
    translatePrompt.textContent = "Loading translation question...";
    translateInput.value = "";
    translateResult.textContent = "";
    translatePatterns.innerHTML = "";

    const resp = await fetch(url("/englishchat/quiz/translate/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicSelect.value,
        custom_topic: customTopic.value.trim(),
        level: state.level,
        seen_question_ids: state.seenQuestionIds.translate,
      }),
    });
    const data = await resp.json();
    if (!data.ok) return showTranslateLoadError();
    renderTranslation(data);
  }

  async function checkTranslationAnswer() {
    if (!state.translation) return;
    const userAnswer = translateInput.value.trim();
    if (!userAnswer) {
      translateResult.textContent = "Type your translation first.";
      return;
    }
    const resp = await fetch(url("/englishchat/quiz/translate/evaluate/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        zh_prompt: state.translation.zh_prompt,
        sample_answer: state.translation.sample_answer,
        user_answer: userAnswer,
        level: state.level,
      }),
    });
    const data = await resp.json();
    if (!data.ok) {
      translateResult.textContent = "Could not check the translation.";
      return;
    }
    translateResult.textContent = `Score: ${data.score}. Better: ${data.corrected}. ${data.feedback_zh || ""}`;
    rememberSpeakText(data.corrected || data.sample_answer || "");
    recordAttempt({
      mode: "translate",
      correct: Number(data.score || 0) >= 80,
      score: Number(data.score || 0),
      pattern: (state.translation.patterns || [])[0] || "",
    });
  }

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => setMode(btn.dataset.mode || "chat"));
  });

  startBtn.addEventListener("click", () => {
    startChat().catch(() => {
      if (state.mode === "chat") addMessage("ai", "Start failed. Please retry.");
      if (state.mode === "quiz") quizResult.textContent = "Start failed. Please retry.";
      if (state.mode === "reorder") reorderResult.textContent = "Start failed. Please retry.";
      if (state.mode === "translate") translateResult.textContent = "Start failed. Please retry.";
    });
  });

  nextQuizBtn.addEventListener("click", () => loadFillBlankQuiz().catch(showQuizLoadError));
  nextReorderBtn.addEventListener("click", () => loadReorderQuiz().catch(showReorderLoadError));
  clearReorderBtn.addEventListener("click", clearReorderAnswer);
  checkReorderBtn.addEventListener("click", () => checkReorderAnswer().catch(() => {
    reorderResult.textContent = "Could not check the answer.";
  }));
  nextTranslateBtn.addEventListener("click", () => loadTranslationQuiz().catch(showTranslateLoadError));
  checkTranslateBtn.addEventListener("click", () => checkTranslationAnswer().catch(() => {
    translateResult.textContent = "Could not check the translation.";
  }));
  refreshSummaryBtn.addEventListener("click", () => updateSummary().catch(() => {
    summaryAdvice.textContent = "Could not refresh the summary.";
  }));
  speakBtn.addEventListener("click", () => speakText(currentSpeakText()));
  dictateBtn.addEventListener("click", startDictation);
  stopSpeechBtn.addEventListener("click", stopSpeechTools);

  sendBtn.addEventListener("click", () => {
    sendUserMessage(userInput.value).catch(() => addMessage("ai", "Send failed. Please retry."));
  });

  stuckBtn.addEventListener("click", () => {
    sendUserMessage("I'm stuck. Please give me 3 simple ways to respond.").catch(() => {
      addMessage("ai", "Please try again.");
    });
  });

  userInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendUserMessage(userInput.value).catch(() => addMessage("ai", "Send failed. Please retry."));
    }
  });
})();

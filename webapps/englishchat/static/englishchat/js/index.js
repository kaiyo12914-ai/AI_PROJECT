(function () {
  "use strict";

  const MAX_SEEN_HISTORY = 12;
  const MAX_DEBUG_LINES = 30;
  const ONLINE_TEST_TOTAL = 10;
  const ONLINE_TEST_MODES = ["quiz", "reorder", "translate"];
  const DEBUG_MODE = document.body.dataset.debugMode === "1";

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
    onlineTest: {
      active: false,
      total: ONLINE_TEST_TOTAL,
      index: 0,
      mode: "",
      question: null,
      picked: [],
      answered: false,
      correct: 0,
      scoreTotal: 0,
    },
    lastSpeakText: "",
    recognition: null,
    listening: false,
    debugLines: [],
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
  const testPanel = document.getElementById("testPanel");
  const testProgress = document.getElementById("testProgress");
  const testPrompt = document.getElementById("testPrompt");
  const testChoices = document.getElementById("testChoices");
  const testAnswer = document.getElementById("testAnswer");
  const testWords = document.getElementById("testWords");
  const testTextInput = document.getElementById("testTextInput");
  const testResult = document.getElementById("testResult");
  const testStartBtn = document.getElementById("testStartBtn");
  const testCheckBtn = document.getElementById("testCheckBtn");
  const testNextBtn = document.getElementById("testNextBtn");
  const summaryStats = document.getElementById("summaryStats");
  const summaryAdvice = document.getElementById("summaryAdvice");
  const composer = document.querySelector(".composer");
  const debugPanel = document.getElementById("debugPanel");
  const debugLog = document.getElementById("debugLog");
  const clearDebugBtn = document.getElementById("clearDebugBtn");

  if (DEBUG_MODE && debugPanel) {
    debugPanel.classList.remove("hidden");
  }

  function url(path) {
    if (typeof window.apiurl === "function") return window.apiurl(path);
    return path;
  }

  function rememberSeenQuestion(mode, questionId) {
    if (!questionId || !state.seenQuestionIds[mode]) return;
    const list = state.seenQuestionIds[mode];
    const next = list.filter((item) => item !== questionId);
    next.push(questionId);
    state.seenQuestionIds[mode] = next.slice(-MAX_SEEN_HISTORY);
  }

  function appendDebugLine(text) {
    if (!DEBUG_MODE || !debugLog || !text) return;
    state.debugLines.push(text);
    state.debugLines = state.debugLines.slice(-MAX_DEBUG_LINES);
    debugLog.innerHTML = "";
    state.debugLines.forEach((line) => {
      const div = document.createElement("div");
      div.className = "debug-line";
      div.textContent = line;
      debugLog.appendChild(div);
    });
    debugLog.scrollTop = debugLog.scrollHeight;
  }

  function logFallback(scope, data) {
    if (!data || !data.fallback_reason) return;
    appendDebugLine(`[${scope}] source=${data.source || "unknown"} reason=${data.fallback_reason}`);
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
    if (state.mode === "test" && state.onlineTest.question) {
      const q = state.onlineTest.question;
      if (state.onlineTest.mode === "quiz") return q.question || state.lastSpeakText;
      if (state.onlineTest.mode === "reorder") return q.answer || q.prompt || state.lastSpeakText;
      if (state.onlineTest.mode === "translate") return q.sample_answer || testTextInput.value || state.lastSpeakText;
    }
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
    if (state.mode === "test") {
      if (!testTextInput.classList.contains("hidden")) {
        testTextInput.value = s;
        testTextInput.focus();
      }
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
    testPanel.classList.toggle("hidden", mode !== "test");
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
    if (mode === "test" && !state.onlineTest.active) resetOnlineTest();
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
    state.onlineTest.active = false;
    state.debugLines = [];
    if (debugLog) debugLog.innerHTML = "";
    chatLog.innerHTML = "";
    correctionBox.textContent = "";
    hintBox.textContent = "";
    starterBox.innerHTML = "";

    if (state.mode === "quiz") return loadFillBlankQuiz();
    if (state.mode === "reorder") return loadReorderQuiz();
    if (state.mode === "translate") return loadTranslationQuiz();
    if (state.mode === "test") return resetOnlineTest();

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
    rememberSeenQuestion("quiz", quiz.question_id);
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
    logFallback("fill_blank", data);
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
    rememberSeenQuestion("reorder", quiz.question_id);
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
    logFallback("reorder", data);
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
    rememberSeenQuestion("translate", quiz.question_id);
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
    logFallback("translation", data);
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

  function resetOnlineTest() {
    state.topic = currentTopic();
    state.level = currentLevel();
    state.onlineTest = {
      active: true,
      total: ONLINE_TEST_TOTAL,
      index: 0,
      mode: "",
      question: null,
      picked: [],
      answered: false,
      correct: 0,
      scoreTotal: 0,
    };
    testResult.textContent = "";
    loadOnlineTestQuestion().catch(showOnlineTestLoadError);
  }

  function showOnlineTestLoadError() {
    testPrompt.textContent = "Could not load the test question.";
    testResult.textContent = "Please try again.";
  }

  function updateOnlineTestProgress() {
    const t = state.onlineTest;
    const average = t.index ? Math.round(t.scoreTotal / t.index) : 0;
    testProgress.textContent = `Question ${Math.min(t.index + 1, t.total)} / ${t.total} | Correct ${t.correct} | Avg ${average}`;
  }

  function setOnlineTestControls(answered) {
    testCheckBtn.disabled = Boolean(answered);
    testNextBtn.disabled = !answered;
  }

  function renderOnlineTestQuestion(mode, quiz) {
    state.onlineTest.mode = mode;
    state.onlineTest.question = quiz;
    state.onlineTest.picked = [];
    state.onlineTest.answered = false;
    updateOnlineTestProgress();
    testChoices.innerHTML = "";
    testWords.innerHTML = "";
    testAnswer.textContent = "";
    testAnswer.classList.add("hidden");
    testTextInput.value = "";
    testTextInput.classList.add("hidden");
    testResult.textContent = "";
    setOnlineTestControls(false);

    if (mode === "quiz") {
      testPrompt.textContent = quiz.question || "";
      rememberSpeakText(quiz.question || "");
      testCheckBtn.classList.add("hidden");
      (quiz.choices || []).forEach((choice) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "quiz-choice";
        btn.textContent = choice;
        btn.addEventListener("click", () => checkOnlineTestAnswer(choice).catch(() => {
          testResult.textContent = "Could not check the answer.";
        }));
        testChoices.appendChild(btn);
      });
      return;
    }

    testCheckBtn.classList.remove("hidden");
    if (mode === "reorder") {
      testPrompt.textContent = quiz.prompt || "Put the words in order.";
      rememberSpeakText(quiz.answer || "");
      testAnswer.classList.remove("hidden");
      (quiz.words || []).forEach((word) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "word-chip";
        chip.textContent = word;
        chip.addEventListener("click", () => {
          if (state.onlineTest.answered) return;
          chip.disabled = true;
          state.onlineTest.picked.push(word);
          testAnswer.textContent = state.onlineTest.picked.join(" ");
        });
        testWords.appendChild(chip);
      });
      return;
    }

    testPrompt.textContent = quiz.zh_prompt || "";
    rememberSpeakText(quiz.sample_answer || "");
    testTextInput.classList.remove("hidden");
    testTextInput.focus();
  }

  async function loadOnlineTestQuestion() {
    const t = state.onlineTest;
    if (!t.active) {
      resetOnlineTest();
      return;
    }
    if (t.index >= t.total) {
      const average = t.total ? Math.round(t.scoreTotal / t.total) : 0;
      testPrompt.textContent = "Test completed.";
      testChoices.innerHTML = "";
      testWords.innerHTML = "";
      testAnswer.classList.add("hidden");
      testTextInput.classList.add("hidden");
      testResult.textContent = `Final score: ${average}. Correct: ${t.correct}/${t.total}.`;
      testProgress.textContent = `Done | Correct ${t.correct}/${t.total} | Avg ${average}`;
      testCheckBtn.disabled = true;
      testNextBtn.disabled = true;
      return;
    }

    const mode = ONLINE_TEST_MODES[t.index % ONLINE_TEST_MODES.length];
    testPrompt.textContent = "Loading test question...";
    const path = mode === "quiz"
      ? "/englishchat/quiz/fill_blank/"
      : mode === "reorder"
        ? "/englishchat/quiz/reorder/"
        : "/englishchat/quiz/translate/";
    const seenKey = mode === "quiz" ? "quiz" : mode;
    const resp = await fetch(url(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: topicSelect.value,
        custom_topic: customTopic.value.trim(),
        level: state.level,
        seen_question_ids: state.seenQuestionIds[seenKey],
      }),
    });
    const data = await resp.json();
    if (!data.ok) return showOnlineTestLoadError();
    logFallback(`test_${mode}`, data);
    rememberSeenQuestion(seenKey, data.question_id);
    renderOnlineTestQuestion(mode, data);
  }

  async function checkOnlineTestAnswer(selectedChoice) {
    const t = state.onlineTest;
    const quiz = t.question;
    if (!quiz || t.answered) return;
    let data = {};
    let attempt = { mode: t.mode, correct: false, score: 0, pattern: "" };

    if (t.mode === "quiz") {
      const selected = String(selectedChoice || "");
      const resp = await fetch(url("/englishchat/quiz/check/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selected,
          answer: quiz.answer,
          explanation_zh: quiz.explanation_zh,
          pattern: quiz.pattern,
        }),
      });
      data = await resp.json();
      testChoices.querySelectorAll("button").forEach((btn) => {
        btn.disabled = true;
        btn.classList.toggle("correct", btn.textContent === data.answer);
        btn.classList.toggle("wrong", btn.textContent === data.selected && !data.correct);
      });
      attempt = { mode: "test_fill_blank", correct: Boolean(data.correct), score: data.correct ? 100 : 0, pattern: data.pattern || "" };
      testResult.textContent = data.correct
        ? `Correct. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`
        : `Not quite. Answer: ${data.answer}. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`;
    } else if (t.mode === "reorder") {
      const userAnswer = t.picked.join(" ");
      if (!userAnswer) {
        testResult.textContent = "Build a sentence first.";
        return;
      }
      const resp = await fetch(url("/englishchat/quiz/reorder/check/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_answer: userAnswer,
          answer: quiz.answer,
          explanation_zh: quiz.explanation_zh,
          pattern: quiz.pattern,
        }),
      });
      data = await resp.json();
      attempt = { mode: "test_reorder", correct: Boolean(data.correct), score: data.correct ? 100 : 0, pattern: data.pattern || "" };
      testResult.textContent = data.correct
        ? `Correct. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`
        : `Not quite. Answer: ${data.answer}. ${data.explanation_zh || ""} Pattern: ${data.pattern || ""}`;
    } else {
      const userAnswer = testTextInput.value.trim();
      if (!userAnswer) {
        testResult.textContent = "Type your translation first.";
        return;
      }
      const resp = await fetch(url("/englishchat/quiz/translate/evaluate/"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          zh_prompt: quiz.zh_prompt,
          sample_answer: quiz.sample_answer,
          user_answer: userAnswer,
          level: state.level,
        }),
      });
      data = await resp.json();
      const score = Number(data.score || 0);
      attempt = { mode: "test_translate", correct: score >= 80, score, pattern: (quiz.patterns || [])[0] || "" };
      testResult.textContent = `Score: ${score}. Better: ${data.corrected}. ${data.feedback_zh || ""}`;
      rememberSpeakText(data.corrected || data.sample_answer || "");
    }

    t.answered = true;
    t.index += 1;
    if (attempt.correct) t.correct += 1;
    t.scoreTotal += Number(attempt.score || 0);
    recordAttempt(attempt);
    updateOnlineTestProgress();
    setOnlineTestControls(true);
  }

  function nextOnlineTestQuestion() {
    if (!state.onlineTest.active || !state.onlineTest.answered) return;
    loadOnlineTestQuestion().catch(showOnlineTestLoadError);
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
  testStartBtn.addEventListener("click", resetOnlineTest);
  testCheckBtn.addEventListener("click", () => checkOnlineTestAnswer().catch(() => {
    testResult.textContent = "Could not check the answer.";
  }));
  testNextBtn.addEventListener("click", nextOnlineTestQuestion);
  refreshSummaryBtn.addEventListener("click", () => updateSummary().catch(() => {
    summaryAdvice.textContent = "Could not refresh the summary.";
  }));
  speakBtn.addEventListener("click", () => speakText(currentSpeakText()));
  dictateBtn.addEventListener("click", startDictation);
  stopSpeechBtn.addEventListener("click", stopSpeechTools);
  if (clearDebugBtn) {
    clearDebugBtn.addEventListener("click", () => {
      state.debugLines = [];
      if (debugLog) debugLog.innerHTML = "";
    });
  }

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

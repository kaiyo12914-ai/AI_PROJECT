(function () {
  "use strict";

  const state = {
    topic: "",
    level: "beginner",
    messages: [],
  };

  const topicSelect = document.getElementById("topicSelect");
  const customTopic = document.getElementById("customTopic");
  const levelSelect = document.getElementById("levelSelect");
  const startBtn = document.getElementById("startBtn");
  const sendBtn = document.getElementById("sendBtn");
  const stuckBtn = document.getElementById("stuckBtn");
  const userInput = document.getElementById("userInput");
  const chatLog = document.getElementById("chatLog");
  const starterBox = document.getElementById("starterBox");
  const hintBox = document.getElementById("hintBox");
  const correctionBox = document.getElementById("correctionBox");

  function url(path) {
    if (typeof window.apiurl === "function") return window.apiurl(path);
    return path;
  }

  function addMessage(role, text) {
    state.messages.push({ role, text });
    const div = document.createElement("div");
    div.className = `msg ${role === "user" ? "user" : "ai"}`;
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
  }

  function setStarters(list) {
    starterBox.innerHTML = "";
    if (!Array.isArray(list) || list.length === 0) return;
    const title = document.createElement("div");
    title.textContent = "可參考句型：";
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
    const original = correction.original || "";
    const improved = correction.improved || "";
    const why = correction.why || "";
    correctionBox.textContent = `你說的：${original} | 更自然：${improved} | 說明：${why}`;
  }

  async function startChat() {
    state.topic = (customTopic.value || "").trim() || topicSelect.value;
    state.level = levelSelect.value;
    state.messages = [];
    chatLog.innerHTML = "";
    correctionBox.textContent = "";
    hintBox.textContent = "";
    starterBox.innerHTML = "";

    const payload = {
      topic: topicSelect.value,
      custom_topic: (customTopic.value || "").trim(),
      level: state.level,
    };

    const resp = await fetch(url("/englishchat/start/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!data.ok) {
      addMessage("ai", "I could not start the chat. Please try again.");
      return;
    }

    addMessage("ai", data.opening || "Hi! Let's start.");
    hintBox.textContent = data.zh_hint || "";
    setStarters(data.starter_sentences || []);
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
        topic: state.topic || topicSelect.value,
        level: state.level || levelSelect.value,
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
  }

  startBtn.addEventListener("click", () => {
    startChat().catch(() => addMessage("ai", "Start failed. Please retry."));
  });

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


(function () {
  "use strict";

  let currentAudio = null;

  function url(path) {
    if (typeof window.apiurl === "function") return window.apiurl(path);
    return path;
  }

  function canUseBrowserTts() {
    return "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  }

  function canUseBrowserStt() {
    return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  function speakWithBrowser(text, options) {
    return new Promise((resolve, reject) => {
      if (!canUseBrowserTts()) {
        reject(new Error("browser tts unavailable"));
        return;
      }
      const s = (text || "").trim();
      if (!s) {
        reject(new Error("text is required"));
        return;
      }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(s);
      utterance.lang = "en-US";
      utterance.rate = options && options.rate ? options.rate : 0.92;
      utterance.onstart = () => options && options.onstart && options.onstart();
      utterance.onend = () => {
        options && options.onend && options.onend();
        resolve();
      };
      utterance.onerror = () => reject(new Error("browser tts failed"));
      window.speechSynthesis.speak(utterance);
    });
  }

  async function speakWithBackend(text, options) {
    const resp = await fetch(url("/englishchat/speech/tts/"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    if (!data.ok || !data.wav_url) {
      throw new Error(data.error || "backend tts failed");
    }
    const audio = new Audio(data.wav_url);
    currentAudio = audio;
    audio.onplay = () => options && options.onstart && options.onstart();
    audio.onended = () => {
      currentAudio = null;
      options && options.onend && options.onend();
    };
    await audio.play();
    return data;
  }

  async function speak(text, options) {
    try {
      return await speakWithBrowser(text, options);
    } catch (browserError) {
      return speakWithBackend(text, options);
    }
  }

  function startBrowserDictation(options) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) throw new Error("browser stt unavailable");
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => options && options.onstart && options.onstart(recognition);
    recognition.onresult = (event) => {
      const text = event.results && event.results[0] && event.results[0][0]
        ? event.results[0][0].transcript
        : "";
      options && options.onresult && options.onresult(text);
    };
    recognition.onerror = (event) => options && options.onerror && options.onerror(event);
    recognition.onend = () => options && options.onend && options.onend();
    recognition.start();
    return recognition;
  }

  async function transcribeAudio(audioBlob, language) {
    const form = new FormData();
    form.append("audio", audioBlob, "speech.webm");
    form.append("language", language || "en");
    const resp = await fetch(url("/englishchat/speech/stt/"), {
      method: "POST",
      body: form,
    });
    return resp.json();
  }

  async function startBackendDictation(options) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      throw new Error("backend stt recorder unavailable");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks = [];
    const recorder = new MediaRecorder(stream);
    const controller = {
      stop() {
        if (recorder.state !== "inactive") recorder.stop();
      },
    };
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size) chunks.push(event.data);
    };
    recorder.onstart = () => options && options.onstart && options.onstart(controller);
    recorder.onerror = (event) => options && options.onerror && options.onerror(event);
    recorder.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      try {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const data = await transcribeAudio(blob, "en");
        if (!data.ok) throw new Error(data.error || "backend stt failed");
        options && options.onresult && options.onresult(data.text || "");
      } catch (e) {
        options && options.onerror && options.onerror(e);
      } finally {
        options && options.onend && options.onend();
      }
    };
    recorder.start();
    return controller;
  }

  function stopPlayback() {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
  }

  window.EnglishChatSpeech = {
    canUseBrowserTts,
    canUseBrowserStt,
    speak,
    startBrowserDictation,
    startBackendDictation,
    transcribeAudio,
    stopPlayback,
  };
})();

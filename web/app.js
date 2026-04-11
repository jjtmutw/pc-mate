const STORAGE_KEY = "voice_mqtt_desktop_settings";

const state = {
  client: null,
  recognition: null,
  isListening: false,
  scanner: null,
  isScanning: false,
  lastScanText: "",
  audioContext: null,
};

const elements = {
  brokerUrl: document.querySelector("#broker-url"),
  topic: document.querySelector("#topic"),
  username: document.querySelector("#username"),
  password: document.querySelector("#password"),
  connectButton: document.querySelector("#connect-button"),
  disconnectButton: document.querySelector("#disconnect-button"),
  mqttStatus: document.querySelector("#mqtt-status"),
  languageSelect: document.querySelector("#language-select"),
  listenButton: document.querySelector("#listen-button"),
  stopButton: document.querySelector("#stop-button"),
  speechStatus: document.querySelector("#speech-status"),
  startScanButton: document.querySelector("#start-scan-button"),
  stopScanButton: document.querySelector("#stop-scan-button"),
  scanStatus: document.querySelector("#scan-status"),
  scannerCard: document.querySelector("#scanner-card"),
  transcriptInput: document.querySelector("#transcript-input"),
  appendEnter: document.querySelector("#append-enter"),
  sendButton: document.querySelector("#send-button"),
  clearButton: document.querySelector("#clear-button"),
  log: document.querySelector("#log"),
};

function addLog(message, level = "info") {
  const row = document.createElement("div");
  row.className = "log-entry";
  const stamp = new Date().toLocaleTimeString("zh-TW", { hour12: false });
  row.innerHTML = `<strong>[${stamp}]</strong> ${message}`;

  if (level === "error") {
    row.style.color = "#ffb3b3";
  }

  elements.log.prepend(row);
}

function saveSettings() {
  const settings = {
    brokerUrl: elements.brokerUrl.value.trim(),
    topic: elements.topic.value.trim(),
    username: elements.username.value.trim(),
    password: elements.password.value,
    language: elements.languageSelect.value,
    appendEnter: elements.appendEnter.checked,
  };

  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

function loadSettings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return;
    }

    const settings = JSON.parse(raw);
    elements.brokerUrl.value = settings.brokerUrl || "wss://broker.emqx.io:8084/mqtt";
    elements.topic.value = settings.topic || "jj/voice/input";
    elements.username.value = settings.username || "";
    elements.password.value = settings.password || "";
    elements.languageSelect.value = settings.language || "zh-TW";
    elements.appendEnter.checked = settings.appendEnter !== false;
  } catch {
    addLog("設定載入失敗，已改用預設值。", "error");
  }
}

function setMqttStatus(text) {
  elements.mqttStatus.textContent = text;
}

function setSpeechStatus(text) {
  elements.speechStatus.textContent = text;
}

function setScanStatus(text) {
  elements.scanStatus.textContent = text;
}

function hasSpeechApi() {
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function hasQrScannerApi() {
  return typeof Html5Qrcode !== "undefined";
}

function normalizeText(text) {
  return text.replace(/\s+/g, " ").trim();
}

function buildPayload(text, source = "mobile-web") {
  return JSON.stringify({
    text: normalizeText(text),
    append_enter: elements.appendEnter.checked,
    source,
    timestamp: new Date().toISOString(),
  });
}

function publishPayload(text, source = "mobile-web") {
  const topic = elements.topic.value.trim();
  const normalized = normalizeText(text);

  if (!state.client || !state.client.connected) {
    addLog("MQTT 尚未連線。", "error");
    return false;
  }

  if (!topic || !normalized) {
    addLog("請確認 Topic 與文字內容不為空。", "error");
    return false;
  }

  saveSettings();

  state.client.publish(topic, buildPayload(normalized, source), { qos: 0, retain: false }, (error) => {
    if (error) {
      addLog(`發送失敗：${error.message}`, "error");
      return;
    }

    addLog(`已發送內容到 ${topic}：${normalized}`);
  });

  return true;
}

function connectMqtt() {
  if (typeof mqtt === "undefined") {
    addLog("MQTT 前端函式庫沒有載入成功。", "error");
    return;
  }

  const brokerUrl = elements.brokerUrl.value.trim();
  const topic = elements.topic.value.trim();

  if (!brokerUrl || !topic) {
    addLog("請先輸入 Broker URL 和 Topic。", "error");
    return;
  }

  saveSettings();

  if (state.client) {
    state.client.end(true);
    state.client = null;
  }

  setMqttStatus("正在連線 MQTT...");

  const options = {
    clean: true,
    connectTimeout: 5000,
    clientId: `voice_web_${Math.random().toString(16).slice(2, 10)}`,
  };

  if (elements.username.value.trim()) {
    options.username = elements.username.value.trim();
  }

  if (elements.password.value) {
    options.password = elements.password.value;
  }

  const client = mqtt.connect(brokerUrl, options);
  state.client = client;

  client.on("connect", () => {
    setMqttStatus(`已連線到 MQTT，可發送到 Topic：${topic}`);
    addLog(`MQTT 已連線：${topic}`);
  });

  client.on("reconnect", () => {
    setMqttStatus("MQTT 重新連線中...");
    addLog("MQTT 重新連線中...");
  });

  client.on("error", (error) => {
    setMqttStatus("MQTT 連線錯誤，請檢查 Broker 設定。");
    addLog(`MQTT 錯誤：${error.message}`, "error");
  });

  client.on("close", () => {
    setMqttStatus("MQTT 已中斷連線。");
    addLog("MQTT 已斷線。");
  });
}

function disconnectMqtt() {
  if (state.client) {
    state.client.end(true);
    state.client = null;
  }

  setMqttStatus("MQTT 已手動中斷。");
}

function createRecognition() {
  if (!hasSpeechApi()) {
    setSpeechStatus("目前瀏覽器不支援語音辨識 API。建議使用 Android Chrome。");
    addLog("瀏覽器不支援 SpeechRecognition。", "error");
    return null;
  }

  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recognition = new Recognition();
  recognition.lang = elements.languageSelect.value;
  recognition.continuous = false;
  recognition.interimResults = true;

  recognition.onstart = () => {
    state.isListening = true;
    setSpeechStatus("正在聽取語音...");
    addLog("開始語音辨識。");
  };

  recognition.onresult = (event) => {
    let finalText = "";
    let interimText = "";

    for (let i = event.resultIndex; i < event.results.length; i += 1) {
      const segment = event.results[i][0]?.transcript || "";
      if (event.results[i].isFinal) {
        finalText += segment;
      } else {
        interimText += segment;
      }
    }

    const merged = normalizeText(finalText || interimText);
    elements.transcriptInput.value = merged;
    setSpeechStatus(finalText ? "辨識完成，可以送出。" : "辨識中...");
  };

  recognition.onerror = (event) => {
    state.isListening = false;
    setSpeechStatus(`語音辨識錯誤：${event.error}`);
    addLog(`語音辨識錯誤：${event.error}`, "error");
  };

  recognition.onend = () => {
    state.isListening = false;
    setSpeechStatus("語音辨識已停止。");
    addLog("語音辨識已停止。");
  };

  return recognition;
}

function startListening() {
  if (!state.recognition) {
    state.recognition = createRecognition();
  }

  if (!state.recognition || state.isListening) {
    return;
  }

  elements.transcriptInput.value = "";
  state.recognition.lang = elements.languageSelect.value;
  saveSettings();
  state.recognition.start();
}

function stopListening() {
  if (state.recognition && state.isListening) {
    state.recognition.stop();
  }
}

function getAudioContext() {
  if (!window.AudioContext && !window.webkitAudioContext) {
    return null;
  }

  if (!state.audioContext) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    state.audioContext = new AudioContextClass();
  }

  return state.audioContext;
}

async function playSuccessDoubleBeep() {
  const audioContext = getAudioContext();
  if (!audioContext) {
    addLog("此瀏覽器不支援提示音播放。", "error");
    return;
  }

  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  const beepAt = (startTime, startFreq, endFreq) => {
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.type = "square";
    oscillator.frequency.setValueAtTime(startFreq, startTime);
    oscillator.frequency.exponentialRampToValueAtTime(endFreq, startTime + 0.08);

    gainNode.gain.setValueAtTime(0.0001, startTime);
    gainNode.gain.exponentialRampToValueAtTime(0.55, startTime + 0.015);
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startTime + 0.18);

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.start(startTime);
    oscillator.stop(startTime + 0.18);
  };

  const now = audioContext.currentTime;
  beepAt(now, 1760, 2200);
  beepAt(now + 0.24, 1568, 2093);
}

function flashCard(element) {
  if (!element) {
    return;
  }

  element.classList.remove("success-flash");
  void element.offsetWidth;
  element.classList.add("success-flash");
}

function handleScanSuccess(decodedText) {
  const normalized = normalizeText(decodedText);
  if (!normalized || normalized === state.lastScanText) {
    return;
  }

  state.lastScanText = normalized;
  elements.transcriptInput.value = normalized;
  setScanStatus("掃描成功，內容已直接帶入待發送文字區。");
  addLog(`掃描成功：${normalized}`);
  flashCard(elements.scannerCard);
  playSuccessDoubleBeep().catch((error) => {
    addLog(`提示音播放失敗：${error.message}`, "error");
  });
}

async function startScanner() {
  if (state.isScanning) {
    return;
  }

  if (!hasQrScannerApi()) {
    setScanStatus("掃碼元件未載入成功，請重新整理頁面。");
    addLog("Html5Qrcode 函式庫沒有載入成功。", "error");
    return;
  }

  state.lastScanText = "";
  if (!state.scanner) {
    state.scanner = new Html5Qrcode("scanner");
  }

  try {
    await state.scanner.start(
      { facingMode: "environment" },
      {
        fps: 10,
        qrbox: { width: 240, height: 240 },
        aspectRatio: 1.333334,
        formatsToSupport: [
          Html5QrcodeSupportedFormats.QR_CODE,
          Html5QrcodeSupportedFormats.EAN_13,
          Html5QrcodeSupportedFormats.EAN_8,
          Html5QrcodeSupportedFormats.CODE_128,
          Html5QrcodeSupportedFormats.CODE_39,
          Html5QrcodeSupportedFormats.UPC_A,
          Html5QrcodeSupportedFormats.UPC_E,
          Html5QrcodeSupportedFormats.ITF,
          Html5QrcodeSupportedFormats.CODABAR,
        ],
      },
      handleScanSuccess,
      () => {}
    );

    state.isScanning = true;
    setScanStatus("相機已啟動，請將 QR Code 或 barcode 對準框內。");
    addLog("掃碼已啟動。");
  } catch (error) {
    state.isScanning = false;
    setScanStatus("無法啟動相機，請確認已允許相機權限。");
    addLog(`啟動掃碼失敗：${error.message}`, "error");
  }
}

async function stopScanner() {
  if (!state.scanner || !state.isScanning) {
    return;
  }

  try {
    await state.scanner.stop();
    await state.scanner.clear();
    state.isScanning = false;
    state.scanner = null;
    setScanStatus("掃碼已停止。");
    addLog("掃碼已停止。");
  } catch (error) {
    addLog(`停止掃碼失敗：${error.message}`, "error");
  }
}

function sendText() {
  publishPayload(elements.transcriptInput.value, "mobile-web");
}

function clearContent() {
  elements.transcriptInput.value = "";
  addLog("內容已清空。");
}

function bootstrap() {
  loadSettings();
  addLog("系統已就緒。請先連線 MQTT。");

  if (!hasSpeechApi()) {
    addLog("此瀏覽器可能不支援語音辨識。", "error");
  }

  if (!hasQrScannerApi()) {
    addLog("此瀏覽器或網頁目前無法使用掃碼元件。", "error");
  }
}

elements.connectButton.addEventListener("click", connectMqtt);
elements.disconnectButton.addEventListener("click", disconnectMqtt);
elements.listenButton.addEventListener("click", startListening);
elements.stopButton.addEventListener("click", stopListening);
elements.startScanButton.addEventListener("click", startScanner);
elements.stopScanButton.addEventListener("click", stopScanner);
elements.sendButton.addEventListener("click", sendText);
elements.clearButton.addEventListener("click", clearContent);

window.addEventListener("beforeunload", () => {
  if (state.client) {
    state.client.end(true);
  }

  if (state.scanner && state.isScanning) {
    state.scanner.stop().catch(() => {});
  }
});

bootstrap();

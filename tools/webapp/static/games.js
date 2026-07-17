const gameActiveModeEl = document.querySelector("#gameActiveMode");
const gameStatusEl = document.querySelector("#gameStatus");
const gameControlsEl = document.querySelector("#gameControls");
const gameCanvas = document.querySelector("#gameCanvas");
const gameCtx = gameCanvas.getContext("2d");
const viewToggle = document.querySelector("#viewToggle");
const stopButton = document.querySelector("#gameStop");
const modeCards = document.querySelectorAll(".mode-card");

let ws = null;
let activeMode = null;
let mirrorVisible = true;
let touchAxis = { horizontal: 0, fire: false };

// Per-mode control descriptions and, for the two modes with directional
// input, a small on-screen button pad so this is usable from a phone with
// no physical keyboard.
const MODE_INFO = {
  rainbow: { label: "Rainbow Wall", controls: "No controls - just watch." },
  pong: { label: "Pong", controls: "Up / Down arrow keys move the paddle." },
  invaders: {
    label: "Space Invaders",
    controls: "Left/Right move, Space fires, P pauses, R restarts. Type your name after a high score.",
  },
  color_game: {
    label: "Color Game",
    controls: "Q/A red, W/S green, E/D blue. Enter or Space starts, submits your match, and continues past results.",
  },
};

async function gamesApi(path, body = null) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "POST" };
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function renderModeInfo(mode) {
  activeMode = mode;
  modeCards.forEach((card) => card.classList.toggle("active", card.dataset.mode === mode));

  if (!mode) {
    gameActiveModeEl.textContent = "Nothing running";
    gameStatusEl.textContent = "Pick a mode to start.";
    gameControlsEl.innerHTML = '<p class="modal-copy">Start a mode to see its controls.</p>';
    hideTouchControls();
    return;
  }

  const info = MODE_INFO[mode] || { label: mode, controls: "" };
  gameActiveModeEl.textContent = info.label;
  gameStatusEl.textContent = "Streaming to the wall.";
  gameControlsEl.innerHTML = `<p>${info.controls}</p>`;

  if (mode === "pong" || mode === "invaders") {
    showTouchControls(mode);
  } else {
    hideTouchControls();
  }
}

function showTouchControls(mode) {
  hideTouchControls();
  const wrap = document.createElement("div");
  wrap.className = "touch-controls visible";
  wrap.id = "touchControls";

  const left = document.createElement("button");
  left.textContent = "◀";
  left.addEventListener("touchstart", (e) => { e.preventDefault(); sendKey("keydown", "left"); });
  left.addEventListener("touchend", (e) => { e.preventDefault(); sendKey("keyup", "left"); });
  left.addEventListener("mousedown", () => sendKey("keydown", mode === "pong" ? "up" : "left"));
  left.addEventListener("mouseup", () => sendKey("keyup", mode === "pong" ? "up" : "left"));

  const fireOrBlank = document.createElement("button");
  if (mode === "invaders") {
    fireOrBlank.textContent = "FIRE";
    fireOrBlank.addEventListener("touchstart", (e) => { e.preventDefault(); sendKey("keydown", "fire"); });
    fireOrBlank.addEventListener("touchend", (e) => { e.preventDefault(); sendKey("keyup", "fire"); });
    fireOrBlank.addEventListener("mousedown", () => sendKey("keydown", "fire"));
    fireOrBlank.addEventListener("mouseup", () => sendKey("keyup", "fire"));
  } else {
    fireOrBlank.textContent = "";
    fireOrBlank.disabled = true;
  }

  const right = document.createElement("button");
  right.textContent = "▶";
  right.addEventListener("touchstart", (e) => { e.preventDefault(); sendKey("keydown", mode === "pong" ? "down" : "right"); });
  right.addEventListener("touchend", (e) => { e.preventDefault(); sendKey("keyup", mode === "pong" ? "down" : "right"); });
  right.addEventListener("mousedown", () => sendKey("keydown", mode === "pong" ? "down" : "right"));
  right.addEventListener("mouseup", () => sendKey("keyup", mode === "pong" ? "down" : "right"));

  wrap.append(left, fireOrBlank, right);
  gameControlsEl.appendChild(wrap);
}

function hideTouchControls() {
  const existing = document.querySelector("#touchControls");
  if (existing) existing.remove();
}

function sendKey(type, key) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, key }));
  }
}

function sendEvent(type, extra = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type, ...extra }));
  }
}

// --- Pong / Invaders keyboard relay ----------------------------------------

const KEY_MAP = {
  pong: {
    ArrowUp: "up",
    ArrowDown: "down",
  },
  invaders: {
    ArrowLeft: "left",
    a: "left",
    ArrowRight: "right",
    d: "right",
    " ": "fire",
  },
};

document.addEventListener("keydown", (event) => {
  if (!activeMode) return;
  if (activeMode === "invaders") {
    handleInvadersKeydown(event);
  } else if (activeMode === "pong") {
    const mapped = KEY_MAP.pong[event.key];
    if (mapped) sendKey("keydown", mapped);
  } else if (activeMode === "color_game") {
    handleColorGameKeydown(event);
  }
});

document.addEventListener("keyup", (event) => {
  if (!activeMode) return;
  if (activeMode === "invaders") {
    const mapped = KEY_MAP.invaders[event.key];
    if (mapped) sendKey("keyup", mapped);
  } else if (activeMode === "pong") {
    const mapped = KEY_MAP.pong[event.key];
    if (mapped) sendKey("keyup", mapped);
  }
});

function handleInvadersKeydown(event) {
  const mapped = KEY_MAP.invaders[event.key];
  if (mapped) {
    sendKey("keydown", mapped);
    return;
  }
  if (event.key === "Enter") {
    sendEvent("submit");
  } else if (event.key === "p" || event.key === "P") {
    sendEvent("pause");
  } else if (event.key === "r" || event.key === "R") {
    sendEvent("restart");
  } else if (event.key === "Backspace") {
    sendEvent("backspace");
  } else if (event.key.length === 1 && /[a-zA-Z0-9]/.test(event.key)) {
    sendEvent("char", { char: event.key });
  }
}

// --- Color Game slider relay -------------------------------------------

const colorState = { r: 128, g: 128, b: 128 };
const COLOR_STEP = 6;

function handleColorGameKeydown(event) {
  // Enter/Space advance the game's own screen flow (start -> target is any
  // key locally; match -> accuracy needs Enter; accuracy -> target accepts
  // Enter/Space/click). The browser doesn't know which screen is currently
  // active server-side, so it just always offers "advance" on these two
  // keys - the server-side screen decides whether/how to use it.
  if (event.key === "Enter" || event.key === " ") {
    sendEvent("advance");
    return;
  }

  const deltas = { dr: 0, dg: 0, db: 0 };
  switch (event.key) {
    case "q": case "Q": deltas.dr = COLOR_STEP; break;
    case "a": case "A": deltas.dr = -COLOR_STEP; break;
    case "w": case "W": deltas.dg = COLOR_STEP; break;
    case "s": case "S": deltas.dg = -COLOR_STEP; break;
    case "e": case "E": deltas.db = COLOR_STEP; break;
    case "d": case "D": deltas.db = -COLOR_STEP; break;
    default:
      return;
  }
  sendEvent("nudge", deltas);
}

// --- Canvas mirror ----------------------------------------------------------

function paintFrame(buffer) {
  if (!mirrorVisible) return;
  const bytes = new Uint8Array(buffer);
  const pixelCount = bytes.length / 3;
  const side = Math.round(Math.sqrt(pixelCount));
  // Frames are row-major RGB888 at the wall's own resolution. We don't
  // know width/height independently over the wire, but the wall is
  // always square in every mode this app drives (cols*width == rows*height
  // for every layout used here), so side*side recovers it exactly.
  if (side * side !== pixelCount || side === 0) return;

  if (gameCanvas.width !== side || gameCanvas.height !== side) {
    gameCanvas.width = side;
    gameCanvas.height = side;
  }

  const imageData = gameCtx.createImageData(side, side);
  for (let i = 0, j = 0; i < bytes.length; i += 3, j += 4) {
    imageData.data[j] = bytes[i];
    imageData.data[j + 1] = bytes[i + 1];
    imageData.data[j + 2] = bytes[i + 2];
    imageData.data[j + 3] = 255;
  }
  gameCtx.putImageData(imageData, 0, 0);
}

// --- Websocket lifecycle -----------------------------------------------

function connectWebSocket() {
  if (ws) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/game`);
  ws.binaryType = "arraybuffer";
  ws.addEventListener("message", (event) => {
    if (event.data instanceof ArrayBuffer) {
      paintFrame(event.data);
    }
  });
  ws.addEventListener("close", () => {
    ws = null;
  });
  ws.addEventListener("error", () => {
    ws = null;
  });
}

// --- Mode picker + view toggle -------------------------------------------

modeCards.forEach((card) => {
  card.addEventListener("click", async () => {
    const mode = card.dataset.mode;
    gameStatusEl.textContent = "Starting...";
    try {
      const result = await gamesApi("/api/games/start", { mode });
      renderModeInfo(result.active_mode);
      if (result.warning) {
        gameStatusEl.textContent = result.warning;
      }
      connectWebSocket();
    } catch (error) {
      gameStatusEl.textContent = error.message;
    }
  });
});

stopButton.addEventListener("click", async () => {
  gameStatusEl.textContent = "Stopping...";
  try {
    await gamesApi("/api/games/stop");
    renderModeInfo(null);
  } catch (error) {
    gameStatusEl.textContent = error.message;
  }
});

viewToggle.addEventListener("change", () => {
  mirrorVisible = !viewToggle.checked;
  gameCanvas.classList.toggle("hidden", !mirrorVisible);
  // Purely a local view preference: it never talks to the server, so it
  // cannot affect what's sent to the wall or what other connected clients
  // see. Pausing paintFrame() above (rather than disconnecting) means the
  // canvas is simply stale, not corrupted, when toggled back on.
});

async function syncGamesState() {
  try {
    const response = await fetch("/api/games/state");
    const data = await response.json();
    if (data.active_mode) {
      renderModeInfo(data.active_mode);
      connectWebSocket();
    }
  } catch (error) {
    // Games tab state is best-effort on load; alignment's own refreshState()
    // already surfaces connectivity problems elsewhere.
  }
}

syncGamesState();

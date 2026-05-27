const grid = document.querySelector("#grid");
const statusEl = document.querySelector("#status");
const currentTileEl = document.querySelector("#currentTile");
const tileList = document.querySelector("#tileList");
const layoutPreview = document.querySelector("#layoutPreview");
const colsInput = document.querySelector("#cols");
const rowsInput = document.querySelector("#rows");

let state = null;

async function api(path, body = null) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function tileNumber(x, y, cols) {
  return y * cols + x + 1;
}

function renderGrid() {
  if (!state) return;
  grid.style.gridTemplateColumns = `repeat(${state.cols}, minmax(72px, 1fr))`;
  grid.innerHTML = "";

  for (let y = state.rows - 1; y >= 0; y -= 1) {
    for (let x = 0; x < state.cols; x += 1) {
      const number = tileNumber(x, y, state.cols);
      const key = `${x},${y}`;
      const cell = document.createElement("button");
      cell.className = "cell";
      cell.dataset.x = x;
      cell.dataset.y = y;
      cell.textContent = number;
      if (state.assigned_cells[key]) {
        cell.classList.add("assigned");
        cell.title = state.assigned_cells[key].ip;
      }
      cell.addEventListener("click", () => assignCell(x, y));
      grid.appendChild(cell);
    }
  }
}

function renderState() {
  if (!state) return;
  colsInput.value = state.cols;
  rowsInput.value = state.rows;
  currentTileEl.textContent = `Current tile: ${state.current_ip || "none"}`;

  tileList.innerHTML = "";
  for (const tile of state.tiles) {
    const li = document.createElement("li");
    const assigned = state.assignments.find((item) => item.ip === tile.ip);
    li.innerHTML = `<strong>${tile.ip}</strong><br>${tile.mac || "no MAC"}<br>${assigned ? `assigned to ${assigned.tile_number}` : tile.status}`;
    tileList.appendChild(li);
  }
  if (state.tiles.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No tiles discovered yet.";
    tileList.appendChild(li);
  }

  layoutPreview.textContent = JSON.stringify(
    {
      cols: state.cols,
      rows: state.rows,
      origin: state.origin,
      order: state.order,
      tiles: state.assignments,
    },
    null,
    2
  );
  renderGrid();
}

async function refreshState() {
  state = await api("/api/state");
  renderState();
}

async function runAction(label, callback) {
  statusEl.textContent = `${label}...`;
  try {
    state = await callback();
    renderState();
    statusEl.textContent = `${label} done.`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function assignCell(gridX, gridY) {
  if (!state?.current_ip) {
    statusEl.textContent = "Start alignment first. The active physical tile will turn red.";
    return;
  }
  await runAction("Assigning tile", () => api("/api/assign", { grid_x: gridX, grid_y: gridY }));
}

document.querySelector("#applyWall").addEventListener("click", () => {
  runAction("Applying wall", () => api("/api/wall", { cols: Number(colsInput.value), rows: Number(rowsInput.value) }));
});

document.querySelector("#discover").addEventListener("click", () => {
  runAction("Discovering tiles", () => api("/api/discover", {}));
});

document.querySelector("#start").addEventListener("click", () => {
  runAction("Starting alignment", () => api("/api/start", {}));
});

document.querySelector("#save").addEventListener("click", async () => {
  statusEl.textContent = "Saving layout...";
  try {
    const result = await api("/api/save", {});
    statusEl.textContent = `Saved ${result.path}`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

document.querySelector("#load").addEventListener("click", () => {
  runAction("Loading saved layout", () => api("/api/load", {}));
});

document.querySelector("#reset").addEventListener("click", () => {
  runAction("Resetting alignment", () => api("/api/reset", {}));
});

refreshState();

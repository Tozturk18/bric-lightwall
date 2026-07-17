const grid = document.querySelector("#grid");
const statusEl = document.querySelector("#status");
const currentTileEl = document.querySelector("#currentTile");
const tileList = document.querySelector("#tileList");
const layoutPreview = document.querySelector("#layoutPreview");
const colsInput = document.querySelector("#cols");
const rowsInput = document.querySelector("#rows");
const setupModal = document.querySelector("#setupModal");
const setupForm = document.querySelector("#setupForm");

let state = null;

async function api(path, body = null) {
  const options = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Request failed: ${response.status}`);
    error.state = data.state;
    throw error;
  }
  return data;
}

function tileNumber(x, y, cols) {
  return y * cols + x + 1;
}

function renderGrid() {
  if (!state) return;
  grid.style.gridTemplateColumns = `repeat(${state.cols}, minmax(74px, 1fr))`;
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
        cell.title = state.assigned_cells[key].mac || state.assigned_cells[key].ip;
      }
      cell.addEventListener("click", () => assignCell(x, y));
      grid.appendChild(cell);
    }
  }
}

function renderState() {
  if (!state) return;

  const current = state.current_tile;
  if (current) {
    currentTileEl.innerHTML = `<strong>${current.mac || "no MAC"}</strong><span>${current.ip}</span>`;
    statusEl.textContent = "That physical tile is red. Click its position on the wall.";
  } else if (state.tiles.length > 0 && state.assignments.length === state.tiles.length) {
    currentTileEl.textContent = "All detected tiles assigned";
    statusEl.textContent = "Alignment complete. Save or download the layout.";
  } else {
    currentTileEl.textContent = "No active tile";
  }

  tileList.innerHTML = "";
  for (const tile of state.tiles) {
    const li = document.createElement("li");
    const tileKey = tile.key || tile.mac || tile.ip;
    const assigned = state.assignments.find((item) => item.key === tileKey || item.mac === tile.mac);
    li.className = assigned ? "assigned-tile" : tileKey === state.current_key ? "active-tile" : "";
    const network = tile.interface ? `${tile.interface}${tile.network ? ` ${tile.network}` : ""}` : "";
    li.innerHTML = `<strong>${tile.mac || "no MAC"}</strong><span>${tile.ip}</span>${network ? `<span>${network}</span>` : ""}<em>${assigned ? `Tile ${assigned.tile_number}` : tileKey === state.current_key ? "red now" : "waiting"}</em>`;
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

async function assignCell(gridX, gridY) {
  if (!state?.current_key) {
    statusEl.textContent = "No active tile is selected.";
    return;
  }
  statusEl.textContent = "Assigning tile and advancing...";
  try {
    state = await api("/api/assign", { grid_x: gridX, grid_y: gridY });
    renderState();
  } catch (error) {
    if (error.state) {
      state = error.state;
      renderState();
    }
    statusEl.textContent = error.message;
  }
}

setupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Discovering tiles...";
  setupModal.classList.add("busy");
  try {
    state = await api("/api/setup", { cols: Number(colsInput.value), rows: Number(rowsInput.value) });
    setupModal.classList.add("hidden");
    renderState();
  } catch (error) {
    if (error.state) {
      state = error.state;
      renderState();
    }
    setupModal.classList.remove("busy");
    statusEl.textContent = error.message;
  }
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

document.querySelector("#reset").addEventListener("click", async () => {
  statusEl.textContent = "Resetting alignment...";
  try {
    state = await api("/api/reset", {});
    renderState();
    setupModal.classList.remove("hidden", "busy");
    statusEl.textContent = "Reset complete. Enter wall size to begin again.";
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

refreshState();

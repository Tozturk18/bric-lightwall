# Browser Tile Alignment

`tools/alignment_web/alignment_server.py` runs on the MacBook or mini-PC and serves a local browser UI for assigning physical tiles to wall positions.

Install Flask on the sender machine if needed:

```bash
python3 -m pip install flask
```

Run:

```bash
cd /opt/bric-lightwall/bric-tile-receiver
python3 tools/alignment_web/alignment_server.py \
  --subnet 10.42.0.0/24 \
  --port 4210
```

Open:

```text
http://localhost:8080
```

Workflow:

1. Enter wall columns and rows.
2. Click **Apply Wall**.
3. Click **Discover Tiles**.
4. Click **Start Alignment**.
5. The current physical tile turns solid red.
6. Click the matching grid cell in the browser.
7. The tile changes to a large green assigned number.
8. Repeat until tiles are assigned.
9. Click **Save Layout** or **Download JSON**.

Use **Load Saved** to reload the current `wall_layout.json` from disk.

Tile numbering uses bottom-left wall origin:

```text
2x2:
3 4
1 2

3x2:
4 5 6
1 2 3
```

The saved `wall_layout.json` contains:

```json
{
  "cols": 2,
  "rows": 2,
  "origin": "bottom-left",
  "order": "left-to-right-then-up",
  "tiles": [
    {
      "tile_number": 1,
      "ip": "10.42.0.2",
      "grid_x": 0,
      "grid_y": 0,
      "status": "assigned",
      "last_seen": 1770000000.0
    }
  ]
}
```

Discovery first uses the existing UDP discovery responder on port `4209`, then optionally probes the requested subnet with the receiver info request on `--port`.

The web app sends only logical `64x64` RGB888 frames. It does not know about HUB75 chain order or panel rotation; the tile receiver handles logical-to-physical mapping.

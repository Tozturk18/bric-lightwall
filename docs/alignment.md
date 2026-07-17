# Browser Tile Alignment

`tools/webapp/app.py` runs on the MacBook or mini-PC and serves a local browser UI for assigning physical tiles to wall positions and starting games.

Install Flask on the sender machine if needed:

```bash
python3 -m pip install flask
```

Run:

```bash
cd /opt/bric-lightwall/bric-tile-receiver
python3 tools/webapp/app.py \
  --subnet 10.42.0.0/24 \
  --port 4210
```

If the sender also has WiFi active, constrain discovery to the Ethernet
interface:

```bash
python3 tools/discover_tiles.py --show-interfaces
python3 tools/webapp/app.py --interface en7 --subnet 10.42.0.0/24
```

Open:

```text
http://localhost:8080
```

Workflow:

1. Enter wall columns and rows in the startup dialog.
2. Click **Begin Alignment**.
3. The app discovers tile receivers and chooses the first unassigned MAC address.
4. The current physical tile turns solid red.
5. Click the matching grid cell in the browser.
6. The assigned tile changes to a white number on a black background.
7. The app automatically advances to the next unassigned MAC address and turns that tile red.
8. Repeat until tiles are assigned.
9. Click **Save** or **Download JSON**.

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
      "mac": "88:a2:9e:b3:fe:6e",
      "last_ip": "10.42.0.2",
      "listen_port": 4210,
      "grid_x": 0,
      "grid_y": 0,
      "status": "assigned",
      "last_seen": 1770000000.0
    }
  ]
}
```

Discovery first sends UDP discovery broadcasts on every local IPv4 interface,
including directed broadcasts such as `10.42.0.255`, then optionally probes the
requested subnet with the receiver info request on `--port`. Saved assignments
are keyed by MAC; `last_ip` is only a cached address from the most recent
discovery.

The web app sends only logical `64x64` RGB888 frames. It does not know about HUB75 chain order or panel rotation; the tile receiver handles logical-to-physical mapping.

The UI intentionally follows a linear flow. The only visible controls after setup are Save, Download JSON, and Reset.

Alignment defaults to `--protocol both` so visual red/number commands work with receivers that accept BRCP and receivers that still accept only the earlier BRIC chunk header. To force one protocol:

```bash
python3 tools/webapp/app.py --subnet 10.42.0.0/24 --protocol brcp
python3 tools/webapp/app.py --subnet 10.42.0.0/24 --protocol bric
```

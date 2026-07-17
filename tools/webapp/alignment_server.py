#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.digit_font import draw_number
from common.frame_sender import ChunkedUDPSender
from common.framebuffer import FrameBuffer
from common.tile_discovery import TileInfo, discover_tiles
from common.tile_identity import normalize_mac, tile_key_from_mapping, tile_key_from_tile


DEFAULT_WIDTH = 64
DEFAULT_HEIGHT = 64


@dataclass
class Assignment:
    tile_number: int
    ip: str
    grid_x: int
    grid_y: int
    status: str
    last_seen: float
    mac: str = ""
    key: str = ""
    listen_port: int = 4210

    def as_dict(self) -> Dict:
        result = {
            "tile_number": self.tile_number,
            "key": self.key or tile_key_from_mapping({"mac": self.mac, "ip": self.ip}),
            "ip": self.ip,
            "last_ip": self.ip,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "status": self.status,
            "last_seen": self.last_seen,
            "listen_port": self.listen_port,
        }
        if self.mac:
            result["mac"] = self.mac
        return result

    def as_layout_dict(self) -> Dict:
        result = {
            "tile_number": self.tile_number,
            "grid_x": self.grid_x,
            "grid_y": self.grid_y,
            "status": self.status,
            "last_seen": self.last_seen,
            "listen_port": self.listen_port,
            "last_ip": self.ip,
        }
        if self.mac:
            result["mac"] = self.mac
        return result


@dataclass
class AlignmentState:
    cols: int = 2
    rows: int = 2
    tiles: Dict[str, TileInfo] = field(default_factory=dict)
    assignments: Dict[str, Assignment] = field(default_factory=dict)
    current_key: Optional[str] = None

    def tile_sort_key(self, tile: TileInfo) -> tuple[str, str]:
        return ((tile.mac or "").lower(), tile.ip)

    def tile_number(self, grid_x: int, grid_y: int) -> int:
        return grid_y * self.cols + grid_x + 1

    def assigned_cells(self) -> Dict[str, Dict]:
        return {
            f"{assignment.grid_x},{assignment.grid_y}": assignment.as_dict()
            for assignment in self.assignments.values()
        }

    def unassigned_tiles(self) -> List[TileInfo]:
        return [
            tile for tile in sorted(self.tiles.values(), key=self.tile_sort_key)
            if tile_key_from_tile(tile) not in self.assignments
        ]

    def current_tile(self) -> Optional[TileInfo]:
        if self.current_key is None:
            return None
        return self.tiles.get(self.current_key)

    def as_dict(self) -> Dict:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "origin": "bottom-left",
            "order": "left-to-right-then-up",
            "tiles": [tile.as_dict() for tile in sorted(self.tiles.values(), key=self.tile_sort_key)],
            "assignments": [item.as_dict() for item in sorted(self.assignments.values(), key=lambda item: item.tile_number)],
            "assigned_cells": self.assigned_cells(),
            "current_key": self.current_key,
            "current_ip": self.current_tile().ip if self.current_tile() else None,
            "current_tile": self.current_tile().as_dict() if self.current_tile() else None,
        }

    def layout_json(self) -> Dict:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "origin": "bottom-left",
            "order": "left-to-right-then-up",
            "tiles": [
                item.as_layout_dict()
                for item in sorted(self.assignments.values(), key=lambda assignment: assignment.tile_number)
            ],
        }

    def load_layout(self, data: Dict, default_port: int) -> None:
        self.cols = int(data.get("cols", self.cols))
        self.rows = int(data.get("rows", self.rows))
        self.assignments.clear()
        self.current_key = None
        for item in data.get("tiles", []):
            mac = normalize_mac(str(item.get("mac") or ""))
            ip = str(item.get("ip") or item.get("last_ip") or "")
            key = tile_key_from_mapping(item)
            if not key:
                continue
            last_seen = float(item.get("last_seen") or time.time())
            tile = self.tiles.get(key) or TileInfo(
                ip=ip,
                listen_port=int(item.get("listen_port") or default_port),
                mac=mac,
                status=str(item.get("status") or "assigned"),
                last_seen=last_seen,
            )
            tile.mac = mac or normalize_mac(tile.mac)
            tile.status = str(item.get("status") or "assigned")
            tile.last_seen = last_seen
            self.tiles[key] = tile
            current_ip = tile.ip or ip
            assignment = Assignment(
                tile_number=int(item["tile_number"]),
                ip=current_ip,
                mac=tile.mac,
                key=key,
                grid_x=int(item["grid_x"]),
                grid_y=int(item["grid_y"]),
                status=tile.status,
                last_seen=last_seen,
                listen_port=tile.listen_port or default_port,
            )
            self.assignments[key] = assignment


def make_solid_frame(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    fb = FrameBuffer(width, height)
    fb.clear(color)
    return fb.copy_bytes()


def make_number_frame(width: int, height: int, number: int) -> bytes:
    fb = FrameBuffer(width, height)
    draw_number(fb, number, color=(255, 255, 255), background=(0, 0, 0))
    return fb.copy_bytes()


def send_frame_to_tile(tile: TileInfo, frame: bytes, args: argparse.Namespace) -> None:
    with ChunkedUDPSender(
        tile.ip,
        port=tile.listen_port or args.receiver_port,
        width=args.width,
        height=args.height,
        chunk_size=args.chunk_size,
        protocol=args.protocol,
        timeout=args.socket_timeout,
    ) as sender:
        for _ in range(max(1, args.visual_repeats)):
            sender.send_frame(frame)
            time.sleep(args.visual_repeat_delay)


def send_solid_to_tile(tile: TileInfo, color: tuple[int, int, int], args: argparse.Namespace) -> None:
    send_frame_to_tile(tile, make_solid_frame(args.width, args.height, color), args)


def send_number_to_tile(tile: TileInfo, number: int, args: argparse.Namespace) -> None:
    send_frame_to_tile(tile, make_number_frame(args.width, args.height, number), args)


def create_app(args: argparse.Namespace, on_before_drive: Optional[Callable[[], None]] = None):
    """
    on_before_drive, if given, is called immediately before this app sends
    any frame to a tile - i.e. right before alignment is about to start
    actively driving the wall. It exists so a caller embedding this app
    inside a larger last-wins setup (see tools/webapp/app.py) can stop a
    currently-running game first. When run standalone via this file's own
    __main__, on_before_drive is never passed, so behavior is unchanged.
    """
    try:
        from flask import Flask, jsonify, request, send_file
    except ImportError as error:
        raise SystemExit(
            "Flask is required for the alignment web app. Install with: python3 -m pip install flask"
        ) from error

    app = Flask(__name__, template_folder="templates", static_folder="static")
    state = AlignmentState()
    layout_path = Path(args.output).resolve()

    def choose_next_tile() -> Optional[TileInfo]:
        remaining = state.unassigned_tiles()
        state.current_key = tile_key_from_tile(remaining[0]) if remaining else None
        if state.current_key:
            if on_before_drive:
                on_before_drive()
            tile = state.tiles[state.current_key]
            send_solid_to_tile(tile, (255, 0, 0), args)
            return tile
        return None

    def discovery_options(data: Optional[Dict] = None) -> Dict:
        data = data or {}
        interfaces = data.get("interfaces") or data.get("interface") or args.interfaces
        if isinstance(interfaces, str):
            interfaces = [item.strip() for item in interfaces.split(",") if item.strip()]
        return {
            "subnet": data.get("subnet") or args.subnet,
            "receiver_port": args.receiver_port,
            "discovery_port": args.discovery_port,
            "timeout": args.discovery_timeout,
            "limit": args.scan_limit,
            "interfaces": interfaces,
            "scan_auto_subnets": bool(
                data.get("scan_auto_subnets", args.scan_auto_subnets)
            ),
        }

    @app.get("/")
    def index():
        return app.jinja_env.get_template("index.html").render()

    @app.get("/api/state")
    def api_state():
        return jsonify(state.as_dict())

    @app.post("/api/setup")
    def api_setup():
        data = request.get_json(force=True, silent=True) or {}
        cols = int(data.get("cols", state.cols))
        rows = int(data.get("rows", state.rows))
        if cols <= 0 or rows <= 0 or cols > 64 or rows > 64:
            return jsonify({"error": "rows and columns must be 1..64"}), 400

        state.cols = cols
        state.rows = rows
        state.assignments.clear()
        state.current_key = None

        tiles = discover_tiles(**discovery_options(data))
        state.tiles = {tile_key_from_tile(tile): tile for tile in tiles if tile_key_from_tile(tile)}
        if not state.tiles:
            return jsonify({"error": "no tile receivers discovered", "state": state.as_dict()}), 404

        try:
            choose_next_tile()
        except OSError as error:
            return jsonify({"error": f"discovered tiles, but failed to send red frame: {error}", "state": state.as_dict()}), 502
        return jsonify(state.as_dict())

    @app.post("/api/wall")
    def api_wall():
        data = request.get_json(force=True, silent=True) or {}
        cols = int(data.get("cols", state.cols))
        rows = int(data.get("rows", state.rows))
        if cols <= 0 or rows <= 0 or cols > 64 or rows > 64:
            return jsonify({"error": "rows and columns must be 1..64"}), 400
        state.cols = cols
        state.rows = rows
        state.assignments.clear()
        state.current_key = None
        return jsonify(state.as_dict())

    @app.post("/api/discover")
    def api_discover():
        data = request.get_json(force=True, silent=True) or {}
        tiles = discover_tiles(**discovery_options(data))
        state.tiles = {tile_key_from_tile(tile): tile for tile in tiles if tile_key_from_tile(tile)}
        state.current_key = None
        return jsonify(state.as_dict())

    @app.post("/api/start")
    def api_start():
        if not state.tiles:
            return jsonify({"error": "discover tiles before starting alignment"}), 400
        try:
            choose_next_tile()
        except OSError as error:
            return jsonify({"error": f"failed to send red frame: {error}"}), 502
        return jsonify(state.as_dict())

    @app.post("/api/assign")
    def api_assign():
        data = request.get_json(force=True, silent=True) or {}
        if state.current_key is None:
            return jsonify({"error": "no current tile; start alignment first"}), 400
        grid_x = int(data.get("grid_x", -1))
        grid_y = int(data.get("grid_y", -1))
        if grid_x < 0 or grid_y < 0 or grid_x >= state.cols or grid_y >= state.rows:
            return jsonify({"error": "grid cell is outside the wall"}), 400
        if f"{grid_x},{grid_y}" in state.assigned_cells():
            return jsonify({"error": "grid cell is already assigned"}), 409

        tile = state.tiles[state.current_key]
        key = tile_key_from_tile(tile)
        assignment = Assignment(
            tile_number=state.tile_number(grid_x, grid_y),
            ip=tile.ip,
            mac=normalize_mac(tile.mac),
            key=key,
            grid_x=grid_x,
            grid_y=grid_y,
            status="assigned",
            last_seen=time.time(),
            listen_port=tile.listen_port or args.receiver_port,
        )
        state.assignments[key] = assignment

        try:
            send_number_to_tile(tile, assignment.tile_number, args)
            choose_next_tile()
        except OSError as error:
            return jsonify({"error": f"assignment saved but tile send failed: {error}", "state": state.as_dict()}), 502

        return jsonify(state.as_dict())

    @app.post("/api/save")
    def api_save():
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(json.dumps(state.layout_json(), indent=2) + "\n", encoding="utf-8")
        return jsonify({"path": str(layout_path), "layout": state.layout_json()})

    @app.post("/api/load")
    def api_load():
        if not layout_path.exists():
            return jsonify({"error": f"{layout_path} does not exist"}), 404
        tiles = discover_tiles(**discovery_options())
        if tiles:
            state.tiles = {tile_key_from_tile(tile): tile for tile in tiles if tile_key_from_tile(tile)}
        data = json.loads(layout_path.read_text(encoding="utf-8"))
        state.load_layout(data, default_port=args.receiver_port)
        return jsonify(state.as_dict())

    @app.get("/api/download")
    def api_download():
        if not layout_path.exists():
            layout_path.write_text(json.dumps(state.layout_json(), indent=2) + "\n", encoding="utf-8")
        return send_file(layout_path, as_attachment=True, download_name="wall_layout.json")

    @app.post("/api/reset")
    def api_reset():
        if on_before_drive and state.tiles:
            on_before_drive()
        black = make_solid_frame(args.width, args.height, (0, 0, 0))
        for tile in state.tiles.values():
            try:
                send_frame_to_tile(tile, black, args)
            except OSError:
                pass
        state.assignments.clear()
        state.current_key = None
        return jsonify(state.as_dict())

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local browser tile alignment GUI for BRIC Light Wall.")
    parser.add_argument("--subnet", default="", help="Optional subnet to scan, e.g. 10.42.0.0/24")
    parser.add_argument(
        "--interface",
        action="append",
        dest="interfaces",
        default=[],
        help=(
            "Limit discovery to a local interface, e.g. en7 on macOS, eth0 on Linux, "
            "Ethernet on Windows, or an adapter IPv4 address. Repeatable."
        ),
    )
    parser.add_argument(
        "--scan-auto-subnets",
        action="store_true",
        help="Actively probe bounded local subnets in addition to broadcast discovery.",
    )
    parser.add_argument(
        "--no-refresh-layout-ips",
        dest="refresh_layout_ips",
        action="store_false",
        default=True,
        help="Do not refresh saved layout current routes by MAC before starting games in the combined web app.",
    )
    parser.add_argument("--port", dest="receiver_port", type=int, default=4210, help="Tile receiver UDP port")
    parser.add_argument("--web-host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--discovery-port", type=int, default=4209)
    parser.add_argument("--discovery-timeout", type=float, default=0.35)
    parser.add_argument("--scan-limit", type=int, default=256)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="both")
    parser.add_argument("--socket-timeout", type=float, default=1.0)
    parser.add_argument("--visual-repeats", type=int, default=3)
    parser.add_argument("--visual-repeat-delay", type=float, default=0.025)
    parser.add_argument("--output", default="wall_layout.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args)
    print(f"Open http://localhost:{args.web_port}")
    app.run(host=args.web_host, port=args.web_port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.frame_mirror import FrameMirror
from common.frame_sender import ChunkedUDPSender, pace_frame
from common.framebuffer import FrameBuffer
from common.wall_layout import load_resolved_wall_layout


Color = Tuple[int, int, int]


def hsv_to_rgb(h: float, s: float = 1.0, v: float = 1.0) -> Color:
    """Convert HSV (h in [0,1)) to RGB 0-255."""
    h = h % 1.0
    i = int(h * 6)
    f = (h * 6) - i
    p = int(255 * v * (1 - s))
    q = int(255 * v * (1 - f * s))
    t = int(255 * v * (1 - (1 - f) * s))
    vv = int(255 * v)
    i %= 6
    if i == 0:
        return vv, t, p
    if i == 1:
        return q, vv, p
    if i == 2:
        return p, vv, t
    if i == 3:
        return p, q, vv
    if i == 4:
        return t, p, vv
    return vv, p, q


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rainbow cycle wall test for BRIC Light Wall")
    parser.add_argument("--layout", default="wall_layout.json", help="Path to wall_layout.json")
    parser.add_argument("--host", help="Fallback single tile IP if layout missing")
    parser.add_argument("--port", type=int, default=4210, help="Fallback tile UDP port")
    parser.add_argument("--width", type=int, default=64, help="Tile width")
    parser.add_argument("--height", type=int, default=64, help="Tile height")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="brcp")
    parser.add_argument("--speed", type=float, default=24.0, help="Pixels per second rainbow moves")
    parser.add_argument("--interface", action="append", dest="interfaces", default=[], help="Local interface for MAC discovery, e.g. en7")
    parser.add_argument("--subnet", default="", help="Optional subnet to probe for current tile IPs")
    parser.add_argument("--scan-auto-subnets", action="store_true", help="Probe bounded local subnets for current tile IPs")
    parser.add_argument("--no-resolve-layout", action="store_true", help="Use saved layout IPs without MAC rediscovery")
    parser.add_argument("--mirror-port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--max-frames", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def run(args: argparse.Namespace, stop_event: threading.Event) -> int:
    """
    The rainbow loop itself, driven by an externally-owned stop_event
    instead of signal handlers. Used both by main() (CLI entry point, with
    a signal-driven stop_event) and directly by the orchestrator's
    WallDriverManager, which runs this in a background thread rather than
    a subprocess since rainbow_wall has no pygame/window dependency.
    """
    layout_path = Path(args.layout)
    tiles: List[Dict] = []
    cols = 1
    rows = 1
    origin = "top-left"

    if layout_path.exists():
        try:
            resolved = load_resolved_wall_layout(
                layout_path,
                default_port=args.port,
                discovery_subnet=args.subnet,
                interfaces=args.interfaces,
                scan_auto_subnets=args.scan_auto_subnets,
                resolve_by_mac=not args.no_resolve_layout,
            )
        except Exception as error:
            print(f"failed to load layout {layout_path}: {error}", file=sys.stderr)
            return 2
        if resolved.unresolved:
            print(f"unresolved tile MAC(s): {', '.join(resolved.unresolved)}", file=sys.stderr)
            return 2
        if resolved.ambiguous:
            print(f"ambiguous tile MAC(s): {', '.join(resolved.ambiguous)}", file=sys.stderr)
            return 2
        tiles = resolved.tiles
        cols = resolved.cols
        rows = resolved.rows
        origin = resolved.origin

    if not tiles:
        if not args.host:
            print("Either --host or a valid --layout is required", file=sys.stderr)
            return 2
        tiles = [{"ip": args.host, "grid_x": 0, "grid_y": 0, "port": args.port}]
        cols = 1
        rows = 1

    wall_w = cols * args.width
    wall_h = rows * args.height

    # Prepare senders keyed by ip:port
    senders: Dict[str, ChunkedUDPSender] = {}
    for tile in tiles:
        key = f"{tile['ip']}:{tile.get('port', args.port)}"
        if key in senders:
            continue
        senders[key] = ChunkedUDPSender(
            tile["ip"],
            port=tile.get("port", args.port),
            width=args.width,
            height=args.height,
            chunk_size=args.chunk_size,
            protocol=args.protocol,
        )

    print(f"Streaming rainbow to {len(tiles)} tile(s): {wall_w}x{wall_h} at {args.fps:g} FPS")

    mirror: Optional[FrameMirror] = FrameMirror(args.mirror_port) if args.mirror_port else None

    fb = FrameBuffer(wall_w, wall_h)

    offset = 0.0
    frames = 0
    last_time = time.monotonic()
    try:
        while not stop_event.is_set():
            frame_start = time.monotonic()
            dt = min(0.05, frame_start - last_time)
            last_time = frame_start

            offset += args.speed * dt

            # draw rainbow columns
            for x in range(wall_w):
                hue = ((x + offset) / float(wall_w)) % 1.0
                color = hsv_to_rgb(hue)
                fb.fill_rect(x, 0, 1, wall_h, color)

            frame = fb.copy_bytes()

            row_stride_full = wall_w * 3
            tile_row_stride = args.width * 3

            for tile in tiles:
                xoff = tile["grid_x"] * args.width
                if origin == "bottom-left":
                    yoff = (rows - 1 - tile["grid_y"]) * args.height
                else:
                    yoff = tile["grid_y"] * args.height

                tile_bytes = bytearray(args.width * args.height * 3)
                for row in range(args.height):
                    src_start = ((yoff + row) * wall_w + xoff) * 3
                    dst_start = row * tile_row_stride
                    tile_bytes[dst_start: dst_start + tile_row_stride] = frame[src_start: src_start + tile_row_stride]

                key = f"{tile['ip']}:{tile.get('port', args.port)}"
                try:
                    senders[key].send_frame(tile_bytes)
                except OSError as error:
                    print(f"send to {tile['ip']} failed: {error}", file=sys.stderr)

            if mirror is not None:
                mirror.send(frame)

            frames += 1
            if args.max_frames and frames >= args.max_frames:
                stop_event.set()

            pace_frame(frame_start, args.fps)
    finally:
        for s in senders.values():
            try:
                s.close()
            except Exception:
                pass
        if mirror is not None:
            mirror.close()

    return 0


def main() -> int:
    args = parse_args()

    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    return run(args, stop_event)


if __name__ == "__main__":
    raise SystemExit(main())

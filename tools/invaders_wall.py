#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.frame_sender import ChunkedUDPSender, pace_frame
from common.framebuffer import FrameBuffer


Color = Tuple[int, int, int]


# Simple 8x8 retro invader sprites, two frames each (legs/antenna wiggle)
SPRITES: List[List[List[str]]] = [
    [
        [
            "00111100",
            "01111110",
            "11111111",
            "11011011",
            "11111111",
            "01100110",
            "01011010",
            "10000001",
        ],
        [
            "00111100",
            "01111110",
            "11111111",
            "11011011",
            "11111111",
            "01100110",
            "01000100",
            "00100010",
        ],
    ],
    [
        [
            "00011000",
            "00111100",
            "01111110",
            "11111111",
            "11111111",
            "01100110",
            "01100110",
            "11000011",
        ],
        [
            "00011000",
            "00111100",
            "01111110",
            "11111111",
            "11111111",
            "01100110",
            "00100100",
            "00011000",
        ],
    ],
    [
        [
            "00100100",
            "01111110",
            "11111111",
            "11111111",
            "11111111",
            "01101110",
            "01011010",
            "10000001",
        ],
        [
            "00100100",
            "01111110",
            "11111111",
            "11111111",
            "11111111",
            "01101110",
            "00100100",
            "00011000",
        ],
    ],
]


PALETTE: List[Color] = [
    (80, 220, 100),
    (80, 200, 220),
    (220, 100, 220),
    (255, 200, 80),
    (200, 130, 255),
]


def draw_sprite(fb: FrameBuffer, x: int, y: int, sprite: List[str], color: Color) -> None:
    h = len(sprite)
    w = len(sprite[0]) if h else 0
    for ry in range(h):
        row = sprite[ry]
        for rx in range(w):
            if row[rx] == "1":
                fb.set_pixel(x + rx, y + ry, color)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retro invaders wall test for BRIC Light Wall")
    parser.add_argument("--layout", default="wall_layout.json", help="Path to wall_layout.json")
    parser.add_argument("--host", help="Fallback single tile IP if layout missing")
    parser.add_argument("--port", type=int, default=4210, help="Fallback tile UDP port")
    parser.add_argument("--width", type=int, default=64, help="Tile width")
    parser.add_argument("--height", type=int, default=64, help="Tile height")
    parser.add_argument("--fps", type=float, default=20.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="brcp")
    parser.add_argument("--speed", type=float, default=1.6, help="Animation speed multiplier")
    return parser.parse_args()


def make_starfield(w: int, h: int, count: int, seed: int = 42) -> List[Tuple[int, int, float]]:
    rnd = random.Random(seed)
    stars: List[Tuple[int, int, float]] = []
    for _ in range(count):
        x = rnd.randrange(0, w)
        y = rnd.randrange(0, h)
        phase = rnd.random() * math.pi * 2
        stars.append((x, y, phase))
    return stars


def main() -> int:
    args = parse_args()

    stop = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    layout_path = Path(args.layout)
    tiles: List[Dict] = []
    cols = 1
    rows = 1
    origin = "top-left"

    if layout_path.exists():
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except Exception as error:
            print(f"failed to load layout {layout_path}: {error}", file=sys.stderr)
            return 2
        cols = int(layout.get("cols") or 0) or 0
        rows = int(layout.get("rows") or 0) or 0
        origin = layout.get("origin") or origin
        for item in layout.get("tiles", []):
            ip = item.get("ip")
            if not ip:
                continue
            grid_x = int(item.get("grid_x", 0))
            grid_y = int(item.get("grid_y", 0))
            listen_port = int(item.get("listen_port") or args.port)
            tiles.append({"ip": ip, "grid_x": grid_x, "grid_y": grid_y, "port": listen_port})
        if tiles and cols <= 0:
            cols = max(t["grid_x"] for t in tiles) + 1
        if tiles and rows <= 0:
            rows = max(t["grid_y"] for t in tiles) + 1

    if not tiles:
        if not args.host:
            print("Either --host or a valid --layout is required", file=sys.stderr)
            return 2
        tiles = [{"ip": args.host, "grid_x": 0, "grid_y": 0, "port": args.port}]
        cols = 1
        rows = 1

    wall_w = cols * args.width
    wall_h = rows * args.height

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

    print(f"Streaming retro invaders to {len(tiles)} tile(s): {wall_w}x{wall_h} at {args.fps:g} FPS")

    fb = FrameBuffer(wall_w, wall_h)

    # formation geometry
    sprite_h = len(SPRITES[0][0])
    sprite_w = len(SPRITES[0][0][0])
    spacing_x = max(4, sprite_w // 2)
    spacing_y = max(6, sprite_h // 2)
    cols_form = max(1, wall_w // (sprite_w + spacing_x))
    rows_form = min(5, max(1, (wall_h - 20) // (sprite_h + spacing_y)))
    formation_width = cols_form * sprite_w + (cols_form - 1) * spacing_x
    start_x = max(0, (wall_w - formation_width) // 2)
    start_y = 12

    # stars
    stars = make_starfield(wall_w, wall_h, max(16, wall_w * wall_h // 1024))

    phase = 0.0
    last_time = time.monotonic()
    leg_toggle = False
    leg_timer = 0.0
    leg_interval = 0.45 / args.speed

    try:
        while not stop:
            t0 = time.monotonic()
            dt = min(0.05, t0 - last_time)
            last_time = t0
            phase += dt * args.speed

            leg_timer += dt
            if leg_timer >= leg_interval:
                leg_timer -= leg_interval
                leg_toggle = not leg_toggle

            fb.clear((6, 8, 20))  # deep space blue background

            # draw subtle scanlines
            for y in range(0, wall_h, 4):
                fb.draw_line_h(0, y, wall_w, (4, 6, 12))

            # stars (twinkle)
            for (sx, sy, sphase) in stars:
                b = 0.6 + 0.4 * math.sin(phase * 2.0 + sphase)
                val = int(255 * max(0.08, b))
                fb.set_pixel(sx, sy, (val, val, val))

            # horizontal formation offset (retro left-right sway)
            amplitude = max(4, min(16, wall_w // 16))
            sway = int(math.sin(phase * 0.9) * amplitude)

            for ry in range(rows_form):
                for cx in range(cols_form):
                    sx = start_x + cx * (sprite_w + spacing_x) + sway
                    sy = start_y + ry * (sprite_h + spacing_y) + int(math.sin(phase * 1.6 + cx * 0.15) * 1.5)
                    sprite_index = (ry + cx) % len(SPRITES)
                    frame = 1 if leg_toggle else 0
                    draw_sprite(fb, sx, sy, SPRITES[sprite_index][frame], PALETTE[ry % len(PALETTE)])

            # small HUD: score and label
            # left score (retro 7-seg-ish) with simple pixels
            fb.fill_rect(6, wall_h - 14, 36, 10, (12, 14, 22))
            fb.fill_rect(wall_w - 42, wall_h - 14, 36, 10, (12, 14, 22))
            # draw tiny 'INVADERS' text as blocks
            label = "INVADERS"
            for i, ch in enumerate(label):
                if ch == ' ':
                    continue
                x = 48 + i * 6
                y = wall_h - 12
                fb.fill_rect(x, y, 4, 2, (200, 200, 60))

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

            pace_frame(t0, args.fps)
    finally:
        for s in senders.values():
            try:
                s.close()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

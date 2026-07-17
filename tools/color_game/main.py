#!/usr/bin/env python3
# =============================================================================
# main.py - Color Match entry point, streaming to the BRIC Light Wall over
# our existing ChunkedUDPSender/wall_layout.json path (not the standalone
# TCP wall/ package this game shipped with originally).
#
# Local play only:
#     python3 tools/color_game/main.py --no-stream
#
# With LED wall output (single tile):
#     python3 tools/color_game/main.py --host 10.42.0.2
#
# With LED wall output (multi-tile, uses wall_layout.json by default):
#     python3 tools/color_game/main.py
# =============================================================================

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
GAME_DIR = Path(__file__).resolve().parent
if str(GAME_DIR) not in sys.path:
    sys.path.insert(0, str(GAME_DIR))

import pygame

from common.frame_mirror import DEFAULT_MIRROR_PORT, FrameMirror
from common.frame_sender import ChunkedUDPSender, pace_frame
from common.wall_layout import load_resolved_wall_layout
from common.web_input import DEFAULT_INPUT_PORT, start_input_listener

from config import WIDTH, HEIGHT, FPS, SLIDER_XS, SLIDER_Y
from sliders import KeyboardSliderInput, WebSliderInput
from screens.start import StartScreen
from screens.target import TargetScreen
from screens.match import MatchScreen
from screens.accuracy import AccuracyScreen

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Color Match - LED wall game")
    parser.add_argument("--layout", default="wall_layout.json", help="Path to wall_layout.json")
    parser.add_argument("--host", help="Fallback single tile IP if layout missing")
    parser.add_argument("--port", type=int, default=4210, help="Fallback tile UDP port")
    parser.add_argument("--width", type=int, default=64, help="Tile width")
    parser.add_argument("--height", type=int, default=64, help="Tile height")
    parser.add_argument("--fps", type=float, default=FPS, help="Game and wall frame rate")
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="brcp")
    parser.add_argument("--fullscreen-preview", action="store_true")
    parser.add_argument("--preview-scale", type=int, help="Pixel scale for the local preview window")
    parser.add_argument("--no-stream", action="store_true", help="Run the local preview without sending UDP frames")
    parser.add_argument("--interface", action="append", dest="interfaces", default=[], help="Local interface for MAC discovery, e.g. en7, eth0, Ethernet, or an adapter IPv4")
    parser.add_argument("--subnet", default="", help="Optional subnet to probe for current tile IPs")
    parser.add_argument("--scan-auto-subnets", action="store_true", help="Probe bounded local subnets for current tile IPs")
    parser.add_argument("--no-resolve-layout", action="store_true", help="Use saved layout IPs without MAC rediscovery")
    parser.add_argument("--web-input", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--input-port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--mirror-port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--max-frames", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def _make_web_slider_handler(web_input: WebSliderInput):
    """
    Build the callback passed to start_input_listener().

    Expected browser messages:
      {"type": "set", "r": 128, "g": 64, "b": 200}
      {"type": "nudge", "dr": 2, "dg": 0, "db": -2}
      {"type": "advance"}   -- see _synthesize_events() below
    Malformed messages are ignored rather than raising, since a stale or
    malformed browser message must never take down the game loop.
    """

    def handler(message: dict) -> None:
        msg_type = message.get("type")
        if msg_type == "set":
            try:
                web_input.set_values(
                    int(message.get("r", 0)),
                    int(message.get("g", 0)),
                    int(message.get("b", 0)),
                )
            except (TypeError, ValueError):
                pass
        elif msg_type == "nudge":
            try:
                web_input.nudge(
                    int(message.get("dr", 0)),
                    int(message.get("dg", 0)),
                    int(message.get("db", 0)),
                )
            except (TypeError, ValueError):
                pass
        elif msg_type == "advance":
            web_input.push_event(message)

    return handler


def _synthesize_events(web_input: WebSliderInput, pygame) -> list:
    """
    Translate WebSliderInput's queued "advance" events into real
    pygame.event.Event objects, so every screen's existing update(dt,
    events) - which checks e.type/e.key on the real pygame event list -
    needs no changes of its own. Each "advance" becomes a KEYDOWN/K_RETURN,
    which is accepted by all three of this game's transition points:
    StartScreen (any KEYDOWN), MatchScreen (specifically K_RETURN), and
    AccuracyScreen (K_RETURN or K_SPACE).
    """
    events = []
    for _event in web_input.drain_events():
        events.append(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    return events


class WallConfig:
    def __init__(self, tiles: List[Dict], cols: int, rows: int, origin: str = "top-left"):
        self.tiles = tiles
        self.cols = cols
        self.rows = rows
        self.origin = origin


def load_wall_config(args: argparse.Namespace) -> WallConfig:
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
            raise RuntimeError(f"failed to load layout {layout_path}: {error}") from error
        if resolved.unresolved:
            raise RuntimeError(f"unresolved tile MAC(s): {', '.join(resolved.unresolved)}")
        if resolved.ambiguous:
            raise RuntimeError(f"ambiguous tile MAC(s): {', '.join(resolved.ambiguous)}")
        tiles = resolved.tiles
        cols = resolved.cols
        rows = resolved.rows
        origin = resolved.origin

    if not tiles:
        if args.no_stream:
            return WallConfig([], 1, 1, origin)
        if not args.host:
            raise RuntimeError("Either --host or a valid --layout is required")
        tiles = [{"ip": args.host, "grid_x": 0, "grid_y": 0, "port": args.port}]
        cols = 1
        rows = 1

    return WallConfig(tiles, cols, rows, origin)


def make_senders(args: argparse.Namespace, tiles: List[Dict]) -> Dict[str, ChunkedUDPSender]:
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
    return senders


def render_wall_frame(surface: pygame.Surface, wall_w: int, wall_h: int) -> bytes:
    """pygame.Surface (game resolution) -> row-major RGB888 bytes at wall resolution."""
    scaled = pygame.transform.smoothscale(surface, (wall_w, wall_h))
    # surfarray gives (W, H, 3); wire format is row-major (y outer, x inner) = (H, W, 3).
    arr = pygame.surfarray.array3d(scaled)
    return arr.transpose(1, 0, 2).tobytes()


def send_wall_frame(
    args: argparse.Namespace,
    config: WallConfig,
    senders: Dict[str, ChunkedUDPSender],
    frame: bytes,
    wall_w: int,
) -> None:
    tile_row_stride = args.width * 3
    for tile in config.tiles:
        xoff = tile["grid_x"] * args.width
        if config.origin == "bottom-left":
            yoff = (config.rows - 1 - tile["grid_y"]) * args.height
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


def main() -> int:
    args = parse_args()

    try:
        config = load_wall_config(args)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    wall_w = config.cols * args.width
    wall_h = config.rows * args.height
    senders = {} if args.no_stream else make_senders(args, config.tiles)
    mirror: Optional[FrameMirror] = FrameMirror(args.mirror_port) if args.mirror_port else None

    pygame.init()
    pygame.display.set_caption("Color Match")
    flags = pygame.FULLSCREEN if args.fullscreen_preview else 0
    if args.preview_scale:
        pygame.display.set_mode((WIDTH * args.preview_scale // 4, HEIGHT * args.preview_scale // 4), flags)
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    clock = pygame.time.Clock()

    if args.web_input:
        sliders = WebSliderInput()
        input_port = args.input_port or DEFAULT_INPUT_PORT
        start_input_listener(_make_web_slider_handler(sliders), port=input_port)
    else:
        sliders = KeyboardSliderInput(x_positions=SLIDER_XS, y=SLIDER_Y)

    screen_map = {
        "start": StartScreen(screen),
        "target": TargetScreen(screen),
        "match": MatchScreen(screen, sliders),
        "accuracy": AccuracyScreen(screen),
    }

    state = "start"
    screen_map[state].enter(data={})

    target_list = ", ".join(f"{t['ip']}:{t.get('port', args.port)}" for t in config.tiles)
    if args.no_stream:
        target_list = "preview only"
    print(f"Color Match {wall_w}x{wall_h} at {args.fps:g} FPS ({target_list})")

    running = True
    frames = 0
    try:
        while running:
            frame_start = time.monotonic()
            dt = clock.tick(FPS) / 1000.0
            events = pygame.event.get()
            if args.web_input:
                events = events + _synthesize_events(sliders, pygame)

            for event in events:
                if event.type == pygame.QUIT:
                    running = False
                    break
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                    break

            if not running:
                break

            next_state, data = screen_map[state].update(dt, events)
            if next_state and next_state != state:
                state = next_state
                screen_map[state].enter(data=data)

            screen_map[state].draw()
            pygame.display.flip()

            if senders or mirror is not None:
                frame = render_wall_frame(screen, wall_w, wall_h)
                if senders:
                    send_wall_frame(args, config, senders, frame, wall_w)
                if mirror is not None:
                    mirror.send(frame)

            frames += 1
            if args.max_frames and frames >= args.max_frames:
                running = False

            pace_frame(frame_start, args.fps)
    finally:
        for sender in senders.values():
            try:
                sender.close()
            except Exception:
                pass
        if mirror is not None:
            mirror.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

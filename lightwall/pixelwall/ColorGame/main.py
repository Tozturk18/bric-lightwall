#!/usr/bin/env python3
# =============================================================================
# main.py – Color Match entry point
#
# Local play (laptop):
#     python main.py
#
# With LED wall output:
#     python main.py --wall \
#         --rows 2 --cols 2 --tile-w 64 --tile-h 64 \
#         --hosts 10.42.0.2 10.42.0.3 10.42.0.5 10.42.0.4
#
# Hosts are supplied in snake order (see wall/config.py for diagram).
# Missing port defaults to --port 8765.  Override per-host with "ip:port".
#
# --wall-fps controls how often frames are sent to the wall (default 30).
# The game itself always runs at FPS (60).
# =============================================================================

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import argparse
import logging
import pygame

from config import WIDTH, HEIGHT, FPS, SLIDER_XS, SLIDER_Y
from sliders import KeyboardSliderInput as SliderClass
from screens.start    import StartScreen
from screens.target   import TargetScreen
from screens.match    import MatchScreen
from screens.accuracy import AccuracyScreen

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)s  %(name)s  %(message)s")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Color Match – LED wall game")

    # Wall output (optional)
    p.add_argument("--wall", action="store_true",
                   help="Enable live output to LED wall")
    p.add_argument("--rows", type=int, default=2,
                   help="Tile rows on the wall (default: 2)")
    p.add_argument("--cols", type=int, default=2,
                   help="Tile columns on the wall (default: 2)")
    p.add_argument("--tile-w", type=int, default=64,
                   help="Tile width in pixels (default: 64)")
    p.add_argument("--tile-h", type=int, default=64,
                   help="Tile height in pixels (default: 64)")
    p.add_argument("--port", type=int, default=8765,
                   help="Default TCP port for all Pis (default: 8765)")
    p.add_argument("--hosts", nargs="+", metavar="IP[:PORT]",
                   default=[],
                   help="Pi addresses in snake order, e.g. 10.42.0.2 10.42.0.3 …")
    p.add_argument("--wall-fps", type=int, default=30,
                   help="Frame rate sent to the wall (default: 30)")

    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # ---- Optional wall sender -------------------------------------------
    wall = None
    if args.wall:
        from wall import WallConfig, WallSender
        cfg  = WallConfig.from_args(
            rows         = args.rows,
            cols         = args.cols,
            tile_w       = args.tile_w,
            tile_h       = args.tile_h,
            hosts        = args.hosts,
            default_port = args.port,
        )
        wall = WallSender(cfg)

    # ---- pygame setup ---------------------------------------------------
    pygame.init()
    pygame.display.set_caption("Color Match")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock  = pygame.time.Clock()

    # ---- Slider input ---------------------------------------------------
    sliders = SliderClass(x_positions=SLIDER_XS, y=SLIDER_Y)

    # ---- Screens --------------------------------------------------------
    screen_map = {
        "start":    StartScreen(screen),
        "target":   TargetScreen(screen),
        "match":    MatchScreen(screen, sliders),
        "accuracy": AccuracyScreen(screen),
    }

    state = "start"
    screen_map[state].enter(data={})

    # Wall frame pacing: send every N game frames
    wall_frame_every = max(1, FPS // args.wall_fps)
    game_frame       = 0

    # ---- Game loop ------------------------------------------------------
    running = True
    while running:
        dt     = clock.tick(FPS) / 1000.0
        events = pygame.event.get()

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

        # Send to wall at wall_fps rate (every Nth game frame)
        if wall and game_frame % wall_frame_every == 0:
            wall.send_surface(screen)

        game_frame += 1

    # ---- Cleanup --------------------------------------------------------
    if wall:
        wall.close()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
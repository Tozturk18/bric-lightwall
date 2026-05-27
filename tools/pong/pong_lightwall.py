#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple


TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.frame_sender import ChunkedUDPSender, pace_frame
from common.framebuffer import FrameBuffer


Color = Tuple[int, int, int]


@dataclass
class PongState:
    width: int
    height: int
    player_y: float
    ai_y: float
    ball_x: float
    ball_y: float
    ball_vx: float
    ball_vy: float
    player_score: int = 0
    ai_score: int = 0

    @property
    def paddle_h(self) -> int:
        return max(10, self.height // 5)

    @property
    def paddle_w(self) -> int:
        return max(2, self.width // 32)

    @property
    def ball_size(self) -> int:
        return max(2, self.width // 24)

    @classmethod
    def create(cls, width: int, height: int) -> "PongState":
        speed = max(width, height) * 0.72
        return cls(
            width=width,
            height=height,
            player_y=(height - max(10, height // 5)) / 2,
            ai_y=(height - max(10, height // 5)) / 2,
            ball_x=width / 2,
            ball_y=height / 2,
            ball_vx=speed,
            ball_vy=speed * 0.42,
        )

    def reset_ball(self, direction: int) -> None:
        speed = max(self.width, self.height) * 0.72
        self.ball_x = self.width / 2
        self.ball_y = self.height / 2
        self.ball_vx = speed * direction
        self.ball_vy = speed * (0.35 if (self.player_score + self.ai_score) % 2 == 0 else -0.35)

    def update(self, dt: float, player_axis: int) -> None:
        paddle_speed = self.height * 1.25
        self.player_y += player_axis * paddle_speed * dt
        self.player_y = max(1, min(self.height - self.paddle_h - 1, self.player_y))

        target = self.ball_y - self.paddle_h / 2
        ai_speed = self.height * 0.82
        if self.ai_y < target:
            self.ai_y = min(target, self.ai_y + ai_speed * dt)
        elif self.ai_y > target:
            self.ai_y = max(target, self.ai_y - ai_speed * dt)
        self.ai_y = max(1, min(self.height - self.paddle_h - 1, self.ai_y))

        self.ball_x += self.ball_vx * dt
        self.ball_y += self.ball_vy * dt

        if self.ball_y <= 1:
            self.ball_y = 1
            self.ball_vy = abs(self.ball_vy)
        elif self.ball_y + self.ball_size >= self.height - 1:
            self.ball_y = self.height - self.ball_size - 1
            self.ball_vy = -abs(self.ball_vy)

        left_x = 3
        right_x = self.width - self.paddle_w - 3
        if (
            self.ball_vx < 0
            and self.ball_x <= left_x + self.paddle_w
            and self.ball_x + self.ball_size >= left_x
            and self.player_y <= self.ball_y + self.ball_size
            and self.ball_y <= self.player_y + self.paddle_h
        ):
            self.ball_x = left_x + self.paddle_w + 1
            self._bounce_from_paddle(self.player_y)

        if (
            self.ball_vx > 0
            and self.ball_x + self.ball_size >= right_x
            and self.ball_x <= right_x + self.paddle_w
            and self.ai_y <= self.ball_y + self.ball_size
            and self.ball_y <= self.ai_y + self.paddle_h
        ):
            self.ball_x = right_x - self.ball_size - 1
            self._bounce_from_paddle(self.ai_y)

        if self.ball_x < -self.ball_size:
            self.ai_score += 1
            self.reset_ball(direction=1)
        elif self.ball_x > self.width:
            self.player_score += 1
            self.reset_ball(direction=-1)

    def _bounce_from_paddle(self, paddle_y: float) -> None:
        speed = min(max(self.width, self.height) * 1.35, abs(self.ball_vx) * 1.04 + 2.0)
        paddle_center = paddle_y + self.paddle_h / 2
        ball_center = self.ball_y + self.ball_size / 2
        normalized = max(-1.0, min(1.0, (ball_center - paddle_center) / (self.paddle_h / 2)))
        self.ball_vx = math.copysign(speed, -self.ball_vx)
        self.ball_vy = normalized * max(self.height * 0.9, speed * 0.9)


class PongRenderer:
    def __init__(self, width: int, height: int) -> None:
        self.fb = FrameBuffer(width, height)

    def render(self, state: PongState) -> bytes:
        self.fb.clear((0, 0, 0))
        self._draw_center_line()
        self.fb.draw_border((0, 25, 45))
        self.fb.fill_rect(3, int(state.player_y), state.paddle_w, state.paddle_h, (0, 210, 255))
        self.fb.fill_rect(
            state.width - state.paddle_w - 3,
            int(state.ai_y),
            state.paddle_w,
            state.paddle_h,
            (255, 190, 0),
        )
        self.fb.fill_rect(int(state.ball_x), int(state.ball_y), state.ball_size, state.ball_size, (255, 255, 255))
        self._draw_score_ticks(state.player_score, 2, (0, 180, 255))
        self._draw_score_ticks(state.ai_score, state.width - 3, (255, 190, 0))
        return self.fb.copy_bytes()

    def _draw_center_line(self) -> None:
        x = self.fb.width // 2
        for y in range(2, self.fb.height - 2, 6):
            self.fb.fill_rect(x, y, 1, 3, (35, 35, 35))

    def _draw_score_ticks(self, score: int, x: int, color: Color) -> None:
        ticks = min(score % 10, max(0, self.fb.height // 5))
        for index in range(ticks):
            self.fb.fill_rect(x, 3 + index * 4, 1, 2, color)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Pong on a BRIC Light Wall tile.")
    parser.add_argument("--host", "--pi", dest="host", required=True, help="Tile receiver IP address")
    parser.add_argument("--port", type=int, default=4210)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="brcp")
    parser.add_argument("--fullscreen-preview", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        import pygame
    except ImportError:
        print("pygame is required for Pong preview. Install with: python3 -m pip install pygame", file=sys.stderr)
        return 2

    stop = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    pygame.init()
    flags = pygame.FULLSCREEN if args.fullscreen_preview else 0
    scale = max(4, min(12, 512 // max(args.width, args.height)))
    preview_size = (args.width * scale, args.height * scale)
    screen = pygame.display.set_mode(preview_size, flags)
    pygame.display.set_caption("BRIC Light Wall Pong")
    clock = pygame.time.Clock()

    state = PongState.create(args.width, args.height)
    renderer = PongRenderer(args.width, args.height)
    sender = ChunkedUDPSender(
        args.host,
        port=args.port,
        width=args.width,
        height=args.height,
        chunk_size=args.chunk_size,
        protocol=args.protocol,
    )

    print(
        f"Streaming Pong to {args.host}:{args.port} as {args.width}x{args.height} "
        f"{args.protocol.upper()} at {args.fps:g} FPS"
    )

    last_time = time.monotonic()
    try:
        while not stop:
            frame_start = time.monotonic()
            dt = min(0.05, frame_start - last_time)
            last_time = frame_start

            player_axis = 0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop = True
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    stop = True

            keys = pygame.key.get_pressed()
            if keys[pygame.K_UP]:
                player_axis -= 1
            if keys[pygame.K_DOWN]:
                player_axis += 1

            state.update(dt, player_axis)
            frame = renderer.render(state)

            try:
                sender.send_frame(frame)
            except OSError as error:
                print(f"send failed: {error}", file=sys.stderr)

            surface = pygame.image.frombuffer(frame, (args.width, args.height), "RGB")
            scaled = pygame.transform.scale(surface, screen.get_size())
            screen.blit(scaled, (0, 0))
            pygame.display.flip()

            pace_frame(frame_start, args.fps)
            clock.tick(max(1, int(args.fps * 2)))
    finally:
        sender.close()
        pygame.quit()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

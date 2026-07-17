#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import random
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.frame_mirror import DEFAULT_MIRROR_PORT, FrameMirror
from common.frame_sender import ChunkedUDPSender, pace_frame
from common.framebuffer import FrameBuffer
from common.web_input import DEFAULT_INPUT_PORT, WebHeldKeysInput, start_input_listener


Color = Tuple[int, int, int]
Rect = Tuple[int, int, int, int]


# 8x8 retro invader sprites, two frames each.
INVADER_SPRITES: List[List[List[str]]] = [
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

PLAYER_SPRITE: List[str] = [
    "00000100000",
    "00001110000",
    "00111111100",
    "01111111110",
    "11111111111",
    "11111111111",
]

SAUCER_SPRITE: List[str] = [
    "0001111111111000",
    "0011111111111100",
    "0110110110110110",
    "1111111111111111",
    "0011001111001100",
    "0001100000011000",
]

SHIELD_PATTERN: List[str] = [
    "00111111111100",
    "01111111111110",
    "11111111111111",
    "11111111111111",
    "11111000011111",
    "11110000001111",
    "11110000001111",
    "11100000000111",
]

INVADER_PALETTE: List[Color] = [
    (80, 230, 110),
    (80, 210, 240),
    (230, 110, 240),
    (255, 210, 80),
    (210, 140, 255),
]

FONT_3X5: Dict[str, Tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "A": ("010", "101", "111", "101", "101"),
    "B": ("110", "101", "110", "101", "110"),
    "C": ("011", "100", "100", "100", "011"),
    "D": ("110", "101", "101", "101", "110"),
    "E": ("111", "100", "110", "100", "111"),
    "F": ("111", "100", "110", "100", "100"),
    "G": ("011", "100", "101", "101", "011"),
    "H": ("101", "101", "111", "101", "101"),
    "I": ("111", "010", "010", "010", "111"),
    "J": ("001", "001", "001", "101", "111"),
    "K": ("101", "101", "110", "101", "101"),
    "L": ("100", "100", "100", "100", "111"),
    "M": ("10001", "11011", "10101", "10001", "10001"),
    "N": ("101", "111", "111", "111", "101"),
    "O": ("111", "101", "101", "101", "111"),
    "P": ("110", "101", "110", "100", "100"),
    "Q": ("111", "101", "101", "111", "001"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("111", "100", "111", "001", "111"),
    "T": ("111", "010", "010", "010", "010"),
    "U": ("101", "101", "101", "101", "111"),
    "V": ("101", "101", "101", "101", "010"),
    "W": ("10001", "10001", "10101", "11011", "10001"),
    "X": ("101", "101", "010", "101", "101"),
    "Y": ("101", "101", "010", "010", "010"),
    "Z": ("111", "001", "010", "100", "111"),
    "_": ("000", "000", "000", "000", "111"),
}


def sprite_size(sprite: List[str]) -> Tuple[int, int]:
    return (len(sprite[0]) if sprite else 0, len(sprite))


def draw_sprite(fb: FrameBuffer, x: int, y: int, sprite: List[str], color: Color) -> None:
    for ry, row in enumerate(sprite):
        for rx, enabled in enumerate(row):
            if enabled == "1":
                fb.set_pixel(x + rx, y + ry, color)


def measure_text(text: str, scale: int = 1, spacing: int = 1) -> Tuple[int, int]:
    width = 0
    height = 0
    visible = False
    for char in text.upper():
        if char == " ":
            width += 3 * scale + spacing
            continue
        glyph = FONT_3X5.get(char)
        if not glyph:
            width += 3 * scale + spacing
            continue
        visible = True
        width += len(glyph[0]) * scale + spacing
        height = max(height, len(glyph) * scale)
    if visible and width:
        width -= spacing
    return width, height


def draw_text(
    fb: FrameBuffer,
    text: str,
    x: int,
    y: int,
    color: Color,
    scale: int = 1,
    spacing: int = 1,
) -> None:
    cursor_x = x
    for char in text.upper():
        if char == " ":
            cursor_x += 3 * scale + spacing
            continue
        glyph = FONT_3X5.get(char)
        if not glyph:
            cursor_x += 3 * scale + spacing
            continue
        for gy, row in enumerate(glyph):
            for gx, enabled in enumerate(row):
                if enabled == "1":
                    fb.fill_rect(cursor_x + gx * scale, y + gy * scale, scale, scale, color)
        cursor_x += len(glyph[0]) * scale + spacing


def draw_centered_text(
    fb: FrameBuffer,
    text: str,
    center_y: int,
    color: Color,
    scale: int = 1,
    spacing: Optional[int] = None,
) -> None:
    if spacing is None:
        spacing = scale
    text_w, text_h = measure_text(text, scale, spacing)
    x = max(0, (fb.width - text_w) // 2)
    y = max(0, center_y - text_h // 2)
    fb.fill_rect(max(0, x - 3), max(0, y - 2), min(fb.width, text_w + 6), text_h + 4, (0, 0, 0))
    draw_text(fb, text, x, y, color, scale, spacing)


def rects_overlap(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


@dataclass
class Shot:
    x: float
    y: float
    vy: float
    color: Color
    width: int = 1
    height: int = 4

    def rect(self) -> Rect:
        return (int(round(self.x)), int(round(self.y)), self.width, self.height)


@dataclass
class Invader:
    col: int
    row: int
    alive: bool = True


@dataclass
class Explosion:
    x: float
    y: float
    color: Color
    ttl: float = 0.28
    duration: float = 0.28
    size: int = 5


@dataclass
class ScoreEntry:
    name: str
    score: int
    level: int


class HighScoreTable:
    def __init__(self, path: Optional[Path], limit: int = 5) -> None:
        self.path = path
        self.limit = limit
        self.entries = self._load()

    def qualifies(self, score: int) -> bool:
        if score <= 0:
            return False
        if len(self.entries) < self.limit:
            return True
        return score > min(entry.score for entry in self.entries)

    def add(self, name: str, score: int, level: int) -> None:
        clean_name = self._clean_name(name) or "PLAYER"
        self.entries.append(ScoreEntry(clean_name, int(score), int(level)))
        self.entries.sort(key=lambda entry: (entry.score, entry.level), reverse=True)
        self.entries = self.entries[: self.limit]
        self._save()

    def _load(self) -> List[ScoreEntry]:
        if self.path is None or not self.path.exists():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as error:
            print(f"failed to load highscores {self.path}: {error}", file=sys.stderr)
            return []

        items = raw.get("scores", raw) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return []

        entries: List[ScoreEntry] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = self._clean_name(str(item.get("name", ""))) or "PLAYER"
            try:
                score = int(item.get("score", 0))
                level = int(item.get("level", 1))
            except (TypeError, ValueError):
                continue
            if score > 0:
                entries.append(ScoreEntry(name, score, max(1, level)))
        entries.sort(key=lambda entry: (entry.score, entry.level), reverse=True)
        return entries[: self.limit]

    def _save(self) -> None:
        if self.path is None:
            return
        payload = {
            "scores": [
                {"name": entry.name, "score": entry.score, "level": entry.level}
                for entry in self.entries
            ]
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        except Exception as error:
            print(f"failed to save highscores {self.path}: {error}", file=sys.stderr)

    @staticmethod
    def _clean_name(name: str) -> str:
        return "".join(char for char in name.upper() if char.isascii() and char.isalnum())[:8]


@dataclass
class Shield:
    x: int
    y: int
    mask: List[List[bool]]

    @property
    def width(self) -> int:
        return len(self.mask[0]) if self.mask else 0

    @property
    def height(self) -> int:
        return len(self.mask)

    @classmethod
    def create(cls, x: int, y: int) -> "Shield":
        return cls(x, y, [[char == "1" for char in row] for row in SHIELD_PATTERN])

    def hit_point(self, rect: Rect) -> Optional[Tuple[int, int]]:
        rx, ry, rw, rh = rect
        for py in range(max(ry, self.y), min(ry + rh, self.y + self.height)):
            row = self.mask[py - self.y]
            for px in range(max(rx, self.x), min(rx + rw, self.x + self.width)):
                if row[px - self.x]:
                    return px, py
        return None

    def erode(self, cx: int, cy: int, radius: int = 2) -> None:
        local_x = cx - self.x
        local_y = cy - self.y
        radius_sq = radius * radius
        for yy in range(max(0, local_y - radius), min(self.height, local_y + radius + 1)):
            for xx in range(max(0, local_x - radius), min(self.width, local_x + radius + 1)):
                dx = xx - local_x
                dy = yy - local_y
                if dx * dx + dy * dy <= radius_sq:
                    self.mask[yy][xx] = False


@dataclass
class InputState:
    horizontal: int = 0
    fire: bool = False
    start: bool = False
    pause_pressed: bool = False
    restart_pressed: bool = False
    submit_name: bool = False
    backspace: bool = False
    typed_chars: List[str] = field(default_factory=list)


@dataclass
class WallConfig:
    tiles: List[Dict]
    cols: int
    rows: int
    origin: str = "top-left"


@dataclass
class LevelSettings:
    cols: int
    rows: int
    step_interval: float
    horizontal_step: int
    descend_step: int
    bomb_interval: float
    bomb_speed: float
    max_bombs: int
    saucer_min: float
    saucer_max: float
    random_dip_chance: float


class SpaceInvadersGame:
    def __init__(
        self,
        width: int,
        height: int,
        lives: int = 3,
        speed: float = 1.0,
        seed: Optional[int] = None,
        high_scores: Optional[HighScoreTable] = None,
    ) -> None:
        self.width = width
        self.height = height
        self.base_lives = max(1, lives)
        self.speed = max(0.25, speed)
        self.rng = random.Random(seed)
        self.high_scores = high_scores or HighScoreTable(None)
        self.player_w, self.player_h = sprite_size(PLAYER_SPRITE)
        self.invader_w, self.invader_h = sprite_size(INVADER_SPRITES[0][0])
        self.saucer_w, self.saucer_h = sprite_size(SAUCER_SPRITE)
        self.score = 0
        self.level = 1
        self.lives = self.base_lives
        self.status = "ready"
        self.player_x = 0.0
        self.player_cooldown = 0.0
        self.player_shot: Optional[Shot] = None
        self.invader_shots: List[Shot] = []
        self.invaders: List[Invader] = []
        self.shields: List[Shield] = []
        self.explosions: List[Explosion] = []
        self.formation_x = 0.0
        self.formation_y = 0.0
        self.formation_dir = 1
        self.step_timer = 0.0
        self.leg_toggle = False
        self.bomb_timer = 0.8
        self.saucer_x: Optional[float] = None
        self.saucer_dir = 1
        self.saucer_timer = 8.0
        self.total_invaders = 1
        self.pending_name = ""
        self.level_settings = LevelSettings(4, 2, 0.7, 1, 1, 1.8, 32.0, 1, 9.0, 16.0, 0.0)
        self.reset_game()

    @property
    def hud_h(self) -> int:
        return 8 if self.height >= 48 else 0

    @property
    def player_y(self) -> int:
        return max(0, self.height - self.player_h - 2)

    @property
    def invader_spacing_x(self) -> int:
        return max(2, min(4, self.width // 40))

    @property
    def invader_spacing_y(self) -> int:
        return max(3, min(6, self.height // 24))

    def reset_game(self) -> None:
        self.score = 0
        self.level = 1
        self.lives = self.base_lives
        self.status = "ready"
        self.pending_name = ""
        self.explosions = []
        self._setup_level()

    def _setup_level(self) -> None:
        self.player_x = (self.width - self.player_w) / 2
        self.player_cooldown = 0.0
        self.player_shot = None
        self.invader_shots = []
        self.saucer_x = None
        self.formation_dir = self.rng.choice((-1, 1))
        self.step_timer = 0.0
        self.leg_toggle = False

        shield_y = self._shield_y()
        start_y = max(9, self.hud_h + self.saucer_h + 3)
        spacing_x = self.invader_spacing_x
        spacing_y = self.invader_spacing_y

        max_cols = max(3, (self.width - 2 + spacing_x) // (self.invader_w + spacing_x))
        available_h = max(self.invader_h, shield_y - start_y - 3)
        max_rows = max(2, (available_h + spacing_y) // (self.invader_h + spacing_y))
        self.level_settings = self._build_level_settings(max_cols, max_rows)
        self.saucer_timer = self.rng.uniform(
            self.level_settings.saucer_min,
            self.level_settings.saucer_max,
        )
        self.bomb_timer = self.rng.uniform(
            self.level_settings.bomb_interval * 0.8,
            self.level_settings.bomb_interval * 1.4,
        )

        cols = self.level_settings.cols
        rows = self.level_settings.rows
        formation_w = cols * self.invader_w + (cols - 1) * spacing_x
        max_start_x = max(0, self.width - formation_w - 1)
        centered_x = max(0, (self.width - formation_w) // 2)
        random_offset = self.rng.randint(-3, 3) if self.level > 1 else 0
        self.formation_x = float(max(0, min(max_start_x, centered_x + random_offset)))
        self.formation_y = float(start_y + self.rng.randint(0, min(3, max(0, shield_y - start_y - rows * self.invader_h))))
        self.invaders = [Invader(col, row) for row in range(rows) for col in range(cols)]
        self.total_invaders = max(1, len(self.invaders))
        self.shields = self._make_shields(shield_y)
        self.status = "ready"

    def _build_level_settings(self, max_cols: int, max_rows: int) -> LevelSettings:
        count_tier = self.level // 2
        speed_tier = (self.level - 1) // 2

        base_cols = min(max_cols, 4)
        base_rows = min(max_rows, 2)
        cols = min(max_cols, base_cols + count_tier)
        rows = min(max_rows, base_rows + count_tier // 4)

        speed_factor = 1.0 + speed_tier * 0.32
        step_interval = max(0.09, (0.72 / speed_factor) * self.rng.uniform(0.94, 1.06))
        horizontal_step = max(1, self.width // 96) + min(3, speed_tier // 4)
        descend_step = max(1, self.height // 64) + min(4, speed_tier // 3)
        bomb_interval = max(0.34, (1.85 - speed_tier * 0.13) * self.rng.uniform(0.85, 1.2))
        bomb_speed = max(24.0, self.height * (0.24 + speed_tier * 0.026)) * self.rng.uniform(0.9, 1.12)
        max_bombs = min(4, 1 + speed_tier // 3 + (1 if self.width >= 128 and speed_tier >= 2 else 0))
        random_dip_chance = min(0.14, max(0, self.level - 2) * 0.015)
        saucer_min = max(4.5, 10.0 - speed_tier * 0.45)
        saucer_max = max(saucer_min + 2.0, 17.0 - speed_tier * 0.55)

        return LevelSettings(
            cols=cols,
            rows=rows,
            step_interval=step_interval,
            horizontal_step=horizontal_step,
            descend_step=descend_step,
            bomb_interval=bomb_interval,
            bomb_speed=bomb_speed,
            max_bombs=max_bombs,
            saucer_min=saucer_min,
            saucer_max=saucer_max,
            random_dip_chance=random_dip_chance,
        )

    def _shield_y(self) -> int:
        shield_h = len(SHIELD_PATTERN)
        return max(self.hud_h + 18, self.height - self.player_h - shield_h - max(8, self.height // 12))

    def _make_shields(self, shield_y: int) -> List[Shield]:
        shield_w = len(SHIELD_PATTERN[0])
        count = max(2, min(4, self.width // 20))
        total_w = count * shield_w
        gap = max(3, (self.width - total_w) // (count + 1))
        shields = []
        x = gap
        for _ in range(count):
            shields.append(Shield.create(x, shield_y))
            x += shield_w + gap
        return shields

    def update(self, dt: float, controls: InputState) -> None:
        raw_dt = min(0.06, dt)
        game_dt = raw_dt * self.speed
        self._update_explosions(raw_dt)

        if controls.restart_pressed:
            self.reset_game()
            return

        if controls.pause_pressed and self.status in ("playing", "paused"):
            self.status = "paused" if self.status == "playing" else "playing"
            return

        if self.status == "name_entry":
            self._update_name_entry(controls)
            return

        if self.status == "high_scores":
            if controls.start:
                self.reset_game()
                self.status = "playing"
            return

        if self.status == "game_over":
            if controls.start:
                self.reset_game()
                self.status = "playing"
            return

        if self.status == "ready":
            self._move_player(raw_dt, controls.horizontal)
            if not (controls.start or controls.fire):
                return
            self.status = "playing"

        if self.status != "playing":
            return

        self._move_player(raw_dt, controls.horizontal)
        self.player_cooldown = max(0.0, self.player_cooldown - raw_dt)
        if controls.fire:
            self._fire_player_shot()

        self._update_player_shot(game_dt)
        self._update_invader_shots(game_dt)
        self._update_saucer(game_dt)
        self._step_invaders(game_dt)
        self._spawn_invader_shot(game_dt)
        self._handle_collisions()
        self._check_overrun()

    def _update_name_entry(self, controls: InputState) -> None:
        if controls.backspace:
            self.pending_name = self.pending_name[:-1]
        for char in controls.typed_chars:
            if len(self.pending_name) >= 8:
                break
            if char.isascii() and char.isalnum():
                self.pending_name += char.upper()
        if controls.submit_name:
            self.high_scores.add(self.pending_name or "PLAYER", self.score, self.level)
            self.pending_name = ""
            self.status = "high_scores"

    def _move_player(self, dt: float, axis: int) -> None:
        speed = max(50.0, self.width * 0.9)
        self.player_x += axis * speed * dt
        self.player_x = max(1.0, min(self.width - self.player_w - 1.0, self.player_x))

    def _fire_player_shot(self) -> None:
        if self.player_shot is not None or self.player_cooldown > 0.0:
            return
        shot_speed = -max(70.0, self.height * 1.15)
        self.player_shot = Shot(
            self.player_x + self.player_w / 2,
            self.player_y - 4,
            shot_speed,
            (255, 255, 255),
            width=1,
            height=4,
        )
        self.player_cooldown = 0.22

    def _update_player_shot(self, dt: float) -> None:
        if self.player_shot is None:
            return
        self.player_shot.y += self.player_shot.vy * dt
        if self.player_shot.y + self.player_shot.height < 0:
            self.player_shot = None

    def _update_invader_shots(self, dt: float) -> None:
        live_shots = []
        for shot in self.invader_shots:
            shot.y += shot.vy * dt
            if shot.y < self.height:
                live_shots.append(shot)
        self.invader_shots = live_shots

    def _update_saucer(self, dt: float) -> None:
        if self.width < self.saucer_w + 8:
            return
        if self.saucer_x is None:
            self.saucer_timer -= dt
            if self.saucer_timer <= 0.0:
                self.saucer_dir = self.rng.choice((-1, 1))
                self.saucer_x = -self.saucer_w if self.saucer_dir > 0 else self.width
            return

        saucer_speed = max(28.0, self.width * 0.28)
        self.saucer_x += self.saucer_dir * saucer_speed * dt
        if self.saucer_x > self.width + self.saucer_w or self.saucer_x < -self.saucer_w * 2:
            self.saucer_x = None
            self.saucer_timer = self.rng.uniform(
                self.level_settings.saucer_min,
                self.level_settings.saucer_max,
            )

    def _step_invaders(self, dt: float) -> None:
        if not self._alive_invaders():
            return
        self.step_timer += dt
        interval = self._step_interval()
        if self.step_timer < interval:
            return
        self.step_timer -= interval

        min_x, max_x, _min_y, _max_y = self._invader_bounds_local()
        step = self.level_settings.horizontal_step
        if self.level > 2 and self.rng.random() < 0.08:
            step += 1
        proposed_x = self.formation_x + self.formation_dir * step
        if proposed_x + min_x <= 1 or proposed_x + max_x >= self.width - 1:
            self.formation_dir *= -1
            self.formation_y += self.level_settings.descend_step
        else:
            self.formation_x = proposed_x
            if self.rng.random() < self.level_settings.random_dip_chance:
                self.formation_y += 1
        self.leg_toggle = not self.leg_toggle

    def _step_interval(self) -> float:
        alive = max(1, len(self._alive_invaders()))
        alive_ratio = alive / self.total_invaders
        return self.level_settings.step_interval * (0.38 + 0.62 * alive_ratio)

    def _spawn_invader_shot(self, dt: float) -> None:
        if len(self.invader_shots) >= self.level_settings.max_bombs:
            return
        self.bomb_timer -= dt
        if self.bomb_timer > 0.0:
            return

        shooters = self._bottom_invaders()
        if shooters:
            shooter = self.rng.choice(shooters)
            sx, sy, sw, sh = self._invader_rect(shooter)
            self.invader_shots.append(
                Shot(
                    sx + sw / 2,
                    sy + sh,
                    self.level_settings.bomb_speed,
                    (255, 90, 70),
                    width=1,
                    height=4,
                )
            )

        alive_ratio = len(self._alive_invaders()) / self.total_invaders
        base = self.level_settings.bomb_interval
        self.bomb_timer = self.rng.uniform(base * 0.55, base * 1.35) * max(0.45, alive_ratio)

    def _handle_collisions(self) -> None:
        self._collide_player_shot_with_shields()
        self._collide_invader_shots_with_shields()
        self._collide_player_shot_with_saucer()
        self._collide_player_shot_with_invaders()
        self._collide_invader_shots_with_player()
        self._collide_invaders_with_shields()

    def _collide_player_shot_with_shields(self) -> None:
        if self.player_shot is None:
            return
        rect = self.player_shot.rect()
        for shield in self.shields:
            point = shield.hit_point(rect)
            if point is None:
                continue
            shield.erode(point[0], point[1], radius=2)
            self.player_shot = None
            return

    def _collide_invader_shots_with_shields(self) -> None:
        live_shots = []
        for shot in self.invader_shots:
            hit = False
            rect = shot.rect()
            for shield in self.shields:
                point = shield.hit_point(rect)
                if point is None:
                    continue
                shield.erode(point[0], point[1], radius=2)
                hit = True
                break
            if not hit:
                live_shots.append(shot)
        self.invader_shots = live_shots

    def _collide_player_shot_with_saucer(self) -> None:
        if self.player_shot is None or self.saucer_x is None:
            return
        if rects_overlap(self.player_shot.rect(), self._saucer_rect()):
            self.score += self.rng.choice((50, 100, 150, 300))
            sx, sy, sw, sh = self._saucer_rect()
            self.explosions.append(Explosion(sx + sw / 2, sy + sh / 2, (255, 80, 80), size=6))
            self.player_shot = None
            self.saucer_x = None
            self.saucer_timer = self.rng.uniform(
                self.level_settings.saucer_min,
                self.level_settings.saucer_max,
            )

    def _collide_player_shot_with_invaders(self) -> None:
        if self.player_shot is None:
            return
        shot_rect = self.player_shot.rect()
        for invader in self._alive_invaders():
            if not rects_overlap(shot_rect, self._invader_rect(invader)):
                continue
            invader.alive = False
            points = (len({inv.row for inv in self.invaders}) - invader.row) * 10
            self.score += points
            ix, iy, iw, ih = self._invader_rect(invader)
            self.explosions.append(Explosion(ix + iw / 2, iy + ih / 2, INVADER_PALETTE[invader.row % len(INVADER_PALETTE)]))
            self.player_shot = None
            if not self._alive_invaders():
                self.score += self.lives * 100
                self.level += 1
                self._setup_level()
            return

    def _collide_invader_shots_with_player(self) -> None:
        player_rect = self._player_rect()
        for index, shot in enumerate(self.invader_shots):
            if not rects_overlap(shot.rect(), player_rect):
                continue
            del self.invader_shots[index]
            self._lose_life()
            return

    def _collide_invaders_with_shields(self) -> None:
        for invader in self._alive_invaders():
            rect = self._invader_rect(invader)
            for shield in self.shields:
                point = shield.hit_point(rect)
                if point is not None:
                    shield.erode(point[0], point[1], radius=3)

    def _check_overrun(self) -> None:
        if not self._alive_invaders():
            return
        _min_x, _max_x, _min_y, max_y = self._invader_bounds_world()
        if max_y >= self.player_y:
            self.explosions.append(Explosion(self.player_x + self.player_w / 2, self.player_y + self.player_h / 2, (255, 60, 60), size=7))
            self._finish_game()

    def _lose_life(self) -> None:
        self.lives -= 1
        self.explosions.append(Explosion(self.player_x + self.player_w / 2, self.player_y + self.player_h / 2, (255, 60, 60), size=7))
        self.invader_shots = []
        self.player_shot = None
        self.player_x = (self.width - self.player_w) / 2
        self.player_cooldown = 0.5
        if self.lives <= 0:
            self._finish_game()
        else:
            self.status = "ready"

    def _finish_game(self) -> None:
        self.lives = 0
        self.player_shot = None
        self.invader_shots = []
        self.saucer_x = None
        self.pending_name = ""
        self.status = "name_entry" if self.high_scores.qualifies(self.score) else "high_scores"

    def _update_explosions(self, dt: float) -> None:
        for explosion in self.explosions:
            explosion.ttl -= dt
        self.explosions = [explosion for explosion in self.explosions if explosion.ttl > 0.0]

    def _alive_invaders(self) -> List[Invader]:
        return [invader for invader in self.invaders if invader.alive]

    def _bottom_invaders(self) -> List[Invader]:
        by_col: Dict[int, Invader] = {}
        for invader in self._alive_invaders():
            current = by_col.get(invader.col)
            if current is None or invader.row > current.row:
                by_col[invader.col] = invader
        return list(by_col.values())

    def _invader_rect(self, invader: Invader) -> Rect:
        x = self.formation_x + invader.col * (self.invader_w + self.invader_spacing_x)
        y = self.formation_y + invader.row * (self.invader_h + self.invader_spacing_y)
        return (int(round(x)), int(round(y)), self.invader_w, self.invader_h)

    def _player_rect(self) -> Rect:
        return (int(round(self.player_x)), self.player_y, self.player_w, self.player_h)

    def _saucer_rect(self) -> Rect:
        saucer_x = self.saucer_x if self.saucer_x is not None else -self.saucer_w
        return (int(round(saucer_x)), self.hud_h + 1, self.saucer_w, self.saucer_h)

    def _invader_bounds_local(self) -> Rect:
        alive = self._alive_invaders()
        if not alive:
            return (0, 0, 0, 0)
        xs = [inv.col * (self.invader_w + self.invader_spacing_x) for inv in alive]
        ys = [inv.row * (self.invader_h + self.invader_spacing_y) for inv in alive]
        return (min(xs), max(xs) + self.invader_w, min(ys), max(ys) + self.invader_h)

    def _invader_bounds_world(self) -> Rect:
        min_x, max_x, min_y, max_y = self._invader_bounds_local()
        return (
            int(round(self.formation_x + min_x)),
            int(round(self.formation_x + max_x)),
            int(round(self.formation_y + min_y)),
            int(round(self.formation_y + max_y)),
        )


class SpaceInvadersRenderer:
    def __init__(self, width: int, height: int, seed: int = 42) -> None:
        self.fb = FrameBuffer(width, height)
        rnd = random.Random(seed)
        star_count = max(12, width * height // 700)
        self.stars = [(rnd.randrange(width), rnd.randrange(height), rnd.random() * math.pi * 2) for _ in range(star_count)]
        self.phase = 0.0

    def render(self, game: SpaceInvadersGame, dt: float) -> bytes:
        self.phase += dt
        self.fb.clear((1, 2, 8))
        self._draw_stars()
        self._draw_hud(game)
        self._draw_saucer(game)
        self._draw_invaders(game)
        self._draw_shields(game)
        self._draw_shots(game)
        self._draw_player(game)
        self._draw_explosions(game)
        self._draw_overlay(game)
        return self.fb.copy_bytes()

    def _draw_stars(self) -> None:
        for sx, sy, phase in self.stars:
            if sy < 8:
                continue
            brightness = int(65 + 60 * (0.5 + 0.5 * math.sin(self.phase * 1.5 + phase)))
            self.fb.set_pixel(sx, sy, (brightness, brightness, brightness))

    def _draw_hud(self, game: SpaceInvadersGame) -> None:
        if game.hud_h <= 0:
            return
        self.fb.draw_line_h(0, game.hud_h - 1, self.fb.width, (12, 26, 36))
        draw_text(self.fb, f"{game.score:04d}"[-6:], 2, 1, (110, 235, 120), scale=1, spacing=1)
        draw_text(self.fb, f"L{game.level}", max(2, self.fb.width // 2 - 5), 1, (255, 210, 80), scale=1, spacing=1)
        for index in range(game.lives):
            x = self.fb.width - 5 - index * 5
            self.fb.fill_rect(x, 2, 3, 3, (80, 210, 255))

    def _draw_saucer(self, game: SpaceInvadersGame) -> None:
        if game.saucer_x is None:
            return
        sx, sy, _sw, _sh = game._saucer_rect()
        draw_sprite(self.fb, sx, sy, SAUCER_SPRITE, (255, 80, 80))

    def _draw_invaders(self, game: SpaceInvadersGame) -> None:
        frame = 1 if game.leg_toggle else 0
        for invader in game._alive_invaders():
            ix, iy, _iw, _ih = game._invader_rect(invader)
            sprite_index = (invader.row + invader.col + game.level) % len(INVADER_SPRITES)
            color = INVADER_PALETTE[invader.row % len(INVADER_PALETTE)]
            draw_sprite(self.fb, ix, iy, INVADER_SPRITES[sprite_index][frame], color)

    def _draw_shields(self, game: SpaceInvadersGame) -> None:
        for shield in game.shields:
            for yy, row in enumerate(shield.mask):
                for xx, enabled in enumerate(row):
                    if enabled:
                        self.fb.set_pixel(shield.x + xx, shield.y + yy, (60, 185, 95))

    def _draw_shots(self, game: SpaceInvadersGame) -> None:
        if game.player_shot is not None:
            x, y, w, h = game.player_shot.rect()
            self.fb.fill_rect(x, y, w, h, game.player_shot.color)
        for shot in game.invader_shots:
            x, y, w, h = shot.rect()
            self.fb.fill_rect(x, y, w, h, shot.color)
            self.fb.set_pixel(x - 1, y + 1, (255, 160, 70))
            self.fb.set_pixel(x + 1, y + 2, (255, 160, 70))

    def _draw_player(self, game: SpaceInvadersGame) -> None:
        color = (80, 210, 255) if game.lives > 0 else (70, 70, 90)
        draw_sprite(self.fb, int(round(game.player_x)), game.player_y, PLAYER_SPRITE, color)

    def _draw_explosions(self, game: SpaceInvadersGame) -> None:
        for explosion in game.explosions:
            progress = max(0.0, min(1.0, explosion.ttl / explosion.duration))
            radius = max(1, int(round(explosion.size * progress)))
            cx = int(round(explosion.x))
            cy = int(round(explosion.y))
            color = explosion.color
            self.fb.set_pixel(cx, cy, (255, 255, 255))
            for delta in range(1, radius + 1):
                self.fb.set_pixel(cx - delta, cy, color)
                self.fb.set_pixel(cx + delta, cy, color)
                self.fb.set_pixel(cx, cy - delta, color)
                self.fb.set_pixel(cx, cy + delta, color)
            if radius > 2:
                self.fb.set_pixel(cx - radius + 1, cy - radius + 1, color)
                self.fb.set_pixel(cx + radius - 1, cy - radius + 1, color)
                self.fb.set_pixel(cx - radius + 1, cy + radius - 1, color)
                self.fb.set_pixel(cx + radius - 1, cy + radius - 1, color)

    def _draw_overlay(self, game: SpaceInvadersGame) -> None:
        scale = 2 if self.fb.width >= 96 else 1
        if game.status == "ready":
            draw_centered_text(self.fb, "SPACE", self.fb.height // 2, (255, 255, 255), scale=scale)
        elif game.status == "paused":
            draw_centered_text(self.fb, "PAUSED", self.fb.height // 2, (255, 210, 80), scale=scale)
        elif game.status == "name_entry":
            self._draw_name_entry(game)
        elif game.status == "high_scores":
            self._draw_high_scores(game)
        elif game.status == "game_over":
            draw_centered_text(self.fb, "GAME OVER", self.fb.height // 2 - 5, (255, 80, 80), scale=scale)
            draw_centered_text(self.fb, "SPACE", self.fb.height // 2 + 12, (255, 255, 255), scale=1)

    def _draw_panel(self, game: SpaceInvadersGame) -> Tuple[int, int, int, int]:
        margin = 4 if self.fb.width >= 96 else 2
        top = max(game.hud_h + 3, self.fb.height // 2 - 36)
        bottom = self.fb.height - 5
        height = max(26, bottom - top)
        self.fb.fill_rect(margin, top, self.fb.width - margin * 2, height, (0, 0, 0))
        self.fb.draw_line_h(margin, top, self.fb.width - margin * 2, (35, 70, 95))
        self.fb.draw_line_h(margin, top + height - 1, self.fb.width - margin * 2, (35, 70, 95))
        return margin, top, self.fb.width - margin * 2, height

    def _draw_name_entry(self, game: SpaceInvadersGame) -> None:
        _x, y, _w, h = self._draw_panel(game)
        blink = "_" if int(self.phase * 3) % 2 == 0 and len(game.pending_name) < 8 else ""
        name = game.pending_name + blink
        if not name:
            name = "_"

        draw_centered_text(self.fb, "NEW HIGH", y + 8, (255, 210, 80), scale=1)
        draw_centered_text(self.fb, str(game.score), y + 19, (110, 235, 120), scale=1)
        draw_centered_text(self.fb, "NAME", y + 31, (80, 210, 255), scale=1)
        draw_centered_text(self.fb, name, y + 42, (255, 255, 255), scale=1)
        if h >= 58:
            draw_centered_text(self.fb, "ENTER", y + 55, (160, 160, 160), scale=1)

    def _draw_high_scores(self, game: SpaceInvadersGame) -> None:
        _x, y, _w, h = self._draw_panel(game)
        draw_centered_text(self.fb, "HIGH SCORES", y + 8, (255, 210, 80), scale=1)

        line_y = y + 18
        line_gap = 8
        available_rows = max(1, (h - 30) // line_gap)
        entries = game.high_scores.entries[:available_rows]
        if not entries:
            draw_centered_text(self.fb, "NO SCORES", line_y + 8, (160, 160, 160), scale=1)
        else:
            max_name_chars = 4 if self.fb.width < 96 else 8
            for index, entry in enumerate(entries):
                score_text = str(entry.score)
                if len(score_text) > 6:
                    score_text = score_text[-6:]
                line = f"{index + 1} {entry.name[:max_name_chars]} {score_text}"
                text_w, _text_h = measure_text(line, 1, 1)
                draw_text(
                    self.fb,
                    line,
                    max(1, (self.fb.width - text_w) // 2),
                    line_y + index * line_gap,
                    (255, 255, 255) if index == 0 else (120, 210, 255),
                    scale=1,
                    spacing=1,
                )

        if h >= 58:
            draw_centered_text(self.fb, "SPACE", y + h - 8, (160, 160, 160), scale=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play Space Invaders on a BRIC Light Wall.")
    parser.add_argument("--layout", default="wall_layout.json", help="Path to wall_layout.json")
    parser.add_argument("--host", "--pi", dest="host", help="Fallback single tile IP if layout missing")
    parser.add_argument("--port", type=int, default=4210, help="Fallback tile UDP port")
    parser.add_argument("--width", type=int, default=64, help="Tile width")
    parser.add_argument("--height", type=int, default=64, help="Tile height")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--protocol", choices=("brcp", "bric", "both"), default="brcp")
    parser.add_argument("--speed", type=float, default=1.0, help="Game speed multiplier")
    parser.add_argument("--lives", type=int, default=3)
    parser.add_argument("--seed", type=int, help="Optional deterministic random seed")
    parser.add_argument(
        "--highscores",
        default=str(TOOLS_DIR / "invaders_highscores.json"),
        help="Path to persistent high-score JSON file",
    )
    parser.add_argument("--fullscreen-preview", action="store_true")
    parser.add_argument("--preview-scale", type=int, help="Pixel scale for the local preview window")
    parser.add_argument("--no-stream", action="store_true", help="Run the local preview without sending UDP frames")
    parser.add_argument("--web-input", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--input-port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--mirror-port", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--max-frames", type=int, default=0, help=argparse.SUPPRESS)
    return parser.parse_args()


def load_wall_config(args: argparse.Namespace) -> WallConfig:
    layout_path = Path(args.layout)
    tiles: List[Dict] = []
    cols = 1
    rows = 1
    origin = "top-left"

    if layout_path.exists():
        try:
            layout = json.loads(layout_path.read_text(encoding="utf-8"))
        except Exception as error:
            raise RuntimeError(f"failed to load layout {layout_path}: {error}") from error
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
            cols = max(tile["grid_x"] for tile in tiles) + 1
        if tiles and rows <= 0:
            rows = max(tile["grid_y"] for tile in tiles) + 1

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


def pygame_controls(pygame) -> Tuple[bool, InputState]:
    stop = False
    controls = InputState()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            stop = True
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                stop = True
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                controls.start = True
                controls.submit_name = True
            elif event.key == pygame.K_SPACE:
                controls.start = True
            elif event.key == pygame.K_BACKSPACE:
                controls.backspace = True
            elif event.key == pygame.K_p:
                controls.pause_pressed = True
            elif event.key == pygame.K_r:
                controls.restart_pressed = True
            typed_char = getattr(event, "unicode", "")
            if len(typed_char) == 1 and typed_char.isalnum():
                controls.typed_chars.append(typed_char.upper())

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        controls.horizontal -= 1
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        controls.horizontal += 1
    controls.fire = keys[pygame.K_SPACE] or keys[pygame.K_RETURN] or controls.start
    return stop, controls


def web_controls(web_input: WebHeldKeysInput) -> Tuple[bool, InputState]:
    """
    Web-input equivalent of pygame_controls(): same (stop, InputState)
    contract, sourced from WebHeldKeysInput instead of a real pygame
    window's event queue and key state.

    Held keys ("left", "right", "fire") map the same way arrow/WASD/space
    do in pygame_controls(). Discrete browser events (matching the shape
    produced by the Flask relay) map onto the same one-shot InputState
    fields that KEYDOWN events populate above: start, submit_name,
    backspace, pause_pressed, restart_pressed, typed_chars.
    """
    stop = False
    controls = InputState()

    for event in web_input.drain_events():
        event_type = event.get("type")
        if event_type == "quit":
            stop = True
        elif event_type == "start":
            controls.start = True
        elif event_type == "submit":
            controls.start = True
            controls.submit_name = True
        elif event_type == "backspace":
            controls.backspace = True
        elif event_type == "pause":
            controls.pause_pressed = True
        elif event_type == "restart":
            controls.restart_pressed = True
        elif event_type == "char":
            char = str(event.get("char", ""))
            if len(char) == 1 and char.isalnum():
                controls.typed_chars.append(char.upper())

    if web_input.is_pressed("left"):
        controls.horizontal -= 1
    if web_input.is_pressed("right"):
        controls.horizontal += 1
    controls.fire = web_input.is_pressed("fire") or controls.start
    return stop, controls


def _make_web_input_handler(web_input: WebHeldKeysInput):
    """
    Build the callback passed to start_input_listener().

    Held-key messages: {"type": "keydown"/"keyup", "key": "left"/"right"/"fire"}
    One-shot messages are forwarded to web_controls() as-is via push_event(),
    e.g. {"type": "start"}, {"type": "pause"}, {"type": "char", "char": "A"}.
    Malformed messages are ignored rather than raising, since a stale or
    malformed browser message must never take down the game loop.
    """
    HELD_KEYS = {"left", "right", "fire"}

    def handler(message: dict) -> None:
        msg_type = message.get("type")
        if msg_type in ("keydown", "keyup"):
            key = message.get("key")
            if key not in HELD_KEYS:
                return
            if msg_type == "keydown":
                web_input.press(key)
            else:
                web_input.release(key)
        else:
            web_input.push_event(message)

    return handler


def main() -> int:
    args = parse_args()
    try:
        import pygame
    except ImportError:
        print("pygame is required for Space Invaders. Install with: python3 -m pip install pygame", file=sys.stderr)
        return 2

    stop = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    try:
        config = load_wall_config(args)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2

    wall_w = config.cols * args.width
    wall_h = config.rows * args.height
    senders = {} if args.no_stream else make_senders(args, config.tiles)

    pygame.init()
    flags = pygame.FULLSCREEN if args.fullscreen_preview else 0
    if args.preview_scale:
        scale = max(1, args.preview_scale)
    else:
        scale = max(3, min(10, 768 // max(wall_w, wall_h)))
    screen = pygame.display.set_mode((wall_w * scale, wall_h * scale), flags)
    pygame.display.set_caption("BRIC Light Wall Space Invaders")
    clock = pygame.time.Clock()

    game = SpaceInvadersGame(
        wall_w,
        wall_h,
        lives=args.lives,
        speed=args.speed,
        seed=args.seed,
        high_scores=HighScoreTable(Path(args.highscores) if args.highscores else None),
    )
    renderer = SpaceInvadersRenderer(wall_w, wall_h, seed=args.seed or 42)

    target_list = ", ".join(f"{tile['ip']}:{tile.get('port', args.port)}" for tile in config.tiles)
    if args.no_stream:
        target_list = "preview only"
    print(
        f"Space Invaders {wall_w}x{wall_h} at {args.fps:g} FPS ({target_list})"
    )
    print("Controls: Left/Right or A/D move, Space/Return fire/start, P pause, R restart, Esc quit")
    print("High score names: type letters/numbers, Backspace edits, Return saves")
    print("Keep the preview window focused so the MacBook keyboard controls the game.")

    web_input = None
    if args.web_input:
        web_input = WebHeldKeysInput()
        input_port = args.input_port or DEFAULT_INPUT_PORT
        start_input_listener(_make_web_input_handler(web_input), port=input_port)

    mirror = FrameMirror(args.mirror_port) if args.mirror_port else None

    last_time = time.monotonic()
    frames = 0
    try:
        while not stop:
            frame_start = time.monotonic()
            dt = min(0.06, frame_start - last_time)
            last_time = frame_start

            if web_input is not None:
                # Still drain pygame's own event queue so QUIT/window-close
                # signals are honored even while browser input drives the
                # game; only the resulting InputState comes from the web.
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        stop = True
                _stop_ignored, controls = web_controls(web_input)
            else:
                event_stop, controls = pygame_controls(pygame)
                stop = stop or event_stop

            game.update(dt, controls)
            frame = renderer.render(game, dt)

            if senders:
                send_wall_frame(args, config, senders, frame, wall_w)
            if mirror is not None:
                mirror.send(frame)

            surface = pygame.image.frombuffer(frame, (wall_w, wall_h), "RGB")
            scaled = pygame.transform.scale(surface, screen.get_size())
            screen.blit(scaled, (0, 0))
            pygame.display.flip()

            frames += 1
            if args.max_frames and frames >= args.max_frames:
                stop = True

            pace_frame(frame_start, args.fps)
            clock.tick(max(1, int(args.fps * 2)))
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

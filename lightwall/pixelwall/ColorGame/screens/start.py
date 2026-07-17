# =============================================================================
# screens/start.py – Title / start screen
# =============================================================================

import math
import pygame
from config import BG, TEXT, MUTED, ACCENT, WIDTH, HEIGHT


class StartScreen:
    """
    Displays the game title and waits for any key or click to begin.

    enter(data)  →  resets animation timer
    update(dt, events)  →  transitions to 'target' on any input
    draw()  →  renders animated title screen
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        self._font_title = pygame.font.SysFont("arial", 90, bold=True)
        self._font_sub   = pygame.font.SysFont("arial", 30)
        self._font_hint  = pygame.font.SysFont("arial", 22)
        self._font_ctrl  = pygame.font.SysFont("arial", 19)

        self._t    = 0.0
        self._next = None

    # --- Screen interface ----------------------------------------------------

    def enter(self, data: dict) -> None:
        self._t    = 0.0
        self._next = None

    def update(self, dt: float, events: list) -> tuple:
        self._t += dt
        for e in events:
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self._next = "target"
        return ("target", {}) if self._next else (None, {})

    def draw(self) -> None:
        self.screen.fill(BG)
        W, H = WIDTH, HEIGHT
        t = self._t

        # ---- Animated title -------------------------------------------------
        pulse = (math.sin(t * 1.6) + 1.0) / 2.0          # 0 → 1
        r = int(110 + 80 * pulse)
        b = int(200 + 55 * (1.0 - pulse))
        title = self._font_title.render("COLOR MATCH", True, (r, 75, b))
        self.screen.blit(title, title.get_rect(center=(W // 2, H // 2 - 100)))

        # ---- Subtitle -------------------------------------------------------
        sub = self._font_sub.render(
            "Use the keyboard sliders to reproduce the target colour", True, MUTED)
        self.screen.blit(sub, sub.get_rect(center=(W // 2, H // 2 - 5)))

        # ---- Controls cheat-sheet -------------------------------------------
        controls = [
            ("Q / A", "Red +  / −"),
            ("W / S", "Green +  / −"),
            ("E / D", "Blue +  / −"),
            ("Shift", "4× speed"),
            ("Enter", "Submit match"),
        ]
        col_x  = W // 2 - 200
        row_y  = H // 2 + 40
        row_h  = 26
        key_col = (160, 160, 200)
        for key_str, desc_str in controls:
            ks = self._font_ctrl.render(key_str, True, key_col)
            ds = self._font_ctrl.render(desc_str, True, MUTED)
            self.screen.blit(ks, (col_x, row_y))
            self.screen.blit(ds, (col_x + 90, row_y))
            row_y += row_h

        # ---- Blinking start prompt ------------------------------------------
        if int(t * 2.2) % 2 == 0:
            hint = self._font_hint.render(
                "Press any key or click to begin", True, TEXT)
            self.screen.blit(hint, hint.get_rect(center=(W // 2, H - 60)))

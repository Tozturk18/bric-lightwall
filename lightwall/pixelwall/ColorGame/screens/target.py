# =============================================================================
# screens/target.py – Target colour display
#
# Fills the screen with a randomly generated RGB colour and shows a
# countdown timer.  Transitions to the match screen after TARGET_DISPLAY_TIME.
# =============================================================================

import random
import pygame
from config import TARGET_DISPLAY_TIME, WIDTH, HEIGHT


class TargetScreen:
    """
    Generates a random target colour, floods the display with it for exactly
    TARGET_DISPLAY_TIME seconds, then passes the colour to the match screen.
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        self._font_title    = pygame.font.SysFont("arial", 48, bold=True)
        self._font_rgb      = pygame.font.SysFont("courier new", 30)
        self._font_countdown = pygame.font.SysFont("arial", 26)

        self.target_color: tuple = (128, 128, 128)
        self._elapsed = 0.0
        self._next    = None

    # --- Screen interface ----------------------------------------------------

    def enter(self, data: dict) -> None:
        # Generate a fresh random RGB colour every round
        self.target_color = (
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )
        self._elapsed = 0.0
        self._next    = None

    def update(self, dt: float, events: list) -> tuple:
        self._elapsed += dt
        if self._elapsed >= TARGET_DISPLAY_TIME:
            self._next = "match"
        if self._next:
            return "match", {"target": self.target_color}
        return None, {}

    def draw(self) -> None:
        W, H = WIDTH, HEIGHT

        # Flood fill with target colour
        self.screen.fill(self.target_color)

        # ---- Progress bar (top of screen) -----------------------------------
        progress = min(self._elapsed / TARGET_DISPLAY_TIME, 1.0)
        bar_w    = int(W * progress)
        pygame.draw.rect(self.screen, (0, 0, 0),        (0, 0, W,     10))
        pygame.draw.rect(self.screen, (255, 255, 255),  (0, 0, bar_w, 10))

        # ---- Adaptive text colour -------------------------------------------
        r, g, b   = self.target_color
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        text_col  = (20, 20, 20) if luminance > 140 else (235, 235, 235)

        # ---- Instruction text -----------------------------------------------
        remaining = max(0.0, TARGET_DISPLAY_TIME - self._elapsed)

        title = self._font_title.render("REMEMBER THIS COLOUR", True, text_col)
        self.screen.blit(title, title.get_rect(center=(W // 2, H // 2 - 65)))

        # rgb_txt = self._font_rgb.render(
        #     f"RGB  ( {r:3d},  {g:3d},  {b:3d} )", True, text_col)
        # self.screen.blit(rgb_txt, rgb_txt.get_rect(center=(W // 2, H // 2)))

        countdown = self._font_countdown.render(
            f"{remaining:.1f} s", True, text_col)
        self.screen.blit(countdown, countdown.get_rect(center=(W // 2, H // 2 + 55)))

# =============================================================================
# screens/accuracy.py – Accuracy result screen
#
# Compares the user's mixed colour to the target using Euclidean RGB distance:
#
#     accuracy = (1 - distance / max_distance) × 100
#
# where  max_distance = √(255² × 3) ≈ 441.67
# =============================================================================

import math
import pygame

from config import (
    BG, PANEL_BG, TEXT, MUTED, ACCENT, DIVIDER,
    SUCCESS, WARNING, DANGER,
    EXCELLENT_THRESHOLD, GOOD_THRESHOLD, 
    WIDTH, HEIGHT,
)


_MAX_DIST = math.sqrt(255 ** 2 * 3)    # ≈ 441.67


def _compute_accuracy(target: tuple, mixed: tuple) -> float:
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, mixed)))
    return (1.0 - dist / _MAX_DIST) * 100.0


class AccuracyScreen:
    """
    Shows the target colour, the user's colour, and the accuracy percentage.
    The score counts up from 0 to the final value over ~1 second.
    Pressing Enter / Space / clicking "Play Again" restarts the game.
    """

    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        self._font_hdr   = pygame.font.SysFont("arial", 24, bold=True)
        self._font_big   = pygame.font.SysFont("arial", 80, bold=True)
        self._font_msg   = pygame.font.SysFont("arial", 36, bold=True)
        self._font_med   = pygame.font.SysFont("arial", 20)
        self._font_lbl   = pygame.font.SysFont("arial", 17, bold=True)
        self._font_mono  = pygame.font.SysFont("courier new", 17)

        self.target: tuple = (128, 128, 128)
        self.mixed:  tuple = (128, 128, 128)
        self._score        = 0.0          # true accuracy
        self._displayed    = 0.0          # animated value
        self._t            = 0.0
        self._next         = None
        self._btn_hover    = False

        # "Play Again" button
        self._btn = pygame.Rect(WIDTH // 2 - 170, HEIGHT - 115, 340, 56)

    # --- Screen interface ----------------------------------------------------

    def enter(self, data: dict) -> None:
        self.target     = data.get("target", (128, 128, 128))
        self.mixed      = data.get("mixed",  (128, 128, 128))
        self._score     = _compute_accuracy(self.target, self.mixed)
        self._displayed = 0.0
        self._t         = 0.0
        self._next      = None

    def update(self, dt: float, events: list) -> tuple:
        self._t += dt

        # Animate score counting up over ~1.2 seconds
        self._displayed = min(self._score, self._t * self._score / 1.2)

        mx, my = pygame.mouse.get_pos()
        self._btn_hover = self._btn.collidepoint(mx, my)

        for e in events:
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if self._btn.collidepoint(e.pos):
                    self._next = "target"
            if e.type == pygame.KEYDOWN and e.key in (
                    pygame.K_RETURN, pygame.K_SPACE):
                self._next = "target"

        return ("target", {}) if self._next else (None, {})

    def draw(self) -> None:
        self.screen.fill(BG)
        self._draw_header()
        self._draw_swatches()
        self._draw_score()
        self._draw_button()

    # ---- private helpers ----------------------------------------------------

    def _draw_header(self) -> None:
        pygame.draw.rect(self.screen, PANEL_BG, (0, 0, WIDTH, 52))
        pygame.draw.line(self.screen, DIVIDER, (0, 52), (WIDTH, 52))
        txt = self._font_hdr.render("ACCURACY RESULT", True, MUTED)
        self.screen.blit(txt, txt.get_rect(center=(WIDTH // 2, 26)))

    def _draw_swatches(self) -> None:
        SW, SH  = 230, 190
        gap     = 70
        total_w = SW * 2 + gap
        lx      = WIDTH // 2 - total_w // 2
        rx      = lx + SW + gap
        sy      = 68

        for color, x, label in [
            (self.target, lx, "TARGET"),
            (self.mixed,  rx, "YOUR MIX"),
        ]:
            # Label above swatch
            lbl = self._font_lbl.render(label, True, MUTED)
            self.screen.blit(lbl, (x + SW // 2 - lbl.get_width() // 2, sy - 24))

            # Swatch rectangle
            rect = pygame.Rect(x, sy, SW, SH)
            pygame.draw.rect(self.screen, color, rect, border_radius=12)
            pygame.draw.rect(self.screen, DIVIDER, rect, 2, border_radius=12)

            # RGB value below swatch
            r, g, b = color
            mono = self._font_mono.render(
                f"({r:3d}, {g:3d}, {b:3d})", True, MUTED)
            self.screen.blit(mono, (
                x + SW // 2 - mono.get_width() // 2,
                sy + SH + 5,
            ))

    def _draw_score(self) -> None:
        score   = self._score
        display = self._displayed

        if score >= EXCELLENT_THRESHOLD:
            msg, col = "Excellent Match!", SUCCESS
        elif score >= GOOD_THRESHOLD:
            msg, col = "Good Match!", WARNING
        else:
            msg, col = "Try Again!", DANGER

        # Large percentage number
        pct = self._font_big.render(f"{display:.1f}%", True, col)
        self.screen.blit(pct, pct.get_rect(center=(WIDTH // 2, 370)))

        # Verdict message
        verdict = self._font_msg.render(msg, True, col)
        self.screen.blit(verdict, verdict.get_rect(center=(WIDTH // 2, 450)))

        # Progress bar
        bar_w = 520
        bar_h = 18
        bx = WIDTH // 2 - bar_w // 2
        by = 495
        pygame.draw.rect(self.screen, PANEL_BG, (bx, by, bar_w, bar_h),
                         border_radius=9)
        fill = int(bar_w * min(display / 100.0, 1.0))
        if fill > 0:
            pygame.draw.rect(self.screen, col, (bx, by, fill, bar_h),
                             border_radius=9)
        pygame.draw.rect(self.screen, DIVIDER, (bx, by, bar_w, bar_h), 1,
                         border_radius=9)

        # Threshold tick marks
        for threshold, label in [
            (GOOD_THRESHOLD, f"{GOOD_THRESHOLD}%"),
            (EXCELLENT_THRESHOLD, f"{EXCELLENT_THRESHOLD}%"),
        ]:
            tx = bx + int(bar_w * threshold / 100)
            pygame.draw.line(self.screen, DIVIDER, (tx, by - 4), (tx, by + bar_h + 4), 2)
            tick_lbl = self._font_mono.render(label, True, (90, 90, 110))
            self.screen.blit(tick_lbl, (tx - tick_lbl.get_width() // 2, by + bar_h + 6))

    def _draw_button(self) -> None:
        col = (130, 110, 255) if self._btn_hover else ACCENT
        pygame.draw.rect(self.screen, col, self._btn, border_radius=12)
        txt = self._font_hdr.render("PLAY AGAIN", True, (255, 255, 255))
        self.screen.blit(txt, txt.get_rect(center=self._btn.center))

        sub = self._font_med.render("Enter / Space", True, MUTED)
        self.screen.blit(sub, sub.get_rect(
            center=(WIDTH // 2, self._btn.bottom + 18)))

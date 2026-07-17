# =============================================================================
# screens/match.py – Colour matching interface  (square layout)
#
#   ┌─────────────────────────────────────────┐
#   │                                         │
#   │    RGB Triangle  (corners glow with     │
#   │    current R / G / B strength)          │
#   │                                         │
#   │              ● fixed cursor             │
#   │         (colour = raw slider mix)       │
#   │                                         │
#   ├─────────────────────────────────────────┤
#   │  RED Q/A   GREEN W/S   BLUE E/D  [mix]  │  140 px
#   └─────────────────────────────────────────┘
#
# The triangle is rebuilt once per round (barycentric base array).
# Each frame, apply_slider_colors() updates the surface in-place via
# a single vectorised numpy multiply — no per-frame allocation.
#
# Submit: Enter key
# =============================================================================

import pygame

from config import (
    BG, PANEL_BG, MUTED, DIVIDER,
    WIDTH, HEIGHT, SLIDER_AREA_H, TRI_AREA_W, TRI_AREA_H,
)
from triangle import (
    build_triangle_base,
    make_triangle_surface,
    apply_slider_colors,
    draw_centroid_marker,
)
from sliders import SliderInput


_TRI_AREA   = (0, 0, TRI_AREA_W, TRI_AREA_H)
_TRI_MARGIN = 55

# Small mix-colour swatch in the slider strip (right side)
_SWATCH_SIZE = 60
_SWATCH_X    = WIDTH  - _SWATCH_SIZE - 16
_SWATCH_Y    = HEIGHT - SLIDER_AREA_H + (SLIDER_AREA_H - _SWATCH_SIZE) // 2


class MatchScreen:
    """
    Minimal match screen: dynamic RGB triangle + keyboard channel bars.
    Press Enter to submit.
    """

    def __init__(self, screen: pygame.Surface, sliders: SliderInput):
        self.screen  = screen
        self.sliders = sliders

        self._font_med  = pygame.font.SysFont("arial", 18)
        self._font_lbl  = pygame.font.SysFont("arial", 16, bold=True)
        self._font_hint = pygame.font.SysFont("arial", 14)

        self.target_color: tuple = (128, 0, 128)
        self._mixed: tuple       = (128, 128, 128)

        self._base_wh3  = None   # (W, H, 3) float32 barycentric weights
        self._tri_surf  = None   # reusable pygame.Surface
        self._verts     = None   # corner screen positions
        self._next      = None

    # --- Screen interface ----------------------------------------------------

    def enter(self, data: dict) -> None:
        self.target_color = data.get("target", (200, 100, 50))
        self._next        = None

        if hasattr(self.sliders, "reset"):
            self.sliders.reset()

        # Pre-compute barycentric weights (once per round, ~0.3–0.8 s)
        self._base_wh3, self._verts = build_triangle_base(
            WIDTH, HEIGHT,
            area_rect=_TRI_AREA,
            margin=_TRI_MARGIN,
        )
        # Allocate the reusable draw surface
        self._tri_surf = make_triangle_surface(WIDTH, HEIGHT)

        # Paint initial state (all sliders at 128)
        r, g, b = self.sliders.get_values()
        apply_slider_colors(self._tri_surf, self._base_wh3, r, g, b)

    def update(self, dt: float, events: list) -> tuple:
        self.sliders.update(events)

        r, g, b      = self.sliders.get_values()
        self._mixed  = (r, g, b)

        # Update triangle in-place — fast numpy multiply, no allocation
        if self._base_wh3 is not None:
            apply_slider_colors(self._tri_surf, self._base_wh3, r, g, b)

        for e in events:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_RETURN:
                self._next = "accuracy"

        if self._next:
            return "accuracy", {
                "target": self.target_color,
                "mixed":  self._mixed,
            }
        return None, {}

    def draw(self) -> None:
        self.screen.fill(BG)
        self._draw_triangle()
        self._draw_slider_strip()

    # ---- private ------------------------------------------------------------

    def _draw_triangle(self) -> None:
        # Dynamic triangle (corners glow at current R/G/B strength)
        if self._tri_surf:
            self.screen.blit(self._tri_surf, (0, 0))

        if self._verts is None:
            return

        # Centroid marker: a filled circle showing the actual blended mix
        # colour at the triangle's centre, drawn directly on the shared
        # render surface so it appears on the wall and the browser mirror
        # identically - there is no separate browser-side render of this.
        r, g, b = self._mixed
        draw_centroid_marker(self.screen, self._verts, r, g, b)

        # Corner labels with current channel value
        r, g, b = self._mixed
        corner_defs = [
            ("RED",   "red",   (255,  80,  80), ( -5, -24), r),
            ("GREEN", "green", ( 55, 210,  75), ( 10,   8), g),
            ("BLUE",  "blue",  ( 70, 120, 255), (-62,   8), b),
        ]
        for label, key, col, (ox, oy), val in corner_defs:
            vx, vy = self._verts[key]
            # Dim the label when channel is low
            brightness = max(80, val)
            c = tuple(int(ch * brightness / 255) for ch in col)
            surf = self._font_lbl.render(f"{label}  {val}", True, c)
            self.screen.blit(surf, (vx + ox, vy + oy))



    def _draw_slider_strip(self) -> None:
        strip_y = HEIGHT - SLIDER_AREA_H

        pygame.draw.rect(self.screen, PANEL_BG,
                         (0, strip_y, WIDTH, SLIDER_AREA_H))
        pygame.draw.line(self.screen, DIVIDER,
                         (0, strip_y), (WIDTH, strip_y))

        self.sliders.draw(self.screen, self._font_med)

        # Mix swatch
        pygame.draw.rect(self.screen, self._mixed,
                         (_SWATCH_X, _SWATCH_Y, _SWATCH_SIZE, _SWATCH_SIZE),
                         border_radius=6)
        pygame.draw.rect(self.screen, DIVIDER,
                         (_SWATCH_X, _SWATCH_Y, _SWATCH_SIZE, _SWATCH_SIZE),
                         2, border_radius=6)

        hint = self._font_hint.render("Enter → submit", True, MUTED)
        self.screen.blit(hint, (
            _SWATCH_X + _SWATCH_SIZE // 2 - hint.get_width() // 2,
            _SWATCH_Y + _SWATCH_SIZE + 4,
        ))
# =============================================================================
# triangle.py – Dynamic RGB triangle renderer
#
# The triangle has three corners whose colours scale with the current slider
# values:
#   Red corner   →  (r, 0, 0)
#   Green corner →  (0, g, 0)
#   Blue corner  →  (0, 0, b)
#
# Every interior pixel blends barycentrically:
#   colour(x,y) = λR·(r,0,0) + λG·(0,g,0) + λB·(0,0,b)
#               = (λR·r, λG·g, λB·b)
#
# Workflow
# --------
#   base, verts = build_triangle_base(W, H, area_rect, margin)
#   surf        = make_triangle_surface(W, H)
#
#   # each frame:
#   apply_slider_colors(surf, base, r, g, b)
#   screen.blit(surf, (0,0))
# =============================================================================

import math
import numpy as np
import pygame


def build_triangle_base(
    screen_w: int,
    screen_h: int,
    area_rect: tuple = None,
    margin: int = 55,
) -> tuple:
    """
    Pre-compute barycentric weight arrays (done once per game session).

    Returns
    -------
    base : np.ndarray  shape (W, H, 3)  dtype float32  values in [0, 1]
           base[x, y] = (λR, λG, λB) — the three corner weights for that pixel.
           Pixels outside the triangle are (0, 0, 0).
    vertices : dict  {'red': (x,y), 'green': (x,y), 'blue': (x,y)}
    """
    if area_rect is None:
        area_rect = (0, 0, screen_w, screen_h)
    ax, ay, aw, ah = area_rect

    side  = min(aw, ah) - margin * 2
    h_tri = side * math.sqrt(3.0) / 2.0
    cx    = ax + aw / 2.0
    cy    = ay + ah / 2.0

    vR = np.array([cx,             cy - h_tri * 2.0 / 3.0])  # Red   – apex
    vG = np.array([cx + side / 2,  cy + h_tri / 3.0       ])  # Green – bottom-right
    vB = np.array([cx - side / 2,  cy + h_tri / 3.0       ])  # Blue  – bottom-left

    # Pixel grid in (H, W) order
    xs = np.arange(screen_w, dtype=np.float32)
    ys = np.arange(screen_h, dtype=np.float32)
    px, py = np.meshgrid(xs, ys)   # shape: (H, W)

    denom = ((vG[1] - vB[1]) * (vR[0] - vB[0]) +
             (vB[0] - vG[0]) * (vR[1] - vB[1]))

    lR = ((vG[1] - vB[1]) * (px - vB[0]) +
          (vB[0] - vG[0]) * (py - vB[1])) / denom
    lG = ((vB[1] - vR[1]) * (px - vB[0]) +
          (vR[0] - vB[0]) * (py - vB[1])) / denom
    lB = 1.0 - lR - lG

    inside = (lR >= -1e-6) & (lG >= -1e-6) & (lB >= -1e-6)

    base_hw3 = np.zeros((screen_h, screen_w, 3), dtype=np.float32)
    base_hw3[inside, 0] = np.clip(lR[inside], 0.0, 1.0)
    base_hw3[inside, 1] = np.clip(lG[inside], 0.0, 1.0)
    base_hw3[inside, 2] = np.clip(lB[inside], 0.0, 1.0)

    # Transpose to (W, H, 3) — matches pygame.surfarray.pixels3d layout
    base_wh3 = base_hw3.transpose(1, 0, 2)

    vertices = {
        "red":   (int(round(vR[0])), int(round(vR[1]))),
        "green": (int(round(vG[0])), int(round(vG[1]))),
        "blue":  (int(round(vB[0])), int(round(vB[1]))),
    }
    return base_wh3, vertices


def make_triangle_surface(screen_w: int, screen_h: int) -> pygame.Surface:
    """Allocate the reusable draw surface (call once, keep across frames)."""
    surf = pygame.Surface((screen_w, screen_h))
    surf.set_colorkey((0, 0, 0))   # transparent outside the triangle
    return surf


def apply_slider_colors(
    surf: pygame.Surface,
    base_wh3: np.ndarray,
    r: int, g: int, b: int,
) -> None:
    """
    Update the triangle surface in-place for the current slider values.

    Each pixel becomes (λR·r, λG·g, λB·b), so:
      - The red corner glows at intensity r
      - The green corner glows at intensity g
      - The blue corner glows at intensity b
      - Interior pixels blend proportionally

    O(W·H) but fully vectorised — typically < 3 ms on a modern CPU.
    """
    # broadcast multiply: (W,H,3) × [r,g,b]  →  (W,H,3)
    arr = (base_wh3 * np.array([r, g, b], dtype=np.float32)).astype(np.uint8)

    px = pygame.surfarray.pixels3d(surf)   # locks surface; shape (W, H, 3)
    px[...] = arr
    del px                                 # release lock


def triangle_centroid(vertices: dict) -> tuple:
    """Return the screen-space centroid of the triangle as (x, y)."""
    xs = [v[0] for v in vertices.values()]
    ys = [v[1] for v in vertices.values()]
    return int(sum(xs) / 3), int(sum(ys) / 3)
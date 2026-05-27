#!/usr/bin/env python3

from __future__ import annotations

from typing import Dict, Iterable, Tuple

from .framebuffer import Color, FrameBuffer


DIGITS: Dict[str, Tuple[str, ...]] = {
    "0": ("111", "101", "101", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "010", "010", "111"),
    "2": ("111", "001", "001", "111", "100", "100", "111"),
    "3": ("111", "001", "001", "111", "001", "001", "111"),
    "4": ("101", "101", "101", "111", "001", "001", "001"),
    "5": ("111", "100", "100", "111", "001", "001", "111"),
    "6": ("111", "100", "100", "111", "101", "101", "111"),
    "7": ("111", "001", "001", "010", "010", "010", "010"),
    "8": ("111", "101", "101", "111", "101", "101", "111"),
    "9": ("111", "101", "101", "111", "001", "001", "111"),
}


def measure_number(text: str, scale: int, spacing: int) -> Tuple[int, int]:
    digits = [char for char in text if char in DIGITS]
    if not digits:
        return 0, 0
    width = len(digits) * 3 * scale + max(0, len(digits) - 1) * spacing
    return width, 7 * scale


def draw_number(
    fb: FrameBuffer,
    value: int | str,
    color: Color = (0, 255, 0),
    scale: int | None = None,
    background: Color | None = None,
) -> None:
    text = str(value)
    digits = [char for char in text if char in DIGITS]
    if background is not None:
        fb.clear(background)
    if not digits:
        return

    if scale is None:
        max_scale_x = max(1, (fb.width - 4) // (len(digits) * 4 - 1))
        max_scale_y = max(1, (fb.height - 4) // 7)
        scale = max(1, min(max_scale_x, max_scale_y))

    spacing = max(1, scale)
    text_width, text_height = measure_number("".join(digits), scale, spacing)
    start_x = (fb.width - text_width) // 2
    start_y = (fb.height - text_height) // 2
    cursor_x = start_x

    for digit in digits:
        glyph = DIGITS[digit]
        for gy, row in enumerate(glyph):
            for gx, enabled in enumerate(row):
                if enabled != "1":
                    continue
                fb.fill_rect(cursor_x + gx * scale, start_y + gy * scale, scale, scale, color)
        cursor_x += 3 * scale + spacing


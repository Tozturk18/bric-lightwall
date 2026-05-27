#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple


Color = Tuple[int, int, int]


def clamp_u8(value: int) -> int:
    return max(0, min(255, int(value)))


@dataclass
class FrameBuffer:
    """Logical row-major RGB888 framebuffer with top-left pixel origin."""

    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("framebuffer width and height must be positive")
        self.pixels = bytearray(self.width * self.height * 3)

    def clear(self, color: Color = (0, 0, 0)) -> None:
        red, green, blue = (clamp_u8(c) for c in color)
        self.pixels[:] = bytes((red, green, blue)) * (self.width * self.height)

    def copy_bytes(self) -> bytes:
        return bytes(self.pixels)

    def set_pixel(self, x: int, y: int, color: Color) -> None:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return
        offset = (y * self.width + x) * 3
        self.pixels[offset] = clamp_u8(color[0])
        self.pixels[offset + 1] = clamp_u8(color[1])
        self.pixels[offset + 2] = clamp_u8(color[2])

    def fill_rect(self, x: int, y: int, width: int, height: int, color: Color) -> None:
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.width, x + width)
        y1 = min(self.height, y + height)
        for py in range(y0, y1):
            for px in range(x0, x1):
                self.set_pixel(px, py, color)

    def draw_line_h(self, x: int, y: int, width: int, color: Color) -> None:
        self.fill_rect(x, y, width, 1, color)

    def draw_line_v(self, x: int, y: int, height: int, color: Color) -> None:
        self.fill_rect(x, y, 1, height, color)

    def draw_border(self, color: Color) -> None:
        self.draw_line_h(0, 0, self.width, color)
        self.draw_line_h(0, self.height - 1, self.width, color)
        self.draw_line_v(0, 0, self.height, color)
        self.draw_line_v(self.width - 1, 0, self.height, color)

    def iter_rgb_tuples(self) -> Iterable[Color]:
        data = self.pixels
        for offset in range(0, len(data), 3):
            yield data[offset], data[offset + 1], data[offset + 2]


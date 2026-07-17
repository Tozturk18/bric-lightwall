# =============================================================================
# sliders.py – Slider input abstraction layer
#
# Usage:
#   from sliders import KeyboardSliderInput, GPIOSliderInput
#
#   # Desktop / testing
#   sliders = KeyboardSliderInput(x_positions=[227, 455, 682], y=652)
#
#   # Raspberry Pi  (MCP3008 ADC on SPI bus 0)
#   sliders = GPIOSliderInput(channels=(0, 1, 2))
#
# Both expose the same interface:
#   sliders.update(events)        – call every frame inside game loop
#   sliders.get_values()          – returns (r, g, b), each 0-255
#   sliders.draw(surface, font)   – optional on-screen rendering
# =============================================================================

import threading
from abc import ABC, abstractmethod
from collections import deque
import pygame


class SliderInput(ABC):
    """Abstract base – all slider sources implement this interface."""

    @abstractmethod
    def get_values(self) -> tuple:
        """Return current (r, g, b) values, each clamped to 0-255."""

    @abstractmethod
    def update(self, events: list) -> None:
        """
        Process input.  Called once per frame with the current event list.
        Hardware implementations may ignore events and poll directly.
        """

    def draw(self, surface: "pygame.Surface", font: "pygame.font.Font") -> None:
        """Optional on-screen rendering.  No-op for hardware implementations."""


# ---------------------------------------------------------------------------
# Desktop implementation – keyboard-driven channel bars
# ---------------------------------------------------------------------------

class KeyboardSliderInput(SliderInput):
    """
    Three keyboard-controlled channel bars rendered on-screen.

    Controls  (hold Shift for 4× speed):
      Q / A  →  Red   channel  +  / -
      W / S  →  Green channel  +  / -
      E / D  →  Blue  channel  +  / -
    """

    # Key pairs (increase, decrease) per channel
    _BINDS = [
        (pygame.K_q, pygame.K_a),   # Red
        (pygame.K_w, pygame.K_s),   # Green
        (pygame.K_e, pygame.K_d),   # Blue
    ]
    _COLORS = (
        (215,  60,  60),    # red channel colour
        ( 55, 200,  70),    # green channel colour
        ( 60, 115, 230),    # blue channel colour
    )
    _CHANNEL_LABELS = ("RED", "GREEN", "BLUE")
    _STEP      = 2   # units per frame (normal)
    _FAST_STEP = 8   # units per frame (Shift held)

    BAR_W = 200
    BAR_H = 20

    def __init__(self, x_positions: list, y: int):
        """
        Args:
            x_positions: list of three x-coordinates (bar centre x).
            y:           y-coordinate shared by all three bars (centre).
        """
        self._xs   = x_positions
        self._y    = y
        self._vals = [128, 128, 128]   # start at mid-range

    # --- SliderInput interface -----------------------------------------------

    def get_values(self) -> tuple:
        return tuple(self._vals)

    def update(self, events: list) -> None:
        keys = pygame.key.get_pressed()
        mods = pygame.key.get_mods()
        step = self._FAST_STEP if (mods & pygame.KMOD_SHIFT) else self._STEP

        for i, (up_key, dn_key) in enumerate(self._BINDS):
            if keys[up_key]:
                self._vals[i] = min(255, self._vals[i] + step)
            if keys[dn_key]:
                self._vals[i] = max(0, self._vals[i] - step)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        for i, cx in enumerate(self._xs):
            sx  = cx - self.BAR_W // 2
            sy  = self._y - self.BAR_H // 2
            val = self._vals[i]
            col = self._COLORS[i]
            fill = int(self.BAR_W * val / 255)

            # Track background
            pygame.draw.rect(surface, (45, 45, 62),
                             (sx, sy, self.BAR_W, self.BAR_H), border_radius=10)
            # Filled portion
            if fill > 0:
                pygame.draw.rect(surface, col,
                                 (sx, sy, fill, self.BAR_H), border_radius=10)
            # Border
            pygame.draw.rect(surface, (70, 70, 90),
                             (sx, sy, self.BAR_W, self.BAR_H), 1, border_radius=10)

            # Channel label + numeric value
            up_char = chr(self._BINDS[i][0]).upper()
            dn_char = chr(self._BINDS[i][1]).upper()
            lbl = font.render(
                f"{self._CHANNEL_LABELS[i]}: {val:3d}", True, (215, 215, 235))
            surface.blit(lbl, (cx - lbl.get_width() // 2, sy - 30))

            # Key-binding hint below the bar
            hint = font.render(f"[{up_char}] + / [{dn_char}] −", True, col)
            surface.blit(hint, (cx - hint.get_width() // 2, sy + self.BAR_H + 6))

    # --- public helpers ------------------------------------------------------

    def reset(self, r: int = 128, g: int = 128, b: int = 128) -> None:
        """Reset slider values (e.g. between rounds)."""
        self._vals = [r, g, b]


# ---------------------------------------------------------------------------
# Raspberry Pi implementation – MCP3008 ADC over SPI
# ---------------------------------------------------------------------------

class GPIOSliderInput(SliderInput):
    """
    Hardware slider input via MCP3008 10-bit ADC connected to the SPI bus.

    Requires:
        pip install spidev

    Wiring (MCP3008 to Raspberry Pi):
        MCP3008 VDD  → 3.3 V
        MCP3008 VREF → 3.3 V
        MCP3008 AGND → GND
        MCP3008 DGND → GND
        MCP3008 CLK  → GPIO 11  (SPI0 SCLK)
        MCP3008 DOUT → GPIO 9   (SPI0 MISO)
        MCP3008 DIN  → GPIO 10  (SPI0 MOSI)
        MCP3008 CS   → GPIO 8   (SPI0 CE0)

        CH0 → Red slider wiper
        CH1 → Green slider wiper
        CH2 → Blue slider wiper
        (Connect each slider: one end → 3.3 V, other end → GND)
    """

    def __init__(self, channels: tuple = (0, 1, 2),
                 spi_bus: int = 0, spi_device: int = 0):
        try:
            import spidev
        except ImportError as exc:
            raise RuntimeError(
                "spidev is not installed.  Run: pip install spidev") from exc

        self._spi = spidev.SpiDev()
        self._spi.open(spi_bus, spi_device)
        self._spi.max_speed_hz = 1_350_000
        self._channels = channels
        self._vals = [0, 0, 0]

    # --- SliderInput interface -----------------------------------------------

    def get_values(self) -> tuple:
        return tuple(self._vals)

    def update(self, events: list) -> None:
        """Ignores pygame events; polls the ADC directly."""
        self._vals = [self._read_adc(ch) for ch in self._channels]

    # --- private helpers -----------------------------------------------------

    def _read_adc(self, channel: int) -> int:
        """Read a 10-bit value from MCP3008 channel, scale to 0-255."""
        r   = self._spi.xfer2([1, (8 + channel) << 4, 0])
        raw = ((r[1] & 3) << 8) | r[2]          # 0 – 1023
        return int(raw * 255 // 1023)

    def __del__(self):
        try:
            self._spi.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Web implementation – values relayed from a browser client over websocket
# ---------------------------------------------------------------------------

class WebSliderInput(SliderInput):
    """
    Slider values driven by a browser client instead of local pygame input.

    A websocket handler (running in a different thread than the game loop)
    calls set_values() or nudge() as messages arrive; update() is a no-op
    here since there is nothing to poll from pygame's event list — the
    browser pushes state asynchronously. get_values() is safe to call from
    the game loop thread while set_values()/nudge() are called from the
    websocket thread.

    Also queues one-shot "advance" events (push_event()/drain_events()):
    every screen's own transition logic (start -> target on any keypress,
    match -> accuracy on Enter, accuracy -> target on Enter/Space/click)
    reads pygame's real event list directly, which is always empty when
    running headless under --web-input. Without a web-relayed equivalent,
    R/G/B nudges/sets still updated this object's state correctly, but the
    game could never leave the start screen to reach a point where that
    state was ever visible - main.py merges drained events into the real
    pygame event list each frame so those existing screen.update(dt,
    events) calls need no changes of their own.
    """

    def __init__(self, initial: tuple = (128, 128, 128)):
        self._lock = threading.Lock()
        self._vals = [clamp_u8(v) for v in initial]
        self._events = deque()

    # --- SliderInput interface -----------------------------------------------

    def get_values(self) -> tuple:
        with self._lock:
            return tuple(self._vals)

    def update(self, events: list) -> None:
        """No-op: values are pushed asynchronously via set_values()/nudge()."""

    # --- public helpers (called from the websocket thread) -------------------

    def set_values(self, r: int, g: int, b: int) -> None:
        with self._lock:
            self._vals = [clamp_u8(r), clamp_u8(g), clamp_u8(b)]

    def nudge(self, dr: int = 0, dg: int = 0, db: int = 0) -> None:
        with self._lock:
            self._vals[0] = clamp_u8(self._vals[0] + dr)
            self._vals[1] = clamp_u8(self._vals[1] + dg)
            self._vals[2] = clamp_u8(self._vals[2] + db)

    def reset(self, r: int = 128, g: int = 128, b: int = 128) -> None:
        """Reset slider values (e.g. between rounds); mirrors KeyboardSliderInput."""
        with self._lock:
            self._vals = [clamp_u8(r), clamp_u8(g), clamp_u8(b)]

    # --- one-shot event queue (called from the websocket thread / drained by the game loop) ---

    def push_event(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    def drain_events(self) -> list:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events


def clamp_u8(value: int) -> int:
    return max(0, min(255, int(value)))

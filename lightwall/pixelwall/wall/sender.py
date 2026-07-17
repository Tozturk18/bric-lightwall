# =============================================================================
# wall/sender.py – Real-time LED wall frame sender
#
# Architecture
# ------------
#   WallSender          – public API, called from the game loop
#     └── PanelSender × N  – one per Raspberry Pi / tile
#           └── background thread  – owns the TCP socket, drains a queue
#
# Game loop calls:
#   wall.send_surface(screen)   # pygame.Surface → scale → tessellate → dispatch
#
# Design goals
# ------------
#   • Never block the game loop.  If a Pi is behind, frames are dropped.
#   • Persistent TCP connections with automatic reconnect on failure.
#   • Wire protocol identical to send_test_frame.py:
#       header  "!IHHII"  = MAGIC, W, H, frame_id, payload_len
#       payload            = raw RGB bytes, row-major (y outer, x inner)
#
# Dependencies: numpy, Pillow, pygame  (all already in requirements.txt)
# =============================================================================

import socket
import struct
import threading
import queue
import logging

import numpy as np
from PIL import Image

import pygame

from .config import WallConfig

log = logging.getLogger(__name__)

MAGIC          = 0x42524943   # "BRIC"
HEADER_FORMAT  = "!IHHII"     # big-endian: uint32 uint16 uint16 uint32 uint32
HEADER_SIZE    = struct.calcsize(HEADER_FORMAT)  # 16 bytes
CONNECT_TIMEOUT = 3.0          # seconds
SEND_TIMEOUT    = 2.0          # seconds


# ---------------------------------------------------------------------------
# Per-Pi sender
# ---------------------------------------------------------------------------

class PanelSender:
    """
    Manages a persistent TCP connection to one Raspberry Pi.

    • Runs in a background daemon thread — never touches the game loop.
    • Queue depth is 2: the Pi always gets the freshest frame; older
      ones are silently dropped when it falls behind.
    • Reconnects automatically after a network error.
    """

    def __init__(self, host: str, port: int, tile_w: int, tile_h: int,
                 label: str = ""):
        self.host   = host
        self.port   = port
        self.tile_w = tile_w
        self.tile_h = tile_h
        self.label  = label or f"{host}:{port}"

        self._sock:   socket.socket | None = None
        self._queue:  queue.Queue = queue.Queue(maxsize=2)
        self._thread: threading.Thread = threading.Thread(
            target=self._run, daemon=True, name=f"panel-{self.label}")
        self._thread.start()

    # ---- public API ---------------------------------------------------------

    def submit(self, tile_rgb: np.ndarray, frame_id: int) -> None:
        """
        Non-blocking.  Drops the frame if the sender is behind.

        tile_rgb: uint8 array shape (tile_h, tile_w, 3), row-major.
        """
        try:
            self._queue.put_nowait((tile_rgb, frame_id))
        except queue.Full:
            pass   # drop — never stall the game loop

    def close(self) -> None:
        """Signal the background thread to exit cleanly."""
        self._queue.put(None)

    # ---- background thread --------------------------------------------------

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._disconnect()
                return

            tile_rgb, frame_id = item
            try:
                self._ensure_connected()
                self._send_frame(tile_rgb, frame_id)
            except OSError as exc:
                log.warning("[%s] send error: %s – will reconnect", self.label, exc)
                self._disconnect()

    def _ensure_connected(self) -> None:
        if self._sock is not None:
            return
        log.info("[%s] connecting to %s:%d …", self.label, self.host, self.port)
        sock = socket.create_connection((self.host, self.port),
                                        timeout=CONNECT_TIMEOUT)
        sock.settimeout(SEND_TIMEOUT)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        log.info("[%s] connected", self.label)

    def _disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _send_frame(self, tile_rgb: np.ndarray, frame_id: int) -> None:
        """
        Serialise tile_rgb and send with BRIC header.

        tile_rgb shape: (tile_h, tile_w, 3) uint8
        Wire order: row-major, matching send_test_frame.py
        """
        payload = tile_rgb.tobytes()         # row-major = y outer, x inner
        header  = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            self.tile_w,
            self.tile_h,
            frame_id,
            len(payload),
        )
        self._sock.sendall(header + payload)


# ---------------------------------------------------------------------------
# Wall-level sender
# ---------------------------------------------------------------------------

class WallSender:
    """
    Top-level sender:  pygame.Surface  →  scale  →  tessellate  →  N PanelSenders

    Usage
    -----
        cfg = WallConfig.from_args(rows=2, cols=2, tile_w=64, tile_h=64,
                                   hosts=["10.42.0.2", "10.42.0.3",
                                          "10.42.0.5", "10.42.0.4"])
        wall = WallSender(cfg)

        # inside game loop:
        wall.send_surface(screen)

        # on quit:
        wall.close()
    """

    def __init__(self, config: WallConfig):
        config.validate()
        self._cfg      = config
        self._frame_id = 0
        self._senders  = [
            PanelSender(
                host   = host,
                port   = port,
                tile_w = config.tile_w,
                tile_h = config.tile_h,
                label  = f"tile{i}@{host}:{port}",
            )
            for i, (host, port) in enumerate(config.hosts)
        ]
        log.info(
            "WallSender ready: %dx%d wall, %d tiles (%dx%d px each)",
            config.wall_w, config.wall_h,
            config.num_tiles, config.tile_w, config.tile_h,
        )

    # ---- public API ---------------------------------------------------------

    def send_surface(self, surface: pygame.Surface) -> None:
        """
        Capture one pygame frame and dispatch tiles to all Pis.
        Non-blocking: returns immediately after queuing.
        """
        wall_img = self._capture_and_scale(surface)
        tiles    = self._tessellate(wall_img)

        for sender, tile in zip(self._senders, tiles):
            arr = np.array(tile, dtype=np.uint8)   # (tile_h, tile_w, 3)
            sender.submit(arr, self._frame_id)

        self._frame_id += 1

    def close(self) -> None:
        """Cleanly shut down all background sender threads."""
        for s in self._senders:
            s.close()

    # ---- private ------------------------------------------------------------

    def _capture_and_scale(self, surface: pygame.Surface) -> Image.Image:
        """pygame.Surface → PIL Image scaled to exact wall pixel dimensions."""
        # surfarray gives (W, H, 3); PIL needs (H, W, 3)
        arr = pygame.surfarray.array3d(surface)
        img = Image.fromarray(arr.transpose(1, 0, 2))
        return img.resize((self._cfg.wall_w, self._cfg.wall_h), Image.BILINEAR)

    def _tessellate(self, img: Image.Image) -> list:
        """
        Crop img into (rows × cols) tiles in snake order.

        Even rows go left→right; odd rows go right→left.
        Mirrors the logic in tessellation.py.
        """
        cfg   = self._cfg
        tiles = []

        for row in range(cfg.rows):
            row_tiles = []
            for col in range(cfg.cols):
                left   = col * cfg.tile_w
                top    = row * cfg.tile_h
                right  = left + cfg.tile_w
                bottom = top  + cfg.tile_h
                row_tiles.append(img.crop((left, top, right, bottom)))

            if row % 2 == 1:
                row_tiles.reverse()

            tiles.extend(row_tiles)

        return tiles
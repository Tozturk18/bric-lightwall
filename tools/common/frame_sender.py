#!/usr/bin/env python3

from __future__ import annotations

import math
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple


BRCP_MAGIC = b"BRCP"
BRIC_MAGIC = b"BRIC"
BRCP_HEADER = struct.Struct("!4sHHIHHH")
BRIC_HEADER = struct.Struct("!4sBBHIHHHHHHI")
BRCP_HEADER_SIZE = BRCP_HEADER.size
BRIC_HEADER_SIZE = BRIC_HEADER.size
BRIC_VERSION = 1
BRIC_PACKET_TYPE_FRAME_CHUNK = 1
DEFAULT_CHUNK_SIZE = 1024
SAFE_LAN_MTU_PAYLOAD = 1400
_FRAME_NUMBER_LOCK = threading.Lock()
_NEXT_FRAME_NUMBER = int(time.time() * 1000) & 0xFFFFFFFF


def next_frame_number() -> int:
    global _NEXT_FRAME_NUMBER
    with _FRAME_NUMBER_LOCK:
        _NEXT_FRAME_NUMBER = (_NEXT_FRAME_NUMBER + 1) & 0xFFFFFFFF
        if _NEXT_FRAME_NUMBER == 0:
            _NEXT_FRAME_NUMBER = 1
        return _NEXT_FRAME_NUMBER


@dataclass
class SendStats:
    frame_number: int
    chunks: int
    bytes_sent: int


def validate_rgb_frame(frame: bytes | bytearray | memoryview, width: int, height: int) -> None:
    expected = width * height * 3
    if len(frame) != expected:
        raise ValueError(f"frame is {len(frame)} bytes; expected {expected} for {width}x{height}")


class ChunkedUDPSender:
    """Chunked UDP sender for logical RGB888 wall frames.

    BRCP is the Mac-side protocol used by the new tools:
    magic, width, height, frame_number, chunk_index, total_chunks, payload_length.

    The older BRIC header remains available for compatibility with earlier local
    scripts; new applications should use the default BRCP mode.
    """

    def __init__(
        self,
        host: str,
        port: int = 4210,
        width: int = 64,
        height: int = 64,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        protocol: str = "brcp",
        timeout: float = 1.0,
    ) -> None:
        self.host = host
        self.port = port
        self.width = width
        self.height = height
        self.chunk_size = chunk_size
        self.protocol = protocol.lower()
        self.address: Tuple[str, int] = (host, port)
        self.frame_number = next_frame_number()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)
        self._validate_options()

    def close(self) -> None:
        self.sock.close()

    def __enter__(self) -> "ChunkedUDPSender":
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.close()

    def send_frame(
        self,
        frame: bytes | bytearray | memoryview,
        frame_number: Optional[int] = None,
    ) -> SendStats:
        validate_rgb_frame(frame, self.width, self.height)
        number = self.frame_number if frame_number is None else frame_number
        total_chunks = math.ceil(len(frame) / self.chunk_size)
        bytes_sent = 0

        for protocol in self._protocols_to_send():
            for chunk_index in range(total_chunks):
                offset = chunk_index * self.chunk_size
                payload = frame[offset : offset + self.chunk_size]
                packet = self._build_header(
                    protocol, number, chunk_index, total_chunks, len(payload)
                ) + bytes(payload)
                bytes_sent += self.sock.sendto(packet, self.address)

        if frame_number is None:
            self.frame_number = (self.frame_number + 1) & 0xFFFFFFFF
            if self.frame_number == 0:
                self.frame_number = 1

        return SendStats(
            frame_number=number,
            chunks=total_chunks * len(self._protocols_to_send()),
            bytes_sent=bytes_sent,
        )

    def send_solid(self, red: int, green: int, blue: int) -> SendStats:
        pixel = bytes((red & 0xFF, green & 0xFF, blue & 0xFF))
        return self.send_frame(pixel * (self.width * self.height))

    def _build_header(
        self,
        protocol: str,
        frame_number: int,
        chunk_index: int,
        total_chunks: int,
        payload_length: int,
    ) -> bytes:
        if protocol == "brcp":
            return BRCP_HEADER.pack(
                BRCP_MAGIC,
                self.width,
                self.height,
                frame_number & 0xFFFFFFFF,
                chunk_index,
                total_chunks,
                payload_length,
            )

        if protocol == "bric":
            return BRIC_HEADER.pack(
                BRIC_MAGIC,
                BRIC_VERSION,
                BRIC_PACKET_TYPE_FRAME_CHUNK,
                BRIC_HEADER_SIZE,
                frame_number & 0xFFFFFFFF,
                self.width,
                self.height,
                chunk_index,
                total_chunks,
                payload_length,
                0,
                0,
            )

        raise ValueError(f"unsupported UDP protocol: {protocol}")

    def _protocols_to_send(self) -> tuple[str, ...]:
        if self.protocol == "both":
            return ("brcp", "bric")
        return (self.protocol,)

    def _validate_options(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("width and height must be positive")
        if self.chunk_size <= 0:
            raise ValueError("chunk size must be positive")
        if self.protocol not in ("brcp", "bric", "both"):
            raise ValueError(f"unsupported UDP protocol: {self.protocol}")
        header_size = BRIC_HEADER_SIZE if self.protocol in ("bric", "both") else BRCP_HEADER_SIZE
        if self.chunk_size + header_size > SAFE_LAN_MTU_PAYLOAD:
            max_chunk = SAFE_LAN_MTU_PAYLOAD - header_size
            raise ValueError(
                f"chunk size {self.chunk_size} is too large for safe LAN UDP; "
                f"use {max_chunk} or less"
            )


def send_tcp_rgb_frame(
    host: str,
    port: int,
    frame: bytes | bytearray | memoryview,
    width: int,
    height: int,
    timeout: float = 2.0,
) -> None:
    """Send a raw RGB888 frame over TCP for legacy full-frame receivers.

    This intentionally does not add a new header. It exists only for simple
    legacy receivers that already expect exactly width * height * 3 bytes.
    """

    validate_rgb_frame(frame, width, height)
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(frame)


def pace_frame(start_time: float, fps: float) -> None:
    if fps <= 0:
        return
    frame_interval = 1.0 / fps
    elapsed = time.monotonic() - start_time
    time.sleep(max(0.0, frame_interval - elapsed))

#!/usr/bin/env python3

from __future__ import annotations

import socket
import struct
import threading

# Fixed local port used by every game subprocess to tee wall frames back to
# the Flask parent process for websocket rebroadcast to browser clients.
# Fixed rather than per-launch because only one game subprocess ever runs at
# a time (last-wins): the orchestrator confirms the previous subprocess is
# dead (proc.wait()/proc.kill()) before starting the next one, so there is
# never a window where two processes could bind or send to it concurrently.
DEFAULT_MIRROR_PORT = 47600

# A raw wall frame (width * height * 3 bytes) routinely exceeds the OS's
# single-UDP-datagram limit well before it approaches the 65507-byte
# theoretical maximum - on macOS this machine's ceiling was observed
# between 8192 and 16384 bytes, and a 128x128 wall's frame is 49152 bytes.
# sendto() raises "Message too long" past that ceiling, which the original
# unchunked version of this module silently swallowed via its
# except OSError: pass - so mirrored frames disappeared completely for any
# wall bigger than about one small tile, with no visible error anywhere.
# Chunking below this size avoids ever hitting that ceiling, on any
# platform's loopback interface.
CHUNK_PAYLOAD_SIZE = 4096
_HEADER = struct.Struct("!IHH")  # frame_id, chunk_index, total_chunks
_HEADER_SIZE = _HEADER.size


class FrameMirror:
    """
    Best-effort tee of wall frames to a local UDP port so a Flask-side web
    UI can rebroadcast them to browser clients over a websocket.

    This is purely additive: it runs after the real wall send, on a
    loopback-only destination, and any failure (nobody listening, buffer
    full, etc.) is swallowed. It must never affect wall output or crash
    the game loop.

    Frames are chunked (see CHUNK_PAYLOAD_SIZE) since a raw frame routinely
    exceeds the OS's single-UDP-datagram size limit.
    """

    def __init__(self, port: int = DEFAULT_MIRROR_PORT):
        self._address = ("127.0.0.1", port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._frame_id = 0

    def send(self, frame: bytes) -> None:
        self._frame_id = (self._frame_id + 1) & 0xFFFFFFFF
        total_chunks = max(1, (len(frame) + CHUNK_PAYLOAD_SIZE - 1) // CHUNK_PAYLOAD_SIZE)
        try:
            for chunk_index in range(total_chunks):
                start = chunk_index * CHUNK_PAYLOAD_SIZE
                payload = frame[start:start + CHUNK_PAYLOAD_SIZE]
                header = _HEADER.pack(self._frame_id, chunk_index, total_chunks)
                self._sock.sendto(header + payload, self._address)
        except OSError:
            pass

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


class FrameReassembler:
    """
    Reassembles FrameMirror's chunked datagrams back into complete frames.

    Stateless across frame_id boundaries beyond the single in-progress
    frame: if a new frame_id arrives before the previous one completed,
    the incomplete one is simply dropped (matching FrameMirror's own
    best-effort, never-block philosophy - a dropped mirror frame is just a
    skipped browser preview frame, never something worth blocking or
    erroring over).
    """

    def __init__(self) -> None:
        self._frame_id = None
        self._total_chunks = 0
        self._chunks = {}

    def add_datagram(self, data: bytes) -> "bytes | None":
        if len(data) < _HEADER_SIZE:
            return None
        frame_id, chunk_index, total_chunks = _HEADER.unpack_from(data, 0)
        payload = data[_HEADER_SIZE:]

        if frame_id != self._frame_id:
            self._frame_id = frame_id
            self._total_chunks = total_chunks
            self._chunks = {}

        if chunk_index >= self._total_chunks:
            return None
        self._chunks[chunk_index] = payload

        if len(self._chunks) < self._total_chunks:
            return None

        complete = b"".join(self._chunks[i] for i in range(self._total_chunks))
        self._frame_id = None
        self._chunks = {}
        return complete

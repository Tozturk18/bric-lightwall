#!/usr/bin/env python3

import socket
import struct
import time
import colorsys

HOST = "10.42.0.2"
PORT = 8765

W = 64
H = 64

MAGIC = 0x42524943  # "BRIC"

def rgb_at(x, y, t):
    hue = ((x / (W - 1)) + t) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)

with socket.create_connection((HOST, PORT)) as s:
    frame_id = 0

    while True:
        payload = bytearray()

        for y in range(H):
            for x in range(W):
                payload.extend(rgb_at(x, y, time.time() * 0.1))

        header = struct.pack(
            "!IHHII",
            MAGIC,
            W,
            H,
            frame_id,
            len(payload)
        )

        s.sendall(header + payload)
        frame_id += 1
        time.sleep(1 / 30)

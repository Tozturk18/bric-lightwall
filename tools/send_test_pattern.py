#!/usr/bin/env python3

import argparse
import colorsys
import math
import socket
import struct
import time


MAGIC = b"BRIC"
VERSION = 1
PACKET_TYPE_FRAME_CHUNK = 1
HEADER_SIZE = 28
HEADER = struct.Struct("!4sBBHIHHHHHHI")


def initial_frame_id():
    frame_id = int(time.time() * 1000) & 0xFFFFFFFF
    return frame_id or 1


def build_header(frame_id, width, height, chunk_index, total_chunks, payload_size):
    return HEADER.pack(
        MAGIC,
        VERSION,
        PACKET_TYPE_FRAME_CHUNK,
        HEADER_SIZE,
        frame_id & 0xFFFFFFFF,
        width,
        height,
        chunk_index,
        total_chunks,
        payload_size,
        0,
        0,
    )


def send_frame(sock, address, frame, frame_id, width, height, chunk_size):
    total_chunks = math.ceil(len(frame) / chunk_size)
    for chunk_index in range(total_chunks):
        offset = chunk_index * chunk_size
        payload = frame[offset : offset + chunk_size]
        sock.sendto(
            build_header(frame_id, width, height, chunk_index, total_chunks, len(payload))
            + payload,
            address,
        )


def gradient(width, height, tick):
    data = bytearray(width * height * 3)
    i = 0
    phase = tick % 256
    for y in range(height):
        for x in range(width):
            data[i] = (x * 255 // max(1, width - 1) + phase) & 0xFF
            data[i + 1] = y * 255 // max(1, height - 1)
            data[i + 2] = ((x + y) * 255 // max(1, width + height - 2)) & 0xFF
            i += 3
    return bytes(data)


def moving_bar(width, height, tick):
    data = bytearray(width * height * 3)
    center = tick % max(1, width)
    i = 0
    for _y in range(height):
        for x in range(width):
            distance = min(abs(x - center), width - abs(x - center))
            level = max(0, 255 - distance * 36)
            data[i] = level
            data[i + 1] = 40
            data[i + 2] = 255 - level
            i += 3
    return bytes(data)


def checkerboard(width, height, tick):
    data = bytearray(width * height * 3)
    cell = 8
    i = 0
    phase = (tick // 8) & 1
    for y in range(height):
        for x in range(width):
            on = ((x // cell) + (y // cell) + phase) & 1
            color = (255, 255, 255) if on else (0, 35, 120)
            data[i], data[i + 1], data[i + 2] = color
            i += 3
    return bytes(data)


def color_cycle(width, height, tick):
    r, g, b = colorsys.hsv_to_rgb((tick % 360) / 360.0, 1.0, 1.0)
    return bytes((int(r * 255), int(g * 255), int(b * 255))) * (width * height)


PATTERNS = {
    "gradient": gradient,
    "moving-bar": moving_bar,
    "checkerboard": checkerboard,
    "color-cycle": color_cycle,
}


def main():
    parser = argparse.ArgumentParser(description="Send BRIC RGB888 test patterns.")
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4210)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--pattern", choices=sorted(PATTERNS), default="gradient")
    parser.add_argument("--frames", type=int, default=0, help="0 means run forever")
    args = parser.parse_args()

    if args.chunk_size <= 0 or args.chunk_size + HEADER_SIZE > 1400:
        raise SystemExit("--chunk-size must be 1..1372 for safe LAN UDP datagrams")

    address = (args.ip, args.port)
    frame_id = initial_frame_id()
    tick = 0
    sent = 0
    frame_interval = 0.0 if args.fps <= 0 else 1.0 / args.fps
    make_frame = PATTERNS[args.pattern]

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while args.frames == 0 or sent < args.frames:
            start = time.monotonic()
            frame = make_frame(args.width, args.height, tick)
            send_frame(sock, address, frame, frame_id, args.width, args.height, args.chunk_size)
            frame_id = (frame_id + 1) & 0xFFFFFFFF
            tick += 1
            sent += 1
            if frame_interval > 0:
                elapsed = time.monotonic() - start
                time.sleep(max(0.0, frame_interval - elapsed))


if __name__ == "__main__":
    main()

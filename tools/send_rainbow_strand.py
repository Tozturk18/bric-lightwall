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
        packet = build_header(
            frame_id, width, height, chunk_index, total_chunks, len(payload)
        ) + payload
        sock.sendto(packet, address)


def strand_index(x, y, width, height, order):
    if order == "serpentine":
        return y * width + (x if y % 2 == 0 else width - 1 - x)
    if order == "column-major":
        return x * height + y
    if order == "column-serpentine":
        return x * height + (y if x % 2 == 0 else height - 1 - y)
    return y * width + x


def make_rainbow_frame(width, height, order, phase, cycles, brightness):
    data = bytearray(width * height * 3)
    total_pixels = max(1, width * height)
    value = max(0.0, min(1.0, brightness))

    i = 0
    for y in range(height):
        for x in range(width):
            index = strand_index(x, y, width, height, order)
            hue = ((index / total_pixels) * cycles + phase) % 1.0
            red, green, blue = colorsys.hsv_to_rgb(hue, 1.0, value)
            data[i] = int(red * 255)
            data[i + 1] = int(green * 255)
            data[i + 2] = int(blue * 255)
            i += 3

    return bytes(data)


def main():
    parser = argparse.ArgumentParser(
        description="Send a cyclic rainbow strand test to a BRIC tile receiver."
    )
    parser.add_argument("--ip", required=True, help="Raspberry Pi tile IP address")
    parser.add_argument("--port", type=int, default=4210)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--cycles", type=float, default=1.0)
    parser.add_argument(
        "--speed",
        type=float,
        default=0.25,
        help="Rainbow phase cycles per second",
    )
    parser.add_argument(
        "--brightness",
        type=float,
        default=1.0,
        help="0.0 to 1.0 sender-side brightness scale",
    )
    parser.add_argument(
        "--order",
        choices=("row-major", "serpentine", "column-major", "column-serpentine"),
        default="row-major",
        help="How to turn the matrix into a test strand",
    )
    parser.add_argument("--frames", type=int, default=0, help="0 means run forever")
    parser.add_argument("--duration", type=float, default=0.0, help="Seconds; 0 means ignore")
    args = parser.parse_args()

    if args.chunk_size <= 0 or args.chunk_size + HEADER_SIZE > 1400:
        raise SystemExit("--chunk-size must be 1..1372 for safe LAN UDP datagrams")
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("--width and --height must be positive")

    address = (args.ip, args.port)
    frame_interval = 0.0 if args.fps <= 0 else 1.0 / args.fps
    start_time = time.monotonic()
    frame_id = initial_frame_id()
    sent = 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while args.frames == 0 or sent < args.frames:
            now = time.monotonic()
            if args.duration > 0 and now - start_time >= args.duration:
                break

            phase = ((now - start_time) * args.speed) % 1.0
            frame = make_rainbow_frame(
                args.width,
                args.height,
                args.order,
                phase,
                args.cycles,
                args.brightness,
            )
            send_frame(sock, address, frame, frame_id, args.width, args.height, args.chunk_size)
            frame_id = (frame_id + 1) & 0xFFFFFFFF
            sent += 1

            if frame_interval > 0:
                elapsed = time.monotonic() - now
                time.sleep(max(0.0, frame_interval - elapsed))


if __name__ == "__main__":
    main()

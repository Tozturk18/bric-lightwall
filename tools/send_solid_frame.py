#!/usr/bin/env python3

import argparse
import math
import socket
import struct
import time


MAGIC = b"BRIC"
VERSION = 1
PACKET_TYPE_FRAME_CHUNK = 1
HEADER_SIZE = 28
HEADER = struct.Struct("!4sBBHIHHHHHHI")


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


def main():
    parser = argparse.ArgumentParser(description="Send solid BRIC RGB888 frames.")
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4210)
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--r", type=int, default=255)
    parser.add_argument("--g", type=int, default=0)
    parser.add_argument("--b", type=int, default=0)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--chunk-size", type=int, default=1024)
    parser.add_argument("--frames", type=int, default=0, help="0 means run forever")
    args = parser.parse_args()

    if args.chunk_size <= 0 or args.chunk_size + HEADER_SIZE > 1400:
        raise SystemExit("--chunk-size must be 1..1372 for safe LAN UDP datagrams")

    color = bytes((args.r & 0xFF, args.g & 0xFF, args.b & 0xFF))
    frame = color * (args.width * args.height)
    address = (args.ip, args.port)
    frame_id = 1
    frame_interval = 0.0 if args.fps <= 0 else 1.0 / args.fps
    sent = 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        while args.frames == 0 or sent < args.frames:
            start = time.monotonic()
            send_frame(
                sock, address, frame, frame_id, args.width, args.height, args.chunk_size
            )
            frame_id = (frame_id + 1) & 0xFFFFFFFF
            sent += 1
            if frame_interval > 0:
                elapsed = time.monotonic() - start
                time.sleep(max(0.0, frame_interval - elapsed))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import json
import math
import socket
import struct
import time


MAGIC = b"BRIC"
VERSION = 1
PACKET_TYPE_FRAME_CHUNK = 1
PACKET_TYPE_INFO_REQUEST = 5
PACKET_TYPE_INFO_RESPONSE = 6
HEADER_SIZE = 28
HEADER = struct.Struct("!4sBBHIHHHHHHI")


def initial_frame_id():
    frame_id = int(time.time() * 1000) & 0xFFFFFFFF
    return frame_id or 1


def build_header(
    frame_id,
    width,
    height,
    chunk_index,
    total_chunks,
    payload_size,
    packet_type=PACKET_TYPE_FRAME_CHUNK,
):
    return HEADER.pack(
        MAGIC,
        VERSION,
        packet_type,
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


def probe_receiver(sock, address, frame_id, width, height):
    request = build_header(
        frame_id,
        width,
        height,
        0,
        1,
        0,
        packet_type=PACKET_TYPE_INFO_REQUEST,
    )
    sock.sendto(request, address)
    while True:
        data, _sender = sock.recvfrom(8192)
        if len(data) < HEADER_SIZE:
            continue
        try:
            magic, version, packet_type, header_size, _frame_id, *_rest = HEADER.unpack(
                data[:HEADER_SIZE]
            )
        except struct.error:
            continue
        if (
            magic != MAGIC
            or version != VERSION
            or packet_type != PACKET_TYPE_INFO_RESPONSE
            or header_size > len(data)
        ):
            continue
        try:
            return json.loads(data[header_size:].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}


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
    parser.add_argument(
        "--probe-timeout",
        type=float,
        default=0.75,
        help="Seconds to wait for the receiver info probe before sending",
    )
    parser.add_argument(
        "--no-probe",
        dest="probe",
        action="store_false",
        help="Send frames without first verifying that a BRIC receiver answers",
    )
    parser.set_defaults(probe=True)
    args = parser.parse_args()

    if args.chunk_size <= 0 or args.chunk_size + HEADER_SIZE > 1400:
        raise SystemExit("--chunk-size must be 1..1372 for safe LAN UDP datagrams")

    color = bytes((args.r & 0xFF, args.g & 0xFF, args.b & 0xFF))
    frame = color * (args.width * args.height)
    address = (args.ip, args.port)
    frame_id = initial_frame_id()
    frame_interval = 0.0 if args.fps <= 0 else 1.0 / args.fps
    sent = 0

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        if args.probe:
            sock.settimeout(args.probe_timeout)
            try:
                info = probe_receiver(sock, address, frame_id, args.width, args.height)
            except socket.timeout as error:
                raise SystemExit(
                    f"no BRIC receiver answered at {args.ip}:{args.port}; "
                    "is bric-tile.service running and listening on UDP 4210?"
                ) from error
            frame_id = (frame_id + 1) & 0xFFFFFFFF or 1
            print(
                "Receiver OK: "
                f"mac={info.get('mac', '-')} "
                f"ip={info.get('ip', args.ip)} "
                f"display={info.get('wall_width', args.width)}x{info.get('wall_height', args.height)} "
                f"port={info.get('listen_port', args.port)}"
            )

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

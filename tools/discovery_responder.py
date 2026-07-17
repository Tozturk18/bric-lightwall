#!/usr/bin/env python3

import argparse
import json
import os
import socket


VERSION = "bric-tile-receiver-v0.1.0"


DEFAULTS = {
    "BRIC_TILE_NAME": "bric-tile",
    "BRIC_LISTEN_IP": "0.0.0.0",
    "BRIC_LISTEN_PORT": "4210",
    "BRIC_WALL_WIDTH": "64",
    "BRIC_WALL_HEIGHT": "64",
    "BRIC_PANEL_ROWS": "32",
    "BRIC_PANEL_COLS": "64",
    "BRIC_PANEL_CHAIN": "2",
    "BRIC_PANEL_PARALLEL": "1",
    "BRIC_BRIGHTNESS": "40",
    "BRIC_HARDWARE_MAPPING": "regular",
    "BRIC_PIXEL_MAPPING": "stacked-panel2-top-rot180",
    "BRIC_OUTPUT_ROTATION": "180",
    "BRIC_SLOWDOWN_GPIO": "4",
}


def parse_env(path):
    values = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as input_file:
            for raw_line in input_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("\"'")
    mac = values.get("BRIC_TILE_MAC", "").strip().lower()
    if not mac or mac == "auto":
        values["BRIC_TILE_MAC"] = read_text("/sys/class/net/eth0/address")
    return values


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as input_file:
            return input_file.readline().strip()
    except OSError:
        return ""


def int_value(values, key):
    try:
        return int(values.get(key, DEFAULTS.get(key, "0")))
    except ValueError:
        return int(DEFAULTS.get(key, "0"))


def local_ip_for_peer(peer_ip):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((peer_ip, 9))
            return sock.getsockname()[0]
    except OSError:
        return ""


def build_response(values, peer_ip):
    configured_ip = values.get("BRIC_LISTEN_IP", "0.0.0.0")
    route_ip = local_ip_for_peer(peer_ip)
    if configured_ip in ("", "0.0.0.0", "auto"):
        ip = route_ip or "0.0.0.0"
    else:
        ip = route_ip or configured_ip

    return {
        "type": "BRIC_TILE_RESPONSE",
        "hostname": values.get("BRIC_TILE_NAME", "bric-tile"),
        "mac": values.get("BRIC_TILE_MAC", ""),
        "ip": ip,
        "listen_port": int_value(values, "BRIC_LISTEN_PORT"),
        "wall_width": int_value(values, "BRIC_WALL_WIDTH"),
        "wall_height": int_value(values, "BRIC_WALL_HEIGHT"),
        "panel_rows": int_value(values, "BRIC_PANEL_ROWS"),
        "panel_cols": int_value(values, "BRIC_PANEL_COLS"),
        "panel_chain": int_value(values, "BRIC_PANEL_CHAIN"),
        "panel_parallel": int_value(values, "BRIC_PANEL_PARALLEL"),
        "brightness": int_value(values, "BRIC_BRIGHTNESS"),
        "hardware_mapping": values.get("BRIC_HARDWARE_MAPPING", "regular"),
        "pixel_mapping": values.get("BRIC_PIXEL_MAPPING", "stacked-panel2-top-rot180"),
        "output_rotation": int_value(values, "BRIC_OUTPUT_ROTATION"),
        "slowdown_gpio": int_value(values, "BRIC_SLOWDOWN_GPIO"),
        "version": VERSION,
    }


def main():
    parser = argparse.ArgumentParser(description="BRIC UDP discovery responder.")
    parser.add_argument("--config", default="/etc/bric-lightwall/tile.env")
    parser.add_argument("--port", type=int, default=4209)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", args.port))
        print(f"BRIC discovery responder listening on UDP {args.port}", flush=True)

        while True:
            data, address = sock.recvfrom(2048)
            if data.strip() != b"BRIC_DISCOVER":
                continue

            values = parse_env(args.config)
            response = build_response(values, address[0])
            sock.sendto(json.dumps(response, separators=(",", ":")).encode("utf-8"), address)


if __name__ == "__main__":
    main()

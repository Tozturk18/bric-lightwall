#!/usr/bin/env python3

import argparse
import json
import socket


def main():
    parser = argparse.ArgumentParser(description="Discover BRIC tile receivers.")
    parser.add_argument("--broadcast", default="255.255.255.255")
    parser.add_argument("--port", type=int, default=4209)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(args.timeout)
        sock.sendto(b"BRIC_DISCOVER", (args.broadcast, args.port))

        while True:
            try:
                data, address = sock.recvfrom(8192)
            except socket.timeout:
                break
            text = data.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text)
                print(json.dumps(parsed, indent=2, sort_keys=True))
            except json.JSONDecodeError:
                print(f"{address[0]}:{address[1]} {text}")


if __name__ == "__main__":
    main()


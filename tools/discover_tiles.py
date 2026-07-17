#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.net_interfaces import list_arp_entries, list_ipv4_interfaces
from common.tile_discovery import discover_tiles


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover BRIC tile receivers.")
    parser.add_argument(
        "--interface",
        action="append",
        dest="interfaces",
        default=[],
        help=(
            "Limit discovery to a local interface, e.g. en7 on macOS, eth0 on Linux, "
            "Ethernet on Windows, or an adapter IPv4 address. Repeatable."
        ),
    )
    parser.add_argument(
        "--subnet",
        default="",
        help="Optional subnet to actively probe, e.g. 10.42.0.0/24. Use 'auto' to probe local /24s.",
    )
    parser.add_argument(
        "--scan-auto-subnets",
        action="store_true",
        help="Actively probe bounded local subnets in addition to broadcast discovery.",
    )
    parser.add_argument(
        "--broadcast",
        action="append",
        default=[],
        help="Extra directed broadcast address to send to, e.g. 10.42.0.255. Repeatable.",
    )
    parser.add_argument("--port", type=int, default=4210, help="Tile receiver UDP port")
    parser.add_argument("--discovery-port", type=int, default=4209)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=256, help="Maximum hosts per active subnet scan")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument(
        "--show-arp",
        action="store_true",
        help="Print complete IPv4 ARP entries for the selected interface(s).",
    )
    parser.add_argument(
        "--no-arp-probe",
        action="store_true",
        help="Do not probe ARP-cache IPs such as link-local 169.254.x.x addresses.",
    )
    parser.add_argument(
        "--show-interfaces",
        action="store_true",
        help="Print local IPv4 interfaces before discovery.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interfaces and not list_ipv4_interfaces(args.interfaces):
        available = list_ipv4_interfaces()
        print(
            "No matching IPv4 interface found for "
            f"{', '.join(args.interfaces)}.",
            file=sys.stderr,
        )
        if available:
            names = ", ".join(f"{iface.name} ({iface.address})" for iface in available)
            print(f"Available IPv4 interfaces: {names}", file=sys.stderr)
        else:
            print("No non-loopback IPv4 interfaces were detected.", file=sys.stderr)
        return 2

    if args.show_interfaces:
        interfaces = [iface.as_dict() for iface in list_ipv4_interfaces(args.interfaces)]
        print(json.dumps({"interfaces": interfaces}, indent=2, sort_keys=True))
    if args.show_arp:
        entries = [entry.as_dict() for entry in list_arp_entries(args.interfaces)]
        print(json.dumps({"arp": entries}, indent=2, sort_keys=True))

    tiles = discover_tiles(
        subnet=args.subnet,
        receiver_port=args.port,
        discovery_port=args.discovery_port,
        timeout=args.timeout,
        limit=args.limit,
        interfaces=args.interfaces,
        scan_auto_subnets=args.scan_auto_subnets,
        broadcasts=args.broadcast,
        probe_arp_cache=not args.no_arp_probe,
    )

    if args.json:
        print(json.dumps([tile.as_dict() for tile in tiles], indent=2, sort_keys=True))
        return 0

    if not tiles:
        print("No BRIC tile receivers discovered.")
        return 1

    print(f"Discovered {len(tiles)} BRIC tile receiver(s):")
    for tile in tiles:
        iface = f" via {tile.interface}" if tile.interface else ""
        network = f" ({tile.network})" if tile.network else ""
        mac = tile.mac or "no-mac"
        host = f" {tile.hostname}" if tile.hostname else ""
        print(
            f"- {tile.ip}:{tile.listen_port}{iface}{network} "
            f"mac={mac}{host} size={tile.wall_width}x{tile.wall_height}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

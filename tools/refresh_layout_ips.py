#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.layout_refresh import refresh_layout_ips


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh wall_layout.json tile IPs by rediscovering receivers by MAC."
    )
    parser.add_argument("--layout", default="wall_layout.json")
    parser.add_argument("--interface", action="append", dest="interfaces", default=[])
    parser.add_argument("--subnet", default="", help="Optional subnet to probe, or 'auto'")
    parser.add_argument("--scan-auto-subnets", action="store_true")
    parser.add_argument("--port", type=int, default=4210, help="Tile receiver UDP port")
    parser.add_argument("--discovery-port", type=int, default=4209)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--limit", type=int, default=256)
    parser.add_argument("--check", action="store_true", help="Discover and report without writing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = refresh_layout_ips(
        args.layout,
        default_port=args.port,
        subnet=args.subnet,
        discovery_port=args.discovery_port,
        timeout=args.timeout,
        limit=args.limit,
        interfaces=args.interfaces,
        scan_auto_subnets=args.scan_auto_subnets,
        save=not args.check,
    )
    print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    if result.discovered_tiles == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from common.tile_discovery import TileInfo, discover_tiles
from common.tile_identity import normalize_mac, tile_key_from_mapping


@dataclass
class ResolvedWallLayout:
    tiles: List[Dict]
    cols: int = 1
    rows: int = 1
    origin: str = "top-left"
    unresolved: List[str] = field(default_factory=list)
    ambiguous: List[str] = field(default_factory=list)
    discovered_tiles: int = 0


def load_resolved_wall_layout(
    layout_path: str | Path,
    default_port: int = 4210,
    discovery_subnet: str = "",
    discovery_port: int = 4209,
    discovery_timeout: float = 0.35,
    scan_limit: int = 256,
    interfaces: Optional[Sequence[str]] = None,
    scan_auto_subnets: bool = False,
    resolve_by_mac: bool = True,
) -> ResolvedWallLayout:
    path = Path(layout_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    cols = int(data.get("cols") or 0) or 0
    rows = int(data.get("rows") or 0) or 0
    origin = data.get("origin") or "top-left"
    items = list(data.get("tiles") or [])

    discovered: List[TileInfo] = []
    if resolve_by_mac and any(normalize_mac(str(item.get("mac") or "")) for item in items):
        discovered = discover_tiles(
            subnet=discovery_subnet,
            receiver_port=default_port,
            discovery_port=discovery_port,
            timeout=discovery_timeout,
            limit=scan_limit,
            interfaces=interfaces,
            scan_auto_subnets=scan_auto_subnets,
        )

    discovered_by_mac: Dict[str, List[TileInfo]] = {}
    for tile in discovered:
        mac = normalize_mac(tile.mac)
        if mac:
            discovered_by_mac.setdefault(mac, []).append(tile)

    layout_mac_counts: Dict[str, int] = {}
    for item in items:
        mac = normalize_mac(str(item.get("mac") or ""))
        if mac:
            layout_mac_counts[mac] = layout_mac_counts.get(mac, 0) + 1

    tiles: List[Dict] = []
    unresolved: List[str] = []
    ambiguous: List[str] = []
    for item in items:
        mac = normalize_mac(str(item.get("mac") or ""))
        key = tile_key_from_mapping(item)
        if resolve_by_mac and mac and layout_mac_counts.get(mac, 0) > 1:
            _append_unique(ambiguous, mac)
            continue
        current = _unique_discovered_tile(mac, discovered_by_mac, ambiguous)
        if current is not None:
            ip = current.ip
        elif mac and resolve_by_mac:
            _append_unique(unresolved, mac)
            continue
        else:
            ip = str(item.get("ip") or item.get("last_ip") or "")
        if not ip:
            _append_unique(unresolved, mac or key or str(item.get("tile_number") or "unknown"))
            continue

        listen_port = int(
            (current.listen_port if current is not None else 0)
            or item.get("listen_port")
            or default_port
        )
        grid_x = int(item.get("grid_x", 0))
        grid_y = int(item.get("grid_y", 0))
        tiles.append(
            {
                "key": key or tile_key_from_mapping({"mac": mac, "ip": ip}),
                "mac": mac,
                "ip": ip,
                "last_ip": ip,
                "grid_x": grid_x,
                "grid_y": grid_y,
                "port": listen_port,
                "listen_port": listen_port,
                "tile_number": int(item.get("tile_number") or (grid_y * max(1, cols) + grid_x + 1)),
            }
        )

    if tiles and cols <= 0:
        cols = max(tile["grid_x"] for tile in tiles) + 1
    if tiles and rows <= 0:
        rows = max(tile["grid_y"] for tile in tiles) + 1

    return ResolvedWallLayout(
        tiles=tiles,
        cols=cols or 1,
        rows=rows or 1,
        origin=origin,
        unresolved=unresolved,
        ambiguous=ambiguous,
        discovered_tiles=len(discovered),
    )


def _unique_discovered_tile(
    mac: str,
    discovered_by_mac: Dict[str, List[TileInfo]],
    ambiguous: List[str],
) -> Optional[TileInfo]:
    if not mac:
        return None
    matches = discovered_by_mac.get(mac) or []
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        _append_unique(ambiguous, mac)
    return None


def _append_unique(values: List[str], value: str) -> None:
    if value and value not in values:
        values.append(value)

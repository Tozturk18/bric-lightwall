#!/usr/bin/env python3

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from common.tile_discovery import TileInfo, discover_tiles
from common.tile_identity import normalize_mac


@dataclass
class LayoutRefreshResult:
    path: str
    changed: bool = False
    discovered_tiles: int = 0
    updated_tiles: int = 0
    missing_macs: List[str] = field(default_factory=list)
    ambiguous_macs: List[str] = field(default_factory=list)
    skipped_tiles: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict:
        return {
            "path": self.path,
            "changed": self.changed,
            "discovered_tiles": self.discovered_tiles,
            "updated_tiles": self.updated_tiles,
            "missing_macs": self.missing_macs,
            "ambiguous_macs": self.ambiguous_macs,
            "skipped_tiles": self.skipped_tiles,
        }


def refresh_layout_ips(
    layout_path: str | Path,
    default_port: int = 4210,
    subnet: str = "",
    discovery_port: int = 4209,
    timeout: float = 0.5,
    limit: int = 256,
    interfaces: Optional[Sequence[str]] = None,
    scan_auto_subnets: bool = False,
    save: bool = True,
) -> LayoutRefreshResult:
    path = Path(layout_path)
    result = LayoutRefreshResult(path=str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    layout_tiles = data.get("tiles") or []

    discovered = discover_tiles(
        subnet=subnet,
        receiver_port=default_port,
        discovery_port=discovery_port,
        timeout=timeout,
        limit=limit,
        interfaces=interfaces,
        scan_auto_subnets=scan_auto_subnets,
    )
    result.discovered_tiles = len(discovered)

    by_mac: Dict[str, List[TileInfo]] = {}
    for tile in discovered:
        mac = normalize_mac(tile.mac)
        if mac:
            by_mac.setdefault(mac, []).append(tile)

    layout_mac_counts: Dict[str, int] = {}
    for item in layout_tiles:
        mac = normalize_mac(str(item.get("mac") or ""))
        if mac:
            layout_mac_counts[mac] = layout_mac_counts.get(mac, 0) + 1

    for item in layout_tiles:
        label = str(item.get("tile_number") or item.get("ip") or "unknown")
        mac = normalize_mac(str(item.get("mac") or ""))
        if not mac:
            result.skipped_tiles.append(label)
            continue
        if layout_mac_counts.get(mac, 0) > 1:
            if mac not in result.ambiguous_macs:
                result.ambiguous_macs.append(mac)
            result.skipped_tiles.append(label)
            continue
        matches = by_mac.get(mac) or []
        if not matches:
            result.missing_macs.append(mac)
            continue
        if len(matches) > 1:
            if mac not in result.ambiguous_macs:
                result.ambiguous_macs.append(mac)
            result.skipped_tiles.append(label)
            continue

        tile = matches[0]
        changed = False
        updates = {
            "last_ip": tile.ip,
            "listen_port": tile.listen_port or default_port,
            "status": tile.status,
            "last_seen": tile.last_seen or time.time(),
        }
        if "ip" in item:
            del item["ip"]
            changed = True
        for key, value in updates.items():
            if item.get(key) != value:
                item[key] = value
                changed = True
        if changed:
            result.updated_tiles += 1
            result.changed = True

    if save and result.changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return result

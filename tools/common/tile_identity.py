#!/usr/bin/env python3

from __future__ import annotations

from typing import Mapping


def normalize_mac(value: str) -> str:
    clean = str(value or "").strip().lower().replace("-", ":")
    if ":" not in clean and len(clean) == 12:
        clean = ":".join(clean[index : index + 2] for index in range(0, 12, 2))
    parts = [part.zfill(2) for part in clean.split(":") if part]
    if len(parts) != 6 or any(len(part) != 2 for part in parts):
        return ""
    return ":".join(parts)


def tile_key_from_values(mac: str = "", ip: str = "") -> str:
    mac_key = normalize_mac(mac)
    if mac_key:
        return mac_key
    ip_value = str(ip or "").strip()
    return f"ip:{ip_value}" if ip_value else ""


def tile_key_from_mapping(item: Mapping) -> str:
    return tile_key_from_values(
        mac=str(item.get("mac") or ""),
        ip=str(item.get("ip") or item.get("last_ip") or ""),
    )


def tile_key_from_tile(tile) -> str:
    return tile_key_from_values(
        mac=str(getattr(tile, "mac", "") or ""),
        ip=str(getattr(tile, "ip", "") or ""),
    )

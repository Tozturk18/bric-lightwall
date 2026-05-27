#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
import json
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


DISCOVERY_MAGIC = b"BRIC_DISCOVER"
DISCOVERY_PORT = 4209
BRIC_INFO_HEADER = struct.Struct("!4sBBHIHHHHHHI")


@dataclass
class TileInfo:
    ip: str
    listen_port: int = 4210
    hostname: str = ""
    mac: str = ""
    wall_width: int = 64
    wall_height: int = 64
    status: str = "discovered"
    last_seen: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict, fallback_ip: str, fallback_port: int = 4210) -> "TileInfo":
        return cls(
            ip=str(data.get("ip") or fallback_ip),
            listen_port=int(data.get("listen_port") or fallback_port),
            hostname=str(data.get("hostname") or ""),
            mac=str(data.get("mac") or ""),
            wall_width=int(data.get("wall_width") or 64),
            wall_height=int(data.get("wall_height") or 64),
            status=str(data.get("status") or "discovered"),
            last_seen=time.time(),
        )

    def as_dict(self) -> Dict:
        return {
            "ip": self.ip,
            "listen_port": self.listen_port,
            "hostname": self.hostname,
            "mac": self.mac,
            "wall_width": self.wall_width,
            "wall_height": self.wall_height,
            "status": self.status,
            "last_seen": self.last_seen,
        }


def discover_tiles(
    subnet: Optional[str] = None,
    receiver_port: int = 4210,
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.25,
    limit: int = 256,
) -> List[TileInfo]:
    tiles: Dict[str, TileInfo] = {}

    for tile in discover_by_broadcast(discovery_port=discovery_port, timeout=timeout):
        tiles[tile.ip] = tile

    if subnet:
        hosts = [host for host in iter_subnet_hosts(subnet, limit=limit) if host not in tiles]
        with ThreadPoolExecutor(max_workers=min(64, max(1, len(hosts)))) as executor:
            futures = {
                executor.submit(probe_bric_info, host, receiver_port, timeout): host
                for host in hosts
            }
            for future in as_completed(futures):
                tile = future.result()
                if tile is not None:
                    tiles[tile.ip] = tile

    return sorted(tiles.values(), key=lambda tile: ipaddress.ip_address(tile.ip))


def discover_by_broadcast(
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.5,
) -> List[TileInfo]:
    found: Dict[str, TileInfo] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(timeout)
        for address in ("255.255.255.255", "127.0.0.1"):
            try:
                sock.sendto(DISCOVERY_MAGIC, (address, discovery_port))
            except OSError:
                continue

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, sender = sock.recvfrom(8192)
            except socket.timeout:
                break
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            tile = TileInfo.from_dict(parsed, fallback_ip=sender[0])
            found[tile.ip] = tile

    return list(found.values())


def probe_bric_info(host: str, port: int = 4210, timeout: float = 0.25) -> Optional[TileInfo]:
    request = BRIC_INFO_HEADER.pack(
        b"BRIC",
        1,
        5,
        BRIC_INFO_HEADER.size,
        1,
        0,
        0,
        0,
        1,
        0,
        0,
        0,
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(request, (host, port))
            data, sender = sock.recvfrom(8192)
        except OSError:
            return None

    if len(data) < BRIC_INFO_HEADER.size:
        return None

    try:
        magic, _version, packet_type, header_size, _frame_id, *_rest = BRIC_INFO_HEADER.unpack(
            data[: BRIC_INFO_HEADER.size]
        )
    except struct.error:
        return None
    if magic != b"BRIC" or packet_type != 6 or header_size > len(data):
        return None

    try:
        parsed = json.loads(data[header_size:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return TileInfo.from_dict(parsed, fallback_ip=sender[0], fallback_port=port)


def iter_subnet_hosts(subnet: str, limit: int = 256) -> Iterable[str]:
    network = ipaddress.ip_network(subnet, strict=False)
    for index, host in enumerate(network.hosts()):
        if index >= limit:
            break
        yield str(host)

#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
import json
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from common.net_interfaces import (
    ArpEntry,
    IPv4Interface,
    annotate_interface,
    auto_scan_subnets,
    directed_broadcasts,
    list_arp_entries,
    list_ipv4_interfaces,
)
from common.tile_identity import tile_key_from_tile


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
    interface: str = ""
    network: str = ""
    response_ip: str = ""
    advertised_ip: str = ""

    @classmethod
    def from_dict(
        cls,
        data: Dict,
        fallback_ip: str,
        fallback_port: int = 4210,
        interfaces: Sequence[IPv4Interface] = (),
        prefer_fallback_ip: bool = False,
        response_ip: str = "",
    ) -> "TileInfo":
        advertised_ip = str(data.get("ip") or "").strip()
        ip = "" if prefer_fallback_ip else advertised_ip
        if not ip or ip == "0.0.0.0":
            ip = fallback_ip
        interface, network = annotate_interface(ip, interfaces)
        return cls(
            ip=ip,
            listen_port=int(data.get("listen_port") or fallback_port),
            hostname=str(data.get("hostname") or ""),
            mac=str(data.get("mac") or ""),
            wall_width=int(data.get("wall_width") or 64),
            wall_height=int(data.get("wall_height") or 64),
            status=str(data.get("status") or "discovered"),
            last_seen=time.time(),
            interface=interface,
            network=network,
            response_ip=response_ip or fallback_ip,
            advertised_ip=advertised_ip,
        )

    def as_dict(self) -> Dict:
        return {
            "key": tile_key_from_tile(self),
            "ip": self.ip,
            "listen_port": self.listen_port,
            "hostname": self.hostname,
            "mac": self.mac,
            "wall_width": self.wall_width,
            "wall_height": self.wall_height,
            "status": self.status,
            "last_seen": self.last_seen,
            "interface": self.interface,
            "network": self.network,
            "response_ip": self.response_ip,
            "advertised_ip": self.advertised_ip,
        }


def discover_tiles(
    subnet: Optional[str] = None,
    receiver_port: int = 4210,
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.25,
    limit: int = 256,
    interfaces: Optional[Sequence[str]] = None,
    scan_auto_subnets: bool = False,
    broadcasts: Optional[Sequence[str]] = None,
    probe_arp_cache: bool = True,
) -> List[TileInfo]:
    tiles: Dict[str, TileInfo] = {}
    restrict_to_named_interfaces = bool(interfaces)
    local_interfaces = list_ipv4_interfaces(names=interfaces)

    for tile in discover_by_broadcast(
        discovery_port=discovery_port,
        timeout=timeout,
        interfaces=local_interfaces,
        broadcasts=broadcasts,
        include_global_broadcast=not restrict_to_named_interfaces,
    ):
        add_tile(tiles, tile)

    scan_subnets: List[str] = []
    if subnet:
        if subnet.lower() == "auto":
            scan_auto_subnets = True
        else:
            scan_subnets.append(subnet)
    if scan_auto_subnets:
        scan_subnets.extend(auto_scan_subnets(local_interfaces, limit_hosts=limit))

    for scan_subnet in _dedupe(scan_subnets):
        hosts = [
            host
            for host in iter_subnet_hosts(scan_subnet, limit=limit)
            if host not in tiles
        ]
        with ThreadPoolExecutor(max_workers=min(64, max(1, len(hosts)))) as executor:
            futures = {
                executor.submit(
                    probe_bric_info,
                    host,
                    receiver_port,
                    timeout,
                    local_interfaces,
                    True,
                ): host
                for host in hosts
            }
            for future in as_completed(futures):
                tile = future.result()
                if tile is not None:
                    tile.interface, tile.network = annotate_interface(tile.ip, local_interfaces)
                    add_tile(tiles, tile)

    if probe_arp_cache:
        entries = list_arp_entries(names=interfaces)
        for tile in discover_by_arp_entries(
            entries,
            receiver_port=receiver_port,
            discovery_port=discovery_port,
            timeout=timeout,
            interfaces=local_interfaces,
        ):
            add_tile(tiles, tile)

    return sorted(tiles.values(), key=lambda tile: ipaddress.ip_address(tile.ip))


def discover_by_broadcast(
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.5,
    interfaces: Optional[Sequence[IPv4Interface]] = None,
    broadcasts: Optional[Sequence[str]] = None,
    include_global_broadcast: bool = True,
) -> List[TileInfo]:
    found: Dict[str, TileInfo] = {}
    local_interfaces = list(interfaces) if interfaces is not None else list_ipv4_interfaces()
    fallback_targets = ["127.0.0.1"]
    if include_global_broadcast:
        fallback_targets.insert(0, "255.255.255.255")
    targets = _dedupe(
        [
            *(broadcasts or ()),
            *directed_broadcasts(local_interfaces),
            *fallback_targets,
        ]
    )
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # On Windows, disable UDP connection-reset errors caused by ICMP
        # unreachable responses. This prevents recvfrom from raising
        # WSAECONNRESET (ConnectionResetError).
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except OSError:
                pass
        sock.settimeout(timeout)
        for address in targets:
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
            except OSError:
                # On Windows a UDP recvfrom can raise WSAECONNRESET (connection reset
                # by remote host) when an ICMP unreachable is received. Ignore
                # these and continue collecting other responses.
                continue
            try:
                parsed = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            tile = TileInfo.from_dict(parsed, fallback_ip=sender[0], interfaces=local_interfaces)
            add_tile(found, tile)

    return list(found.values())


def discover_by_arp_entries(
    entries: Sequence[ArpEntry],
    receiver_port: int = 4210,
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.25,
    interfaces: Optional[Sequence[IPv4Interface]] = None,
) -> List[TileInfo]:
    found: Dict[str, TileInfo] = {}
    local_addresses = {iface.address for iface in interfaces or []}
    for entry in entries:
        if entry.ip in local_addresses or entry.mac == "ff:ff:ff:ff:ff:ff":
            continue
        tile = probe_discovery_responder(
            entry.ip,
            discovery_port=discovery_port,
            timeout=timeout,
            interfaces=interfaces,
        )
        if tile is None:
            tile = probe_bric_info(
                entry.ip,
                port=receiver_port,
                timeout=timeout,
                interfaces=interfaces,
                prefer_host_ip=True,
            )
        if tile is not None:
            tile.interface = entry.interface
            if tile.ip.startswith("169.254."):
                tile.network = "169.254.0.0/16"
            add_tile(found, tile)
    return list(found.values())


def probe_discovery_responder(
    host: str,
    discovery_port: int = DISCOVERY_PORT,
    timeout: float = 0.25,
    interfaces: Optional[Sequence[IPv4Interface]] = None,
) -> Optional[TileInfo]:
    local_interfaces = list(interfaces) if interfaces is not None else list_ipv4_interfaces()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except OSError:
                pass
        try:
            sock.sendto(DISCOVERY_MAGIC, (host, discovery_port))
            data, sender = sock.recvfrom(8192)
        except OSError:
            return None

    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return TileInfo.from_dict(
        parsed,
        fallback_ip=host,
        interfaces=local_interfaces,
        prefer_fallback_ip=True,
        response_ip=sender[0],
    )


def probe_bric_info(
    host: str,
    port: int = 4210,
    timeout: float = 0.25,
    interfaces: Optional[Sequence[IPv4Interface]] = None,
    prefer_host_ip: bool = False,
) -> Optional[TileInfo]:
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
        # See note above: disable Windows UDP connection-reset behavior.
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except OSError:
                pass
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
    return TileInfo.from_dict(
        parsed,
        fallback_ip=host if prefer_host_ip else sender[0],
        fallback_port=port,
        interfaces=interfaces or (),
        prefer_fallback_ip=prefer_host_ip,
        response_ip=sender[0],
    )


def iter_subnet_hosts(subnet: str, limit: int = 256) -> Iterable[str]:
    network = ipaddress.ip_network(subnet, strict=False)
    for index, host in enumerate(network.hosts()):
        if index >= limit:
            break
        yield str(host)


def _dedupe(values: Iterable[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for value in values:
        clean = str(value or "").strip()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
    return result


def add_tile(tiles: Dict[str, TileInfo], tile: TileInfo) -> None:
    key = tile_key_from_tile(tile) or tile.ip
    tiles[key] = tile

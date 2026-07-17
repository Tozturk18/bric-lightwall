#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence


@dataclass(frozen=True)
class IPv4Interface:
    name: str
    address: str
    netmask: str
    network: str
    broadcast: str
    is_loopback: bool = False
    is_point_to_point: bool = False

    def contains(self, ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip) in ipaddress.ip_network(self.network, strict=False)
        except ValueError:
            return False

    def scan_network(self, max_prefixlen: int = 24) -> str:
        """Return a bounded subnet suitable for active LAN probing.

        Some systems report broad networks such as 169.254.0.0/16. Scanning
        that entire range would be slow and noisy, so for active probes we cap
        to the local /24 containing this interface address.
        """

        iface = ipaddress.ip_interface(f"{self.address}/{self.netmask}")
        prefixlen = max(iface.network.prefixlen, max_prefixlen)
        if prefixlen > 30:
            prefixlen = iface.network.prefixlen
        return str(ipaddress.ip_interface(f"{self.address}/{prefixlen}").network)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "address": self.address,
            "netmask": self.netmask,
            "network": self.network,
            "broadcast": self.broadcast,
            "is_loopback": self.is_loopback,
            "is_point_to_point": self.is_point_to_point,
        }


@dataclass(frozen=True)
class ArpEntry:
    ip: str
    mac: str
    interface: str

    def as_dict(self) -> dict:
        return {
            "ip": self.ip,
            "mac": self.mac,
            "interface": self.interface,
        }


def list_ipv4_interfaces(
    names: Optional[Sequence[str]] = None,
    include_loopback: bool = False,
) -> List[IPv4Interface]:
    wanted = {name for name in names or [] if name}
    interfaces = _list_with_ip_command() or _list_with_ifconfig()
    result: List[IPv4Interface] = []
    seen = set()
    for iface in interfaces:
        if wanted and iface.name not in wanted:
            continue
        if iface.is_loopback and not include_loopback:
            continue
        key = (iface.name, iface.address)
        if key in seen:
            continue
        seen.add(key)
        result.append(iface)
    return result


def list_arp_entries(names: Optional[Sequence[str]] = None) -> List[ArpEntry]:
    wanted = {name for name in names or [] if name}
    arp_path = shutil.which("arp")
    if not arp_path:
        return []
    command = [arp_path, "-an"]
    if len(wanted) == 1:
        command.extend(["-i", next(iter(wanted))])
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    entries: List[ArpEntry] = []
    seen = set()
    for line in result.stdout.splitlines():
        match = re.search(
            r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:]{11,17})\s+on\s+(?P<iface>\S+)",
            line,
        )
        if not match:
            continue
        iface = match.group("iface")
        if wanted and iface not in wanted:
            continue
        mac = match.group("mac").lower()
        ip = match.group("ip")
        key = (ip, mac, iface)
        if key in seen:
            continue
        seen.add(key)
        entries.append(ArpEntry(ip=ip, mac=mac, interface=iface))
    return entries


def directed_broadcasts(interfaces: Iterable[IPv4Interface]) -> List[str]:
    broadcasts: List[str] = []
    seen = set()
    for iface in interfaces:
        if iface.is_point_to_point:
            continue
        target = iface.broadcast
        if not target:
            try:
                network = ipaddress.ip_network(iface.network, strict=False)
                if network.num_addresses <= 2:
                    continue
                target = str(network.broadcast_address)
            except ValueError:
                continue
        if target not in seen:
            seen.add(target)
            broadcasts.append(target)
    return broadcasts


def auto_scan_subnets(interfaces: Iterable[IPv4Interface], limit_hosts: int = 256) -> List[str]:
    subnets: List[str] = []
    seen = set()
    for iface in interfaces:
        if iface.is_point_to_point:
            continue
        try:
            network = ipaddress.ip_network(iface.network, strict=False)
        except ValueError:
            continue
        if network.num_addresses <= 2:
            continue
        subnet = str(network)
        if max(0, network.num_addresses - 2) > limit_hosts:
            subnet = iface.scan_network()
        if subnet not in seen:
            seen.add(subnet)
            subnets.append(subnet)
    return subnets


def annotate_interface(ip: str, interfaces: Iterable[IPv4Interface]) -> tuple[str, str]:
    for iface in interfaces:
        if iface.contains(ip):
            return iface.name, iface.network
    return "", ""


def _list_with_ip_command() -> List[IPv4Interface]:
    ip_path = shutil.which("ip")
    if not ip_path:
        return []
    try:
        result = subprocess.run(
            [ip_path, "-j", "-4", "addr", "show"],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
        return []

    interfaces: List[IPv4Interface] = []
    for item in data:
        name = str(item.get("ifname") or "")
        flags = set(item.get("flags") or [])
        if not name or "UP" not in flags:
            continue
        is_loopback = "LOOPBACK" in flags
        is_point_to_point = "POINTOPOINT" in flags
        for addr in item.get("addr_info") or []:
            if addr.get("family") != "inet" or not addr.get("local"):
                continue
            local = str(addr["local"])
            prefixlen = int(addr.get("prefixlen") or 32)
            try:
                iface = ipaddress.ip_interface(f"{local}/{prefixlen}")
            except ValueError:
                continue
            broadcast = str(addr.get("broadcast") or iface.network.broadcast_address)
            interfaces.append(
                IPv4Interface(
                    name=name,
                    address=local,
                    netmask=str(iface.netmask),
                    network=str(iface.network),
                    broadcast=broadcast,
                    is_loopback=is_loopback,
                    is_point_to_point=is_point_to_point,
                )
            )
    return interfaces


def _list_with_ifconfig() -> List[IPv4Interface]:
    ifconfig_path = shutil.which("ifconfig")
    if not ifconfig_path:
        return []
    try:
        result = subprocess.run(
            [ifconfig_path],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    interfaces: List[IPv4Interface] = []
    current_name = ""
    current_flags = ""
    current_active = True
    for raw_line in result.stdout.splitlines():
        header = re.match(r"^([A-Za-z0-9_.:-]+):\s+flags=.*?<([^>]*)>", raw_line)
        if header:
            current_name = header.group(1)
            current_flags = header.group(2)
            current_active = "UP" in current_flags
            continue

        stripped = raw_line.strip()
        if stripped.startswith("status:"):
            current_active = "active" in stripped or current_active
            continue
        if not current_name or not current_active or not stripped.startswith("inet "):
            continue

        parts = stripped.split()
        try:
            address = parts[parts.index("inet") + 1]
        except (ValueError, IndexError):
            continue
        netmask = _value_after(parts, "netmask") or "255.255.255.255"
        broadcast = _value_after(parts, "broadcast")
        try:
            dotted_netmask = _normalize_netmask(netmask)
            iface = ipaddress.ip_interface(f"{address}/{dotted_netmask}")
        except ValueError:
            continue
        if not broadcast:
            broadcast = str(iface.network.broadcast_address)
        interfaces.append(
            IPv4Interface(
                name=current_name,
                address=address,
                netmask=str(iface.netmask),
                network=str(iface.network),
                broadcast=broadcast,
                is_loopback="LOOPBACK" in current_flags,
                is_point_to_point="POINTOPOINT" in current_flags,
            )
        )
    return interfaces


def _value_after(parts: Sequence[str], key: str) -> str:
    try:
        return parts[parts.index(key) + 1]
    except (ValueError, IndexError):
        return ""


def _normalize_netmask(value: str) -> str:
    if value.startswith("0x"):
        raw = int(value, 16)
        return str(ipaddress.IPv4Address(raw))
    return str(ipaddress.IPv4Address(value))

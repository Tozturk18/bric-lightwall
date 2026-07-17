#!/usr/bin/env python3

from __future__ import annotations

import ipaddress
import json
import os
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
    interfaces = _list_for_platform()
    result: List[IPv4Interface] = []
    seen = set()
    for iface in interfaces:
        if wanted and not _interface_matches(iface, wanted):
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
    interfaces = _list_for_platform()
    arp_path = shutil.which("arp")
    if not arp_path:
        return []
    if os.name == "nt":
        command = [arp_path, "-a"]
    else:
        command = [arp_path, "-an"]
    if os.name != "nt" and len(wanted) == 1:
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

    if os.name == "nt":
        entries = _parse_windows_arp_output(result.stdout, interfaces)
    else:
        entries = _parse_unix_arp_output(result.stdout)

    if not wanted:
        return entries
    return [
        entry
        for entry in entries
        if _arp_entry_matches(entry, wanted, interfaces)
    ]


def _parse_unix_arp_output(output: str) -> List[ArpEntry]:
    entries: List[ArpEntry] = []
    seen = set()
    for line in output.splitlines():
        match = re.search(
            r"\((?P<ip>\d+\.\d+\.\d+\.\d+)\)\s+at\s+(?P<mac>[0-9a-fA-F:]{11,17})\s+on\s+(?P<iface>\S+)",
            line,
        )
        if not match:
            continue
        iface = match.group("iface")
        mac = match.group("mac").lower()
        ip = match.group("ip")
        _append_arp_entry(entries, seen, ip, mac, iface)
    return entries


def _parse_windows_arp_output(
    output: str,
    interfaces: Sequence[IPv4Interface],
) -> List[ArpEntry]:
    entries: List[ArpEntry] = []
    seen = set()
    address_to_name = {iface.address: iface.name for iface in interfaces}
    current_interface = ""
    for line in output.splitlines():
        header = re.search(
            r"^\s*Interface:\s+(?P<ip>\d+\.\d+\.\d+\.\d+)\s+---\s+0x[0-9a-fA-F]+",
            line,
        )
        if header:
            interface_ip = header.group("ip")
            current_interface = address_to_name.get(interface_ip, interface_ip)
            continue

        match = re.search(
            r"^\s*(?P<ip>\d+\.\d+\.\d+\.\d+)\s+"
            r"(?P<mac>(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2})\s+\S+",
            line,
        )
        if not match:
            continue
        mac = match.group("mac").replace("-", ":").lower()
        _append_arp_entry(entries, seen, match.group("ip"), mac, current_interface)
    return entries


def _append_arp_entry(
    entries: List[ArpEntry],
    seen: set,
    ip: str,
    mac: str,
    iface: str,
) -> None:
    mac = mac.lower()
    if mac == "ff:ff:ff:ff:ff:ff":
        return
    if not _is_usable_arp_probe_ip(ip):
        return
    key = (ip, mac, iface)
    if key in seen:
        return
    seen.add(key)
    entries.append(ArpEntry(ip=ip, mac=mac, interface=iface))


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


def _is_usable_arp_probe_ip(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if address.version != 4:
        return False
    return not (
        address.is_loopback
        or address.is_multicast
        or address.is_unspecified
        or ip == "255.255.255.255"
    )


def _list_for_platform() -> List[IPv4Interface]:
    if os.name == "nt":
        return _list_with_ipconfig() or _list_with_ip_command() or _list_with_ifconfig()
    return _list_with_ip_command() or _list_with_ifconfig() or _list_with_ipconfig()


def _interface_matches(iface: IPv4Interface, wanted: Iterable[str]) -> bool:
    name = iface.name.lower()
    address = iface.address.lower()
    network = iface.network.lower()
    for value in wanted:
        target = str(value or "").strip().lower()
        if not target:
            continue
        if target in {name, address, network}:
            return True
        if target in name:
            return True
    return False


def _arp_entry_matches(
    entry: ArpEntry,
    wanted: Iterable[str],
    interfaces: Sequence[IPv4Interface],
) -> bool:
    entry_interface = entry.interface.lower()
    for value in wanted:
        target = str(value or "").strip().lower()
        if not target:
            continue
        if target == entry_interface or target in entry_interface:
            return True
    for iface in interfaces:
        if _interface_matches(iface, wanted) and (
            entry.interface == iface.name or iface.contains(entry.ip)
        ):
            return True
    return False


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


def _list_with_ipconfig() -> List[IPv4Interface]:
    ipconfig_path = shutil.which("ipconfig")
    if not ipconfig_path:
        return []
    try:
        result = subprocess.run(
            [ipconfig_path],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return _parse_ipconfig_output(result.stdout)


def _parse_ipconfig_output(output: str) -> List[IPv4Interface]:
    interfaces: List[IPv4Interface] = []
    current_name = ""
    current_ipv4 = ""
    current_netmask = ""
    current_disconnected = False

    def flush_current() -> None:
        nonlocal current_name, current_ipv4, current_netmask, current_disconnected
        if current_name and current_ipv4 and current_netmask and not current_disconnected:
            try:
                iface = ipaddress.ip_interface(f"{current_ipv4}/{current_netmask}")
            except ValueError:
                pass
            else:
                interfaces.append(
                    IPv4Interface(
                        name=current_name,
                        address=current_ipv4,
                        netmask=str(iface.netmask),
                        network=str(iface.network),
                        broadcast=str(iface.network.broadcast_address),
                        is_loopback="loopback" in current_name.lower(),
                        is_point_to_point=False,
                    )
                )
        current_name = ""
        current_ipv4 = ""
        current_netmask = ""
        current_disconnected = False

    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        header = re.match(r"^[^\s].*\badapter\s+(?P<name>.+):$", stripped, re.IGNORECASE)
        if header:
            flush_current()
            current_name = header.group("name").strip()
            continue

        if not current_name or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.lower()
        value = value.strip()
        if "media state" in key and "disconnected" in value.lower():
            current_disconnected = True
        elif "ipv4 address" in key:
            current_ipv4 = _clean_windows_ipv4(value)
        elif "subnet mask" in key:
            current_netmask = _clean_windows_ipv4(value)

    flush_current()
    return interfaces


def _clean_windows_ipv4(value: str) -> str:
    match = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", value)
    return match.group(0) if match else ""


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

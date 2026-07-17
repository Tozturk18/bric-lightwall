#!/usr/bin/env bash
set -euo pipefail

INTERFACE="eth0"
CONNECTION_NAME="bric-eth0-linklocal"
REMOVE_STATIC_CONNECTION="bric-eth0-static"

usage() {
  cat <<'USAGE'
Configure a Raspberry Pi Ethernet interface for IPv4 link-local addressing.

This is the no-DHCP/no-static Ethernet mode. The Pi will choose a 169.254.x.x
address on eth0, and the sender tools will discover the tile by its Ethernet
MAC address.

Examples:
  sudo scripts/configure_linklocal_ethernet.sh
  sudo scripts/configure_linklocal_ethernet.sh --interface eth0

Options:
  --interface NAME     Ethernet interface to configure (default: eth0)
  --connection NAME    NetworkManager connection name
                       (default: bric-eth0-linklocal)
  --keep-static        Do not remove the old bric-eth0-static connection
  -h, --help           Show this help text
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interface)
      INTERFACE="${2:?missing value for --interface}"
      shift 2
      ;;
    --connection)
      CONNECTION_NAME="${2:?missing value for --connection}"
      shift 2
      ;;
    --keep-static)
      REMOVE_STATIC_CONNECTION=""
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo." >&2
  exit 1
fi

if ! ip link show "${INTERFACE}" >/dev/null 2>&1; then
  echo "Interface ${INTERFACE} was not found." >&2
  exit 1
fi

show_result() {
  echo
  echo "Current IPv4 state for ${INTERFACE}:"
  ip -4 addr show dev "${INTERFACE}" || true
  echo
  echo "Expected result: inet 169.254.x.x/16 on ${INTERFACE}."
}

if command -v nmcli >/dev/null 2>&1 && nmcli general status >/dev/null 2>&1; then
  if [[ -n "${REMOVE_STATIC_CONNECTION}" ]] \
    && nmcli -t -f NAME connection show | grep -Fxq "${REMOVE_STATIC_CONNECTION}"; then
    nmcli connection down "${REMOVE_STATIC_CONNECTION}" >/dev/null 2>&1 || true
    nmcli connection delete "${REMOVE_STATIC_CONNECTION}"
  fi

  if ! nmcli -t -f NAME connection show | grep -Fxq "${CONNECTION_NAME}"; then
    nmcli connection add \
      type ethernet \
      ifname "${INTERFACE}" \
      con-name "${CONNECTION_NAME}" \
      autoconnect yes
  fi

  nmcli connection modify "${CONNECTION_NAME}" \
    connection.interface-name "${INTERFACE}" \
    connection.autoconnect yes \
    ipv4.method link-local \
    ipv4.never-default yes \
    ipv4.ignore-auto-dns yes \
    ipv6.method disabled

  ip link set "${INTERFACE}" up
  nmcli connection up "${CONNECTION_NAME}"
  echo "Configured ${INTERFACE} for IPv4 link-local with NetworkManager."
  show_result
  exit 0
fi

if command -v systemctl >/dev/null 2>&1 && command -v networkctl >/dev/null 2>&1; then
  network_file="/etc/systemd/network/10-bric-${INTERFACE}.network"
  {
    printf '[Match]\n'
    printf 'Name=%s\n\n' "${INTERFACE}"
    printf '[Network]\n'
    printf 'DHCP=no\n'
    printf 'LinkLocalAddressing=ipv4\n'
    printf 'IPv6AcceptRA=no\n'
  } > "${network_file}"

  ip link set "${INTERFACE}" up
  systemctl enable --now systemd-networkd
  networkctl reload 2>/dev/null || systemctl restart systemd-networkd
  networkctl reconfigure "${INTERFACE}" 2>/dev/null || true

  echo "Wrote ${network_file} and enabled IPv4 link-local for ${INTERFACE}."
  show_result
  exit 0
fi

if command -v avahi-autoipd >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1; then
  ip link set "${INTERFACE}" up
  systemctl enable --now "avahi-autoipd@${INTERFACE}.service"
  echo "Enabled avahi-autoipd for IPv4 link-local on ${INTERFACE}."
  show_result
  exit 0
fi

cat >&2 <<'ERROR'
Could not find NetworkManager, systemd-networkd, or avahi-autoipd tooling.
Install/enable one of those IPv4 link-local managers, then rerun this script.
ERROR
exit 1

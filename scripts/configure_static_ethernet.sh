#!/usr/bin/env bash
set -euo pipefail

INTERFACE="eth0"
ADDRESS=""
GATEWAY=""
DNS=""
CONNECTION_NAME="bric-eth0-static"

usage() {
  cat <<'USAGE'
Configure a Raspberry Pi Ethernet interface with a static IPv4 address.

Examples:
  sudo scripts/configure_static_ethernet.sh --address 10.42.0.2/24
  sudo scripts/configure_static_ethernet.sh --interface eth0 --address 10.42.0.3/24

Options:
  --interface NAME   Ethernet interface to configure (default: eth0)
  --address CIDR    Required static address, e.g. 10.42.0.2/24
  --gateway IP      Optional gateway. Leave unset for an offline switch.
  --dns IP          Optional DNS server. Leave unset for an offline switch.
  --connection NAME NetworkManager connection name (default: bric-eth0-static)
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interface)
      INTERFACE="${2:?missing value for --interface}"
      shift 2
      ;;
    --address)
      ADDRESS="${2:?missing value for --address}"
      shift 2
      ;;
    --gateway)
      GATEWAY="${2:?missing value for --gateway}"
      shift 2
      ;;
    --dns)
      DNS="${2:?missing value for --dns}"
      shift 2
      ;;
    --connection)
      CONNECTION_NAME="${2:?missing value for --connection}"
      shift 2
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

if [[ -z "${ADDRESS}" ]]; then
  echo "--address is required, e.g. --address 10.42.0.2/24" >&2
  exit 2
fi

if ! [[ "${ADDRESS}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+$ ]]; then
  echo "--address must be CIDR notation, e.g. 10.42.0.2/24" >&2
  exit 2
fi

if command -v nmcli >/dev/null 2>&1; then
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
    ipv4.method manual \
    ipv4.addresses "${ADDRESS}" \
    ipv4.never-default yes \
    ipv4.ignore-auto-dns yes \
    ipv6.method disabled

  if [[ -n "${GATEWAY}" ]]; then
    nmcli connection modify "${CONNECTION_NAME}" \
      ipv4.gateway "${GATEWAY}" \
      ipv4.never-default no
  else
    nmcli connection modify "${CONNECTION_NAME}" ipv4.gateway ""
  fi

  if [[ -n "${DNS}" ]]; then
    nmcli connection modify "${CONNECTION_NAME}" ipv4.dns "${DNS}"
  else
    nmcli connection modify "${CONNECTION_NAME}" ipv4.dns ""
  fi

  nmcli connection up "${CONNECTION_NAME}"
  echo "Configured ${INTERFACE} as ${ADDRESS} with NetworkManager."
  exit 0
fi

if command -v systemctl >/dev/null 2>&1; then
  network_file="/etc/systemd/network/10-bric-${INTERFACE}.network"
  {
    printf '[Match]\n'
    printf 'Name=%s\n\n' "${INTERFACE}"
    printf '[Network]\n'
    printf 'DHCP=no\n'
    printf 'Address=%s\n' "${ADDRESS}"
    printf 'LinkLocalAddressing=yes\n'
    if [[ -n "${GATEWAY}" ]]; then
      printf 'Gateway=%s\n' "${GATEWAY}"
    fi
    if [[ -n "${DNS}" ]]; then
      printf 'DNS=%s\n' "${DNS}"
    fi
  } > "${network_file}"

  systemctl enable --now systemd-networkd
  networkctl reload 2>/dev/null || systemctl restart systemd-networkd
  echo "Wrote ${network_file} and enabled systemd-networkd for ${INTERFACE} ${ADDRESS}."
  exit 0
fi

cat >&2 <<'ERROR'
Could not find NetworkManager or systemd-networkd tooling.
Configure eth0 manually with the static address shown in --address.
ERROR
exit 1

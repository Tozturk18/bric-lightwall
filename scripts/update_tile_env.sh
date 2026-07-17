#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-/etc/bric-lightwall/tile.env}"

mkdir -p "$(dirname "${ENV_FILE}")"

declare -A values=()

if [[ -f "${ENV_FILE}" ]]; then
  while IFS='=' read -r key value; do
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    [[ -z "${key}" || "${key}" == \#* ]] && continue
    values["${key}"]="${value}"
  done < "${ENV_FILE}"
fi

eth0_mac=""
if [[ -r /sys/class/net/eth0/address ]]; then
  eth0_mac="$(tr -d '\n' < /sys/class/net/eth0/address)"
fi

values[BRIC_TILE_NAME]="${values[BRIC_TILE_NAME]:-bric-tile}"
if [[ "${values[BRIC_LISTEN_IP_LOCKED]:-0}" != "1" ]]; then
  values[BRIC_LISTEN_IP]="0.0.0.0"
else
  values[BRIC_LISTEN_IP]="${values[BRIC_LISTEN_IP]:-0.0.0.0}"
fi
values[BRIC_LISTEN_PORT]="${values[BRIC_LISTEN_PORT]:-4210}"
values[BRIC_WALL_WIDTH]="64"
values[BRIC_WALL_HEIGHT]="64"
values[BRIC_PANEL_ROWS]="32"
values[BRIC_PANEL_COLS]="64"
values[BRIC_PANEL_CHAIN]="2"
values[BRIC_PANEL_PARALLEL]="1"
values[BRIC_BRIGHTNESS]="40"
if [[ "${values[BRIC_TILE_MAC_LOCKED]:-0}" != "1" && -n "${eth0_mac}" ]]; then
  values[BRIC_TILE_MAC]="${eth0_mac}"
else
  values[BRIC_TILE_MAC]="${values[BRIC_TILE_MAC]:-auto}"
fi
values[BRIC_HARDWARE_MAPPING]="regular"
values[BRIC_PIXEL_MAPPING]="stacked-panel2-top-rot180"
values[BRIC_OUTPUT_ROTATION]="180"
values[BRIC_SLOWDOWN_GPIO]="4"
values[BRIC_FRAME_TIMEOUT_MS]="${values[BRIC_FRAME_TIMEOUT_MS]:-100}"
values[BRIC_SOCKET_RCVBUF]="${values[BRIC_SOCKET_RCVBUF]:-8388608}"
values[BRIC_IDLE_PATTERN]="${values[BRIC_IDLE_PATTERN]:-blank}"

tmp_file="$(mktemp)"
{
  printf 'BRIC_TILE_NAME=%s\n' "${values[BRIC_TILE_NAME]}"
  printf 'BRIC_LISTEN_IP=%s\n' "${values[BRIC_LISTEN_IP]}"
  printf 'BRIC_LISTEN_PORT=%s\n' "${values[BRIC_LISTEN_PORT]}"
  printf 'BRIC_WALL_WIDTH=%s\n' "${values[BRIC_WALL_WIDTH]}"
  printf 'BRIC_WALL_HEIGHT=%s\n' "${values[BRIC_WALL_HEIGHT]}"
  printf 'BRIC_PANEL_ROWS=%s\n' "${values[BRIC_PANEL_ROWS]}"
  printf 'BRIC_PANEL_COLS=%s\n' "${values[BRIC_PANEL_COLS]}"
  printf 'BRIC_PANEL_CHAIN=%s\n' "${values[BRIC_PANEL_CHAIN]}"
  printf 'BRIC_PANEL_PARALLEL=%s\n' "${values[BRIC_PANEL_PARALLEL]}"
  printf 'BRIC_BRIGHTNESS=%s\n' "${values[BRIC_BRIGHTNESS]}"
  printf 'BRIC_TILE_MAC=%s\n' "${values[BRIC_TILE_MAC]:-}"
  printf 'BRIC_HARDWARE_MAPPING=%s\n' "${values[BRIC_HARDWARE_MAPPING]}"
  printf 'BRIC_PIXEL_MAPPING=%s\n' "${values[BRIC_PIXEL_MAPPING]}"
  printf 'BRIC_OUTPUT_ROTATION=%s\n' "${values[BRIC_OUTPUT_ROTATION]}"
  printf 'BRIC_SLOWDOWN_GPIO=%s\n' "${values[BRIC_SLOWDOWN_GPIO]}"
  printf 'BRIC_FRAME_TIMEOUT_MS=%s\n' "${values[BRIC_FRAME_TIMEOUT_MS]}"
  printf 'BRIC_SOCKET_RCVBUF=%s\n' "${values[BRIC_SOCKET_RCVBUF]}"
  printf 'BRIC_IDLE_PATTERN=%s\n' "${values[BRIC_IDLE_PATTERN]}"
} > "${tmp_file}"

install -m 0644 "${tmp_file}" "${ENV_FILE}"
rm -f "${tmp_file}"

echo "Updated ${ENV_FILE} for 64x64 stacked BRIC tile output."

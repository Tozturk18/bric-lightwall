#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-/etc/bric-lightwall/tile.env}"

echo "== Hostname =="
hostname

echo
echo "== eth0 MAC =="
cat /sys/class/net/eth0/address 2>/dev/null || true

echo
echo "== eth0 IPv4 =="
ip -4 addr show eth0 2>/dev/null || true

echo
echo "== All IPv4 interfaces =="
ip -4 addr show 2>/dev/null || ifconfig 2>/dev/null || true

echo
echo "== IPv4 routes =="
ip route 2>/dev/null || netstat -rn -f inet 2>/dev/null || true

echo
echo "== ${ENV_FILE} =="
sed -n '1,200p' "${ENV_FILE}" 2>/dev/null || true

echo
echo "== Service status =="
printf 'bric-tile.service: '
systemctl is-active bric-tile.service 2>/dev/null || true
printf 'bric-discovery.service: '
systemctl is-active bric-discovery.service 2>/dev/null || true

echo
echo "== UDP listeners =="
ss -ulpn 2>/dev/null | grep -E ':(4209|4210)\b' || true

echo
echo "== bric-discovery.service journal =="
journalctl -u bric-discovery.service -n 40 --no-pager 2>/dev/null || true

echo
echo "== bric-tile.service journal =="
journalctl -u bric-tile.service -n 60 --no-pager 2>/dev/null || true

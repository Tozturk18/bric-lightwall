#!/usr/bin/env bash
set -euo pipefail

systemctl stop bric-tile.service bric-discovery.service 2>/dev/null || true
systemctl disable bric-tile.service bric-discovery.service 2>/dev/null || true

rm -f /etc/systemd/system/bric-tile.service
rm -f /etc/systemd/system/bric-discovery.service

systemctl daemon-reload
systemctl reset-failed bric-tile.service bric-discovery.service 2>/dev/null || true

echo "BRIC tile services removed."


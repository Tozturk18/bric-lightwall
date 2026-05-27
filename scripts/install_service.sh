#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

install -m 0644 "${REPO_DIR}/systemd/bric-tile.service" /etc/systemd/system/bric-tile.service
install -m 0644 "${REPO_DIR}/systemd/bric-discovery.service" /etc/systemd/system/bric-discovery.service

systemctl daemon-reload
systemctl enable bric-tile.service bric-discovery.service
systemctl restart bric-discovery.service
systemctl restart bric-tile.service

systemctl --no-pager --full status bric-discovery.service || true
systemctl --no-pager --full status bric-tile.service || true


# Offline Ethernet Operation

The wall can run with no WiFi and no internet as long as the Mac or mini-PC and
all Raspberry Pis have IPv4 addresses on the same Ethernet subnet. The TP-Link
TL-SG1024DE switch does not provide DHCP by itself, so use static addresses or
another local DHCP source.

Recommended static layout:

```text
MacBook / mini-PC Ethernet: 10.42.0.1/24
Pi tile 1 eth0:            10.42.0.2/24
Pi tile 2 eth0:            10.42.0.3/24
Pi tile 3 eth0:            10.42.0.4/24
Pi tile 4 eth0:            10.42.0.5/24
Gateway/DNS:               blank for offline use
```

On macOS, configure the USB-C or built-in Ethernet adapter manually in System
Settings with IP `10.42.0.1` and subnet mask `255.255.255.0`. On this Mac, the
active Ethernet adapter currently appears as `en7`; verify with:

```bash
python3 tools/discover_tiles.py --show-interfaces
```

On each Raspberry Pi, assign a unique static address:

```bash
cd /opt/bric-lightwall
sudo scripts/configure_static_ethernet.sh --address 10.42.0.2/24
sudo scripts/update_tile_env.sh
sudo scripts/install_service.sh
```

Use `10.42.0.3/24`, `10.42.0.4/24`, and `10.42.0.5/24` on the other Pis. The
`update_tile_env.sh` step refreshes `BRIC_TILE_MAC` from each Pi's own `eth0`
address, which keeps alignment identity stable across WiFi/Ethernet changes.

Discover receivers over Ethernet:

```bash
python3 tools/discover_tiles.py --interface en7 --subnet 10.42.0.0/24
```

If you do not know the interface name, omit `--interface`; discovery now sends
directed broadcasts on every local IPv4 interface:

```bash
python3 tools/discover_tiles.py
```

To keep an existing physical alignment but update saved WiFi IPs to Ethernet
IPs, refresh `wall_layout.json` by MAC:

```bash
python3 tools/refresh_layout_ips.py --interface en7 --subnet 10.42.0.0/24
```

If the refresh reports duplicate or ambiguous MACs, rerun this on every Pi and
then redo alignment once:

```bash
sudo /opt/bric-lightwall/scripts/update_tile_env.sh
sudo systemctl restart bric-discovery.service bric-tile.service
```

Run the combined web app over Ethernet:

```bash
python3 tools/webapp/app.py \
  --interface en7 \
  --subnet 10.42.0.0/24 \
  --web-host 127.0.0.1
```

Open `http://localhost:8080`, complete alignment, save the layout, then use the
Games tab. Before each game starts, the web app refreshes saved layout IPs by
MAC so switching between WiFi and Ethernet does not require reassigning tiles.

Direct sender tools also work over Ethernet once the target IPs are Ethernet
addresses:

```bash
python3 tools/pong/pong_lightwall.py --host 10.42.0.2
python3 tools/send_test_pattern.py --ip 10.42.0.2 --pattern moving-bar
```

Troubleshooting:

- If no tiles are discovered, confirm each Pi has an `eth0` IPv4 address with
  `sudo scripts/healthcheck.sh`.
- If discovery only returns `192.168.1.x`, the saved layout or discovery run is
  still using WiFi. Run discovery with `--interface en7 --subnet 10.42.0.0/24`
  and save or refresh the layout.
- If a game preview runs but the wall does not update, verify `wall_layout.json`
  contains `10.42.0.x` addresses, not `192.168.1.x`.
- If duplicate MACs appear, refresh each Pi's tile env with
  `sudo scripts/update_tile_env.sh`; do not copy a populated `tile.env` from one
  Pi to another.

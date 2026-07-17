# Offline Ethernet Operation

The wall can run with no WiFi and no internet as long as the Mac or mini-PC can
reach the Raspberry Pis over IPv4 on Ethernet. The saved wall layout uses each
Pi's Ethernet MAC address as the durable identity; IP addresses are discovered at
runtime and may change.

If you have DHCP on the Ethernet network, random/DHCP addresses are fine. If the
TP-Link TL-SG1024DE is the only network device, it will not hand out DHCP leases
by itself; link-local `169.254.x.x` addresses are also fine. Discovery probes
ARP-seen link-local addresses and maps them back to each tile's MAC.

Recommended random/link-local layout:

```text
MacBook / mini-PC Ethernet: 169.254.x.x/16 on the Ethernet adapter
Pi tile eth0:               169.254.x.x/16 chosen automatically per Pi
Gateway/DNS:                blank for offline use
```

On macOS, set the Ethernet adapter to DHCP for a fully offline switch; with no
DHCP server present, macOS should self-assign a `169.254.x.x` address. If the
adapter is still manually set to the old static fallback address, you can add a
temporary link-local alias for testing:

```bash
sudo ifconfig en7 inet 169.254.1.1 netmask 255.255.0.0 alias
```

On each Raspberry Pi, make sure `eth0` also has an IPv4 address. An `inet6
fe80::...` line is not enough for the current receiver stack because discovery
and frame streaming use IPv4 UDP.

```bash
cd /opt/bric-lightwall
sudo scripts/configure_linklocal_ethernet.sh
sudo scripts/update_tile_env.sh
sudo scripts/install_service.sh
ip -4 addr show eth0
```

The last command should show an address like `inet 169.254.87.128/16` on `eth0`.
The exact address may change; the saved wall layout uses the Ethernet MAC
address instead.

Optional static fallback layout:

```text
MacBook / mini-PC Ethernet: 10.42.0.1/24
Pi tile 1 eth0:            10.42.0.2/24
Pi tile 2 eth0:            10.42.0.3/24
Pi tile 3 eth0:            10.42.0.4/24
Pi tile 4 eth0:            10.42.0.5/24
Gateway/DNS:               blank for offline use
```

On macOS, verify the active Ethernet adapter name with:

```bash
python3 tools/discover_tiles.py --show-interfaces
```

On this Mac it currently appears as `en7`. If you choose the optional static
fallback, configure the Mac Ethernet adapter manually with IP `10.42.0.1` and
subnet mask `255.255.255.0`.

On each Raspberry Pi, make sure the tile env uses the Pi's real Ethernet MAC:

```bash
cd /opt/bric-lightwall
sudo scripts/update_tile_env.sh
sudo scripts/install_service.sh
```

If you choose static fallback addresses, assign a unique address first. Do not
run the same `10.42.0.2/24` command on every Pi.

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
python3 tools/discover_tiles.py --interface en7
```

If you do not know the interface name, omit `--interface`; discovery sends
directed broadcasts on every local IPv4 interface and probes complete ARP-cache
entries:

```bash
python3 tools/discover_tiles.py
```

To keep an existing physical alignment but refresh the cached current route for
each MAC, run:

```bash
python3 tools/refresh_layout_ips.py --interface en7
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
  --web-host 127.0.0.1
```

Open `http://localhost:8080`, complete alignment, save the layout, then use the
Games tab. Before each game starts, the web app resolves every saved MAC to its
currently discovered IP. If a MAC is missing or duplicated, the game will not
start against stale addresses.

Direct single-tile sender tools still accept explicit IPs for quick diagnostics:

```bash
python3 tools/pong/pong_lightwall.py --host 10.42.0.2
python3 tools/send_test_pattern.py --ip 10.42.0.2 --pattern moving-bar
```

Troubleshooting:

- If no tiles are discovered, confirm each Pi has an `eth0` IPv4 address with
  `sudo scripts/healthcheck.sh`.
- If `eth0` only shows `inet6 fe80::...` and has no `inet` line, run
  `sudo scripts/configure_linklocal_ethernet.sh` on that Pi.
- If the Pis show `169.254.x.x` addresses, that is acceptable; rerun discovery
  after the Mac has seen them on the Ethernet link.
- If discovery only returns WiFi-side addresses, run discovery with the Ethernet
  interface, for example `--interface en7`.
- If a game refuses to start with unresolved MACs, the corresponding Pi did not
  respond to discovery on the selected Ethernet network.
- If duplicate MACs appear, refresh each Pi's tile env with
  `sudo scripts/update_tile_env.sh`; do not copy a populated `tile.env` from one
  Pi to another.

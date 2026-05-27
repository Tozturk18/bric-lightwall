# BRIC Tile Receiver

BRIC Tile Receiver is a small C++17 UDP receiver for one BRIC Light Wall HUB75 tile controller. It receives chunked RGB888 frames over UDP, reassembles complete frames, and displays them with the already-built `hzeller/rpi-rgb-led-matrix` library.

This first clean implementation targets the Raspberry Pi 5 running DietPi/Debian as root, using DHCP addresses and tile identity by Ethernet MAC address. Hostnames and fixed IP addresses are intentionally not used for identity.

## Current Tested Hardware Configuration

The current panel setup was verified with the upstream matrix demo:

```bash
cd /opt/rpi-rgb-led-matrix/examples-api-use
sudo ./demo \
  --led-rows=32 \
  --led-cols=64 \
  --led-chain=2 \
  --led-parallel=1 \
  --led-brightness=40 \
  --led-slowdown-gpio=4 \
  -D 0
```

The matrix library reports a hardware canvas of `128x32` because it sees two chained `64x32` panels side by side. The physical BRIC tile is mounted differently: panel 2 is above panel 1, and panel 2 is rotated 180 degrees. The receiver therefore exposes a logical UDP frame size of `64x64` and maps it onto the library's `128x32` canvas.

```text
rows=32
cols=64
chain=2
parallel=1
matrix canvas=128x32
logical UDP size=64x64
brightness=40
slowdown_gpio=4
hardware_mapping=regular
pixel_mapping=stacked-panel2-top-rot180
output_rotation=180
```

## Dependency

The receiver links directly against:

```text
/opt/rpi-rgb-led-matrix/include
/opt/rpi-rgb-led-matrix/lib/librgbmatrix.a
```

The library must already be cloned and built. This repository does not vendor or rebuild it.

## Configuration

The receiver reads:

```text
/etc/bric-lightwall/tile.env
```

Required and optional keys are shown in [config/tile.env.example](config/tile.env.example).

Update the active tile config for the current stacked `64x64` layout:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/scripts/update_tile_env.sh
```

To change display size later, update these together:

```text
BRIC_WALL_WIDTH
BRIC_WALL_HEIGHT
BRIC_PANEL_ROWS
BRIC_PANEL_COLS
BRIC_PANEL_CHAIN
BRIC_PANEL_PARALLEL
BRIC_PIXEL_MAPPING
```

For the current physical layout, keep the matrix hardware settings at `panel_cols=64`, `panel_rows=32`, `chain=2`, `parallel=1`, but set `BRIC_WALL_WIDTH=64`, `BRIC_WALL_HEIGHT=64`, `BRIC_PIXEL_MAPPING=stacked-panel2-top-rot180`, and `BRIC_OUTPUT_ROTATION=180`.

Mapping details:

- Logical rows `0..31` go to physical panel 2, which is the top panel.
- Logical rows `32..63` go to physical panel 1, which is the bottom panel.
- Panel 2 is rotated 180 degrees, so both local axes are inverted before writing into the second chained panel.
- `(0,0)` is treated as the top-left corner of each physical `64x32` panel.
- `BRIC_OUTPUT_ROTATION=180` rotates the final logical tile image so text appears upright on the installed tile.

## Build

```bash
cd /opt/bric-lightwall/bric-tile-receiver
./scripts/build.sh
```

The receiver binary is:

```text
/opt/bric-lightwall/bric-tile-receiver/build/bric_tile_receiver
```

## Run Manually

Run a local LED test pattern:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/build/bric_tile_receiver --test-pattern 3
```

Run the UDP receiver in the foreground:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/build/bric_tile_receiver
```

It prints lightweight stats once per second:

```text
packets_per_second
bytes_per_second
completed_frames
displayed_fps
dropped_frames
incomplete_frames
bad_packets
bad_size_frames
last_sender_ip
```

## Send Test Frames

From the Pi itself:

```bash
python3 /opt/bric-lightwall/bric-tile-receiver/tools/send_solid_frame.py \
  --ip 127.0.0.1 \
  --width 64 \
  --height 64 \
  --r 255 \
  --g 0 \
  --b 0 \
  --fps 30 \
  --frames 120
```

From a Mac or another machine, replace `--ip` with the tile controller IP:

```bash
python3 tools/send_test_pattern.py \
  --ip 192.168.1.63 \
  --width 64 \
  --height 64 \
  --fps 30 \
  --pattern moving-bar
```

Cyclic rainbow strand test from a Mac:

```bash
python3 tools/send_rainbow_strand.py \
  --ip 192.168.1.63 \
  --width 64 \
  --height 64 \
  --fps 30 \
  --order row-major
```

## Pong

Run Pong from the MacBook or mini-PC:

```bash
python3 tools/pong/pong_lightwall.py \
  --host 10.42.0.2 \
  --port 4210 \
  --width 64 \
  --height 64
```

Install pygame first if needed:

```bash
python3 -m pip install pygame
```

See [docs/pong.md](docs/pong.md).

## Browser Alignment

Run the local alignment web app from the MacBook or mini-PC:

```bash
python3 tools/alignment_web/alignment_server.py \
  --subnet 10.42.0.0/24 \
  --port 4210
```

Then open:

```text
http://localhost:8080
```

Install Flask first if needed:

```bash
python3 -m pip install flask
```

See [docs/alignment.md](docs/alignment.md).

Alignment opens with a small wall-size dialog, discovers receivers automatically, turns the active tile red, and advances to the next MAC address after each grid click. Assigned tiles show a white number on a black background. Alignment sends red/number frames with `--protocol both` by default for compatibility with BRCP and older BRIC receivers. Pong defaults to BRCP; use `--protocol bric` or `--protocol both` if the preview runs but the tile does not update.

## Discovery

Discovery uses a separate UDP responder on port `4209`. It listens for the exact text:

```text
BRIC_DISCOVER
```

and responds with JSON containing tile identity, MAC address, IP, display configuration, and receiver version.

Run the responder manually:

```bash
python3 /opt/bric-lightwall/bric-tile-receiver/tools/discovery_responder.py
```

Discover from another machine:

```bash
python3 /opt/bric-lightwall/bric-tile-receiver/tools/discover_tiles.py
```

## UDP Frame Protocol

Mac-side tools use BRCP chunked UDP by default. Each datagram starts with this network-byte-order header:

```text
magic[4]       = "BRCP"
frame_width    = uint16_t
frame_height   = uint16_t
frame_number   = uint32_t
chunk_index    = uint16_t
total_chunks   = uint16_t
payload_length = uint16_t
```

The receiver also accepts the earlier BRIC packet header for existing scripts:

```text
magic[4]      = "BRIC"
version       = uint8_t, currently 1
packet_type   = uint8_t
header_size   = uint16_t
frame_id      = uint32_t
frame_width   = uint16_t
frame_height  = uint16_t
chunk_index   = uint16_t
total_chunks  = uint16_t
payload_size  = uint16_t
flags         = uint16_t
reserved      = uint32_t
```

Packet types:

```text
1 = frame chunk
2 = full-frame packet if small enough
3 = ping
4 = pong
5 = config/info request
6 = config/info response
```

RGB payloads are contiguous RGB888 row-major bytes. For the current logical `64x64` tile, one frame is:

```text
64 * 64 * 3 = 12288 bytes
```

The sender tools default to 1024-byte chunks, so a `64x64` frame is sent as 12 packets.

The receiver accepts only frames whose `frame_width` and `frame_height` match the configured logical display size. Wrong-size frames are dropped and counted in `bad_size_frames`.

## Systemd

Install and start both services:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/scripts/install_service.sh
```

Services:

```text
bric-tile.service       C++ UDP receiver on port 4210
bric-discovery.service  Python discovery responder on port 4209
```

Uninstall:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/scripts/uninstall_service.sh
```

Health check:

```bash
sudo /opt/bric-lightwall/bric-tile-receiver/scripts/healthcheck.sh
```

## Troubleshooting

- If the receiver fails during matrix initialization, rerun the upstream demo command and confirm the same panel options still work.
- If the receiver reports a mapping mismatch, check `BRIC_WALL_WIDTH`, `BRIC_WALL_HEIGHT`, `BRIC_PANEL_*`, and `BRIC_PIXEL_MAPPING`.
- If discovery returns `0.0.0.0`, confirm `eth0` has carrier and a DHCP IPv4 address.
- If UDP frames are dropped, keep `--chunk-size` at or below `1024` and verify sender width/height match the tile config.
- If the service restarts continuously, inspect `journalctl -u bric-tile.service -n 100 --no-pager`.

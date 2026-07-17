# Pong Sender

`tools/pong/pong_lightwall.py` runs on the MacBook or mini-PC. It opens a pygame preview window, renders Pong into a logical RGB888 framebuffer, and streams the same frames to the tile receiver with BRCP chunked UDP.

Install pygame on the sender machine if needed:

```bash
python3 -m pip install pygame
```

Run:

```bash
cd /opt/bric-lightwall/bric-tile-receiver
python3 tools/pong/pong_lightwall.py \
  --host 10.42.0.2 \
  --port 4210 \
  --width 64 \
  --height 64
```

For a multi-tile wall, Pong uses `wall_layout.json` by default and resolves each
saved MAC to the tile's current IP before streaming. If the sender has multiple
active networks, pass the Ethernet interface/subnet you want discovery to use:

```bash
python3 tools/refresh_layout_ips.py --interface en7 --subnet 10.42.0.0/24
python3 tools/pong/pong_lightwall.py --interface en7 --subnet 10.42.0.0/24
```

For an old IP-only layout, use `--no-resolve-layout`.

Controls:

- Up arrow: move player paddle up
- Down arrow: move player paddle down
- Esc: quit
- Ctrl+C: quit from the terminal

Defaults:

- `--fps 30`
- `--chunk-size 1024`
- `--protocol brcp`

The sender does not send full frames as one UDP datagram. A `64x64` RGB888 frame is `12288` bytes and is split into 12 chunks at the default chunk size.

The software framebuffer uses top-left origin and row-major RGB888 bytes. Tile physical mapping remains the receiver's responsibility.

If the preview opens but the tile does not update, the Pi may still be running an older receiver that only accepts the previous BRIC chunk header. Try:

```bash
python3 tools/pong/pong_lightwall.py --host 10.42.0.2 --protocol bric
```

For a short compatibility test you can also use `--protocol both`, which sends each frame using both chunk headers.

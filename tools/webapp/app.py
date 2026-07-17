#!/usr/bin/env python3
# =============================================================================
# app.py - Two-tab BRIC Light Wall web app: Alignment + Games.
#
# This is the single Flask process for the whole UI. It composes the
# existing alignment_server.create_app() (unchanged REST API, wired with a
# last-wins hook) with new routes for picking a game mode and a /ws/game
# websocket that relays browser input to the active game subprocess and
# mirrors the game's own wall frames back to the browser.
#
# Run:
#   python3 tools/webapp/app.py --subnet 10.42.0.0/24
# =============================================================================

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
WEBAPP_DIR = Path(__file__).resolve().parent
if str(WEBAPP_DIR) not in sys.path:
    sys.path.insert(0, str(WEBAPP_DIR))

import alignment_server
from common.layout_refresh import refresh_layout_ips
from orchestrator import DEFAULT_INPUT_PORT, SUBPROCESS_MODES, WallDriverManager

# How often each browser connection's send loop checks for a new mirrored
# frame while otherwise blocked waiting on incoming messages. Short enough
# that browser-perceived input latency and frame latency both stay well
# under a frame interval at typical wall FPS; named so it can be retuned
# without restructuring the connection loop.
WS_RECEIVE_TIMEOUT_S = 0.03

GAME_MODES = ("pong", "invaders", "color_game", "rainbow")


class FrameBroadcastHub:
    """
    Fan-out point between the orchestrator's single MirrorListener and any
    number of connected browser websocket clients.

    Each subscriber holds only the single most recent frame, never a
    queue: a new frame overwrites whatever that subscriber hasn't sent
    yet. This guarantees a slow or stalled browser client can never build
    an unbounded backlog or fall further and further behind on stale
    frames - it just skips forward to the latest frame once it catches up.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest_by_subscriber: Dict[int, bytes] = {}
        self._next_id = 0

    def subscribe(self) -> int:
        with self._lock:
            subscriber_id = self._next_id
            self._next_id += 1
            self._latest_by_subscriber[subscriber_id] = b""
            return subscriber_id

    def unsubscribe(self, subscriber_id: int) -> None:
        with self._lock:
            self._latest_by_subscriber.pop(subscriber_id, None)

    def publish(self, frame: bytes) -> None:
        with self._lock:
            for subscriber_id in self._latest_by_subscriber:
                self._latest_by_subscriber[subscriber_id] = frame

    def take_latest(self, subscriber_id: int) -> Optional[bytes]:
        """Return and clear the pending frame for this subscriber, or None if
        there isn't a new one since the last take_latest() call."""
        with self._lock:
            frame = self._latest_by_subscriber.get(subscriber_id)
            if not frame:
                return None
            self._latest_by_subscriber[subscriber_id] = b""
            return frame


def _relay_input_to_game(message: dict) -> None:
    """
    Forward one parsed browser input message to whatever game subprocess
    is currently listening on DEFAULT_INPUT_PORT. Best-effort: if nothing
    is listening (no game active, or it's between switches), the send
    simply has no receiver and is silently dropped - never raises into the
    websocket handler.
    """
    import socket as _socket

    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
    try:
        sock.sendto(json.dumps(message).encode("utf-8"), ("127.0.0.1", DEFAULT_INPUT_PORT))
    except OSError:
        pass
    finally:
        sock.close()


def create_app(args: argparse.Namespace):
    try:
        from flask import Flask, jsonify, request
        from flask_sock import Sock
    except ImportError as error:
        raise SystemExit(
            "Flask and flask-sock are required. Install with: "
            "python3 -m pip install -r requirements.txt"
        ) from error

    manager = WallDriverManager()
    hub = FrameBroadcastHub()
    manager.start_mirror(hub.publish)

    align_app = alignment_server.create_app(args, on_before_drive=manager.stop)
    sock = Sock(align_app)

    @align_app.get("/api/games/state")
    def api_games_state():
        return jsonify({"active_mode": manager.active_mode, "modes": list(GAME_MODES)})

    @align_app.post("/api/games/start")
    def api_games_start():
        data = request.get_json(force=True, silent=True) or {}
        mode = data.get("mode")
        if mode not in GAME_MODES:
            return jsonify({"error": f"unknown mode: {mode}", "modes": list(GAME_MODES)}), 400

        layout_path = Path(args.output).resolve()
        if not layout_path.exists():
            return jsonify({
                "error": (
                    f"no wall layout at {layout_path}; complete tile alignment and "
                    "Save first, or POST a single-tile --host fallback is not yet supported here"
                )
            }), 400

        refresh_warning = None
        if args.refresh_layout_ips:
            try:
                refresh_result = refresh_layout_ips(
                    layout_path,
                    default_port=args.receiver_port,
                    subnet=args.subnet,
                    discovery_port=args.discovery_port,
                    timeout=args.discovery_timeout,
                    limit=args.scan_limit,
                    interfaces=args.interfaces,
                    scan_auto_subnets=args.scan_auto_subnets,
                )
                if refresh_result.ambiguous_macs:
                    refresh_warning = (
                        "layout IP refresh skipped duplicate MACs: "
                        + ", ".join(refresh_result.ambiguous_macs)
                    )
            except Exception as error:
                refresh_warning = f"layout IP refresh failed: {error}"

        params = dict(
            layout=str(layout_path),
            width=args.width,
            height=args.height,
            port=args.receiver_port,
        )
        try:
            manager.switch_to(mode, **params)
        except Exception as error:
            return jsonify({"error": str(error)}), 500
        return jsonify({"active_mode": manager.active_mode, "warning": refresh_warning})

    @align_app.post("/api/games/stop")
    def api_games_stop():
        manager.stop()
        return jsonify({"active_mode": manager.active_mode})

    @sock.route("/ws/game")
    def ws_game(ws):
        """
        One thread per connected browser client (flask-sock's default).
        Each iteration: wait up to WS_RECEIVE_TIMEOUT_S for an incoming
        message (None on a plain timeout - normal, just means nothing
        arrived yet, keep looping), relay it to the active game's input
        port if present, then send this subscriber's latest pending
        mirrored frame, if any. simple_websocket raises ConnectionClosed
        (not a special return value) once the client actually disconnects.
        """
        from simple_websocket import ConnectionClosed

        subscriber_id = hub.subscribe()
        try:
            while True:
                try:
                    message = ws.receive(timeout=WS_RECEIVE_TIMEOUT_S)
                except ConnectionClosed:
                    break

                if isinstance(message, str):
                    try:
                        parsed = json.loads(message)
                    except json.JSONDecodeError:
                        parsed = None
                    if isinstance(parsed, dict):
                        _relay_input_to_game(parsed)

                frame = hub.take_latest(subscriber_id)
                if frame:
                    ws.send(frame)
        finally:
            hub.unsubscribe(subscriber_id)

    return align_app


def main() -> int:
    args = alignment_server.parse_args()
    app = create_app(args)
    print(f"Open http://localhost:{args.web_port}")
    app.run(host=args.web_host, port=args.web_port, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

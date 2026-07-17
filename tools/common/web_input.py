#!/usr/bin/env python3
# =============================================================================
# web_input.py - Browser input relay for game subprocesses.
#
# Each game (Pong, Space Invaders, Color Game) runs as its own OS
# subprocess, launched by the Flask parent's orchestrator. The browser's
# websocket connection terminates in the Flask parent, not the subprocess,
# so key events are relayed to the subprocess over a small local UDP
# channel (DEFAULT_INPUT_PORT) - symmetric to how frames are teed back to
# Flask over DEFAULT_MIRROR_PORT in tools/common/frame_mirror.py.
#
# Flow: browser -> websocket -> Flask -> UDP datagram (127.0.0.1) ->
# start_input_listener()'s background thread inside the subprocess ->
# WebAxisInput / WebSliderInput -> game loop.
#
# Local pygame keyboard polling remains the default/fallback in every game
# script; these classes are only used when a game is launched with
# --web-input by the orchestrator.
# =============================================================================

from __future__ import annotations

import json
import socket
import threading
from collections import deque
from typing import Callable, Deque, Set

# Fixed local port every game subprocess listens on for browser-relayed
# input, mirroring DEFAULT_MIRROR_PORT's frame channel in the other
# direction. Fixed for the same reason: only one game subprocess runs at a
# time (last-wins), and the orchestrator confirms the previous subprocess is
# dead before starting the next one.
DEFAULT_INPUT_PORT = 47601


class WebAxisInput:
    """
    Minimal input source for single-axis games (e.g. Pong's up/down paddle).

    A websocket relay thread calls set_axis()/press_key()/release_key() as
    messages arrive from the browser; the game loop calls get_axis() once
    per frame. Thread-safe: writer and reader run on different threads.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pressed: Set[str] = set()

    def press(self, key: str) -> None:
        with self._lock:
            self._pressed.add(key)

    def release(self, key: str) -> None:
        with self._lock:
            self._pressed.discard(key)

    def clear(self) -> None:
        with self._lock:
            self._pressed.clear()

    def is_pressed(self, key: str) -> bool:
        with self._lock:
            return key in self._pressed

    def get_axis(self, negative_key: str, positive_key: str) -> int:
        with self._lock:
            axis = 0
            if negative_key in self._pressed:
                axis -= 1
            if positive_key in self._pressed:
                axis += 1
            return axis


class WebHeldKeysInput:
    """
    Input source for games needing several simultaneously-held keys plus a
    stream of one-shot discrete events (e.g. Space Invaders: left/right/fire
    are held state, while pause/restart/submit/backspace/typed characters
    are single-frame edge events that must fire exactly once, mirroring
    pygame's KEYDOWN semantics rather than key-is-down polling).

    A websocket relay thread calls press()/release() for held keys and
    push_event() for one-shot events; the game loop calls is_pressed() for
    held state and drain_events() once per frame to consume and clear
    pending discrete events. Thread-safe: writer and reader run on
    different threads.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pressed: Set[str] = set()
        self._events: Deque[dict] = deque()

    def press(self, key: str) -> None:
        with self._lock:
            self._pressed.add(key)

    def release(self, key: str) -> None:
        with self._lock:
            self._pressed.discard(key)

    def is_pressed(self, key: str) -> bool:
        with self._lock:
            return key in self._pressed

    def push_event(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    def drain_events(self) -> list:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events


def start_input_listener(
    on_message: Callable[[dict], None],
    port: int = DEFAULT_INPUT_PORT,
) -> threading.Thread:
    """
    Start a daemon thread listening on 127.0.0.1:port for newline-independent
    JSON UDP datagrams from the Flask parent, calling on_message(dict) for
    each one that parses cleanly. Malformed datagrams are silently dropped
    (never crash the game loop over a bad browser message).

    The returned thread is a daemon: it does not need explicit shutdown when
    the subprocess exits, matching how the game loop itself terminates on
    process kill.
    """

    def _run() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", port))
        while True:
            try:
                data, _addr = sock.recvfrom(2048)
            except OSError:
                return
            try:
                message = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict):
                try:
                    on_message(message)
                except Exception:
                    pass

    thread = threading.Thread(target=_run, daemon=True, name="web-input-listener")
    thread.start()
    return thread

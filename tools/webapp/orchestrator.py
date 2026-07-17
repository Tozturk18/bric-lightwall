#!/usr/bin/env python3
# =============================================================================
# orchestrator.py - Single shared "wall driver" slot for the two-tab web app.
#
# Alignment and each Games-tab mode all drive the same physical wall, and
# only one of them may be doing so at a time (last-wins). This module owns
# that single slot and the mechanics of stopping whatever is currently
# running before starting the next thing:
#
#   - Pong, Space Invaders, and Color Game are pygame-based and run as
#     separate OS subprocesses (SDL wants the main thread, especially on
#     macOS, and pygame has per-process global state that makes repeated
#     start/stop/start of different games inside one process fragile).
#     Stopping means killing the process, not asking it nicely over a
#     shared-memory flag - a subprocess that ignored a polite stop would
#     otherwise keep pushing frames to the wall at the same time as
#     whatever starts next, which is exactly what last-wins must prevent.
#
#   - Rainbow Wall has no pygame/window dependency, so it runs as a plain
#     background thread via tools/rainbow_wall.py's run(args, stop_event).
#
# Each game subprocess additionally tees its wall frames to a fixed local
# UDP port (tools/common/frame_mirror.py) and, for Pong/Invaders/Color
# Game, listens on a second fixed local UDP port for browser-relayed input
# (tools/common/web_input.py). This module owns a single long-lived
# listener thread on the mirror port, invoking a caller-supplied callback
# for each received frame - the Flask app wires that callback to a
# websocket broadcast; this module has no Flask/websocket dependency of
# its own so it can be exercised and tested without either.
# =============================================================================

from __future__ import annotations

import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from common.frame_mirror import DEFAULT_MIRROR_PORT, FrameReassembler
from common.web_input import DEFAULT_INPUT_PORT

SUBPROCESS_STOP_TIMEOUT_S = 2.0
THREAD_STOP_TIMEOUT_S = 2.0

# Modes whose script lives directly under tools/, keyed by name -> relative
# path from REPO_ROOT. Rainbow Wall is deliberately absent: it is driven
# in-process via tools/rainbow_wall.run(), not launched as a script.
SUBPROCESS_MODES = {
    "pong": TOOLS_DIR / "pong" / "pong_lightwall.py",
    "invaders": TOOLS_DIR / "invaders_wall.py",
    "color_game": TOOLS_DIR / "color_game" / "main.py",
}


class GameProcess:
    """
    One running (or about to run) pygame-based game subprocess.

    start() launches it with SDL_VIDEODRIVER=dummy (the Flask host may have
    no real display) plus --web-input/--input-port/--mirror-port so it
    reads browser-relayed input and tees frames back to us, instead of
    reading a local keyboard/window that doesn't meaningfully exist here.

    stop() is unconditional: terminate, wait briefly, kill if still alive.
    It always leaves the subprocess confirmed dead before returning, which
    is the property last-wins depends on.
    """

    def __init__(self, name: str, script_path: Path, extra_args: Optional[list] = None):
        self.name = name
        self._script_path = script_path
        self._extra_args = extra_args or []
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        import os

        env = dict(os.environ)
        env["SDL_VIDEODRIVER"] = "dummy"

        args = [
            sys.executable,
            str(self._script_path),
            "--web-input",
            "--input-port", str(DEFAULT_INPUT_PORT),
            "--mirror-port", str(DEFAULT_MIRROR_PORT),
            *self._extra_args,
        ]
        self._proc = subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def stop(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            self._proc = None
            return
        self._proc.terminate()
        try:
            self._proc.wait(timeout=SUBPROCESS_STOP_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=SUBPROCESS_STOP_TIMEOUT_S)
        self._proc = None


class ThreadDriver:
    """
    Rainbow Wall's in-process background-thread equivalent of GameProcess.
    Same start()/stop()/is_alive() shape so WallDriverManager can treat
    both uniformly, but stop() sets a threading.Event and joins rather than
    killing an OS process.
    """

    def __init__(self, name: str, target: Callable[..., int], args: tuple):
        self.name = name
        self._target = target
        self._args = args
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._target,
            args=(*self._args, self._stop_event),
            daemon=True,
            name=f"wall-driver-{self.name}",
        )
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=THREAD_STOP_TIMEOUT_S)
        self._thread = None


class MirrorListener:
    """
    Long-lived background thread owned by the manager (started once,
    independent of which mode is active) that receives frames on the fixed
    local mirror port and forwards each one's raw bytes to on_frame().

    Runs continuously regardless of whether a game is currently active;
    datagrams simply stop arriving when nothing is streaming. Kept
    separate from any individual game's lifecycle so switching modes never
    requires rebinding this socket.

    Frames arrive chunked (FrameMirror splits them to stay under the OS's
    UDP datagram size limit), so each received datagram is fed through a
    FrameReassembler and on_frame() only fires once a complete frame has
    been reassembled.
    """

    def __init__(self, on_frame: Callable[[bytes], None], port: int = DEFAULT_MIRROR_PORT):
        self._on_frame = on_frame
        self._port = port
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._reassembler = FrameReassembler()

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", self._port))
        self._thread = threading.Thread(target=self._run, daemon=True, name="mirror-listener")
        self._thread.start()

    def _run(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while True:
            try:
                data, _addr = sock.recvfrom(1 << 16)
            except OSError:
                return
            try:
                frame = self._reassembler.add_datagram(data)
                if frame is not None:
                    self._on_frame(frame)
            except Exception:
                pass

    def stop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


class WallDriverManager:
    """
    The single shared wall-driver slot. Exactly one of {a GameProcess, a
    ThreadDriver, nothing} is active at a time.

    switch_to(None) stops whatever is active and starts nothing - this is
    what the alignment endpoints call before sending their own one-off
    frames, and what "stop everything" from the UI maps to.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: Optional[object] = None
        self._active_mode: Optional[str] = None
        self._mirror: Optional[MirrorListener] = None

    def start_mirror(self, on_frame: Callable[[bytes], None]) -> None:
        if self._mirror is not None:
            return
        self._mirror = MirrorListener(on_frame)
        self._mirror.start()

    @property
    def active_mode(self) -> Optional[str]:
        with self._lock:
            return self._active_mode

    def switch_to(self, mode: Optional[str], **params) -> None:
        """
        Stop whatever is currently active (confirmed dead before this
        returns), then start `mode` if given. mode=None just stops.

        params are forwarded as CLI args to the target script/function;
        see _extra_args_for() for the mapping.

        Validates and builds the new driver BEFORE stopping the current
        one: an unknown mode (e.g. a typo from the caller) must raise
        without touching whatever is already running, rather than
        stopping a perfectly good active mode and only then discovering
        the requested one doesn't exist.
        """
        if mode is not None and mode != "rainbow" and mode not in SUBPROCESS_MODES:
            raise ValueError(f"unknown mode: {mode}")

        with self._lock:
            if mode == "rainbow":
                driver = self._build_rainbow_driver(**params)
            elif mode in SUBPROCESS_MODES:
                driver = self._build_game_process(mode, **params)
            else:
                driver = None

            if self._active is not None:
                self._active.stop()
                self._active = None
                self._active_mode = None

            if driver is None:
                return

            driver.start()
            self._active = driver
            self._active_mode = mode

    def stop(self) -> None:
        self.switch_to(None)

    def _build_game_process(self, mode: str, **params) -> GameProcess:
        script_path = SUBPROCESS_MODES[mode]
        extra_args = _params_to_cli_args(params)
        return GameProcess(mode, script_path, extra_args)

    def _build_rainbow_driver(self, **params) -> ThreadDriver:
        import argparse as _argparse

        import rainbow_wall

        defaults = {
            "layout": str(REPO_ROOT / "wall_layout.json"),
            "host": None,
            "port": 4210,
            "width": 64,
            "height": 64,
            "fps": 30.0,
            "chunk_size": 1024,
            "protocol": "brcp",
            "speed": 24.0,
            "mirror_port": DEFAULT_MIRROR_PORT,
            "max_frames": 0,
        }
        defaults.update(params)
        ns = _argparse.Namespace(**defaults)
        return ThreadDriver("rainbow", rainbow_wall.run, (ns,))


def _params_to_cli_args(params: dict) -> list:
    """Translate {"width": 64, "no_stream": True} into ["--width", "64", "--no-stream"]."""
    args = []
    for key, value in params.items():
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                args.append(flag)
        elif value is not None:
            args.extend([flag, str(value)])
    return args

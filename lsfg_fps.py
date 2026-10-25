# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""The frame rate you see, from gamescope's stats pipe (gamescope -T .../stats.pipe writes "fps=<n>" lines).

gamescope counts the frames the game hands it, so with lsfg-vk this is the generated rate; the game's own rate is
that divided by the multiplier. The pipe is read only while the FPS counter is on. Nothing on SteamOS reads it
otherwise; a second reader would split the lines between the two.
"""

import glob
import os
import re
import select
import threading
import time

_FPS = re.compile(rb"^fps=([0-9]+(?:\.[0-9]+)?)$", re.M)
STALE_S = 3.0  # gamescope writes a few lines a second; older values no longer describe the screen


def pipe_pattern():
    return f"/run/user/{os.getuid()}/gamescope.*/stats.pipe"


def label(fps, multiplier):
    """"base / shown FPS" while frame generation runs, "shown FPS" without it; "" hides the counter."""
    if fps is None:
        return ""
    whole = lambda value: int(value + 0.5)  # noqa: E731 - round half up, as people read a counter
    return f"{whole(fps / multiplier)} / {whole(fps)} FPS" if multiplier > 1 else f"{whole(fps)} FPS"


def last_fps(data):
    """The newest fps value in a chunk of the pipe's text, or None."""
    values = _FPS.findall(data)
    return float(values[-1]) if values else None


class Reader:
    def __init__(self, pattern):
        self.pattern = pattern
        self.fps = None
        self.at = 0.0
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="deckyls-fps", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.fps = None

    def current(self):
        """The displayed frame rate, or None when gamescope has not reported one lately."""
        return self.fps if self.fps is not None and time.monotonic() - self.at < STALE_S else None

    def _run(self):
        while not self._stop.is_set():
            path = next(iter(sorted(glob.glob(self.pattern))), None)
            if path is None:
                self._stop.wait(2.0)
                continue
            try:
                self._read(path)
            except OSError:
                self._stop.wait(2.0)

    def _read(self, path):
        # Non-blocking open: a FIFO without a writer would otherwise block here, and stop() could not end it.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            pending = b""
            while not self._stop.is_set():
                ready, _, _ = select.select([fd], [], [], 1.0)
                if not ready:
                    continue
                chunk = os.read(fd, 4096)
                if not chunk:  # no writer at the moment (gamescope opens its end once a reader exists)
                    self._stop.wait(0.5)
                    continue
                pending += chunk
                complete, _, pending = pending.rpartition(b"\n")
                value = last_fps(complete)
                if value is not None:
                    self.fps, self.at = value, time.monotonic()
        finally:
            os.close(fd)

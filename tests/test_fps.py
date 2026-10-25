# SPDX-License-Identifier: BSD-3-Clause
import os
import tempfile
import threading
import time
import unittest

import _harness  # noqa: F401
import lsfg_fps


class FpsTest(unittest.TestCase):
    def test_newest_whole_fps_line_wins(self):
        self.assertEqual(lsfg_fps.last_fps(b"fps=20.4\nfocus=steam\nfps=143.95\nfocus=steam\n"), 143.95)
        self.assertEqual(lsfg_fps.last_fps(b"fps=60\n"), 60.0)
        self.assertIsNone(lsfg_fps.last_fps(b"focus=steam\nfps=abc\nxfps=5\n"))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "needs POSIX FIFOs")
    def test_reader_follows_gamescope_pipe_and_stops(self):
        folder = tempfile.mkdtemp()
        os.mkdir(os.path.join(folder, "gamescope.x"))
        pipe = os.path.join(folder, "gamescope.x", "stats.pipe")
        os.mkfifo(pipe)
        reader = lsfg_fps.Reader(os.path.join(folder, "gamescope.*", "stats.pipe"))
        reader.start()

        def gamescope():
            with open(pipe, "wb", buffering=0) as w:  # blocks until the reader has opened its end
                w.write(b"fps=120.5\nfocus=steam\nfps=1")  # a line cut in half must wait for its end
                time.sleep(0.3)
                w.write(b"44.0\n")
                time.sleep(0.3)

        writer = threading.Thread(target=gamescope)
        writer.start()
        deadline = time.monotonic() + 5
        while reader.current() != 144.0 and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(reader.current(), 144.0)
        writer.join()
        reader.stop()
        self.assertIsNone(reader.current())
        reader._thread.join(3)
        self.assertFalse(reader._thread.is_alive(), "stop() ends the reader even with no writer")

    def test_stale_reading_is_not_shown(self):
        reader = lsfg_fps.Reader("")
        reader.fps, reader.at = 90.0, time.monotonic() - lsfg_fps.STALE_S - 1
        self.assertIsNone(reader.current())


if __name__ == "__main__":
    unittest.main()

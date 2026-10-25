# SPDX-License-Identifier: BSD-3-Clause
import os
import tempfile
import unittest

import _harness  # noqa: F401
import lsfg_mangohud as m


class MangoHudTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def test_presets_extend_levels_2_to_4_with_the_line_first(self):
        text = m.presets()
        self.assertTrue(text.startswith(m.MARKER))
        self.assertNotIn("[preset 1]", text, "level 1 (the FPS number alone) stays Steam's")
        for level in (2, 3, 4):
            section = text.split(f"[preset {level}]\n", 1)[1].split("\n\n", 1)[0].splitlines()
            # MangoHud draws in file order; after inherit the line would fall off level 2's bar.
            self.assertEqual([line.split("=", 1)[0] for line in section], ["exec", "inherit"])
            self.assertIn('"$XDG_RUNTIME_DIR/deckyls/fps"', section[0])
            self.assertNotIn("#", section[0], "MangoHud cuts lines at #")

    def test_only_our_own_presets_file_is_written_or_removed(self):
        path = os.path.join(self.dir, "MangoHud", "presets.conf")
        self.assertTrue(m.install(path))
        self.assertTrue(m.install(path), "rewriting our own file is fine")
        m.remove(path)
        self.assertFalse(os.path.exists(path))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("[preset 3]\nfull\n")
        self.assertFalse(m.install(path))
        m.remove(path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "[preset 3]\nfull\n")

    def test_text_file_appears_and_goes(self):
        path = m.text_path(self.dir)
        m.write_text(path, "LSFG 2x - base 60 FPS")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "LSFG 2x - base 60 FPS\n")
        m.write_text(path, "")
        self.assertFalse(os.path.exists(path))
        m.write_text(path, "")  # already gone

    def test_overlay_config_is_rewritten_unchanged(self):
        config = os.path.join(self.dir, "gamescope.abc", "mangohud.config")
        os.makedirs(os.path.dirname(config))
        with open(config, "w", encoding="utf-8") as f:
            f.write("control=mangohud\npreset=2\n")
        m.reload_overlay(self.dir)
        with open(config, encoding="utf-8") as f:
            self.assertEqual(f.read(), "control=mangohud\npreset=2\n")


if __name__ == "__main__":
    unittest.main()

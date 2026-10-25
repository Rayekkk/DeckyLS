# SPDX-License-Identifier: BSD-3-Clause
import asyncio
import os
import tomllib
import unittest

import _harness  # noqa: F401
import main


class MainTest(unittest.TestCase):
    def setUp(self):
        self.plugin = main.Plugin()
        asyncio.run(self.plugin._main())
        try:
            os.remove(self.plugin.config_path)
        except FileNotFoundError:
            pass

    def call(self, *args, **kw):
        return asyncio.run(self.plugin.set_profile(*args, **kw))

    def test_running_game_gets_a_profile_and_its_state(self):
        state = self.call(["1809540"], "Nine Sols", 3, 0.8, True, appid=1809540)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["game"]["settings"]["multiplier"], 3)
        self.assertEqual(state["game"]["ids"], ["1809540"])
        with open(self.plugin.config_path, "rb") as f:
            self.assertEqual(tomllib.load(f)["profile"][0]["flow_scale"], 0.8)

    def test_bad_input_from_the_panel_never_reaches_the_file(self):
        for args in ((["1"], "x", 5, 1.0, True), (["1"], "x", True, 1.0, True), (["1"], "x", 2, 0.1, True),
                     (["1"], "x", 2, float("nan"), True), (["1"], "x", 2, 1.0, "yes"), ([], "x", 2, 1.0, True),
                     ([1], "x", 2, 1.0, True), ("1", "x", 2, 1.0, True), (["1"], None, 2, 1.0, True)):
            state = self.call(*args)
            self.assertEqual(state["error"], "Invalid settings were rejected.", args)
        self.assertFalse(os.path.exists(self.plugin.config_path))

    def test_non_steam_games_are_matched_by_exe_too(self):
        self.assertEqual(main._ids(1809540, "NineSols.exe"), ["1809540"])
        self.assertEqual(main._ids(0x80000001, "Game.exe"), [str(0x80000001), "Game.exe"])
        self.assertEqual(main._ids(0x80000001, ""), [str(0x80000001)])


if __name__ == "__main__":
    unittest.main()

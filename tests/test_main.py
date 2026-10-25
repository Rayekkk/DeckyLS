# SPDX-License-Identifier: BSD-3-Clause
import asyncio
import os
import tomllib
import unittest

import _harness  # noqa: F401
import lsfg_config
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

    def test_list_switch_prepares_and_removes_a_game_without_touching_the_running_one(self):
        self.call(["1145360"], "Hades", 1, 1.0, True, appid=1809540, game_name="Nine Sols")
        state = asyncio.run(self.plugin.remove_profile(["1145360"], 1809540, "Nine Sols"))
        self.assertEqual((state["error"], state["game"]["name"]), ("", "Nine Sols"))
        with open(self.plugin.config_path, "rb") as f:
            self.assertEqual(tomllib.load(f)["profile"], [lsfg_config.PLACEHOLDER])
        self.assertFalse(any(e["name"] == lsfg_config.PLACEHOLDER["name"] for e in state["games"]))
        bad = asyncio.run(self.plugin.remove_profile("1145360", 0, ""))
        self.assertEqual(bad["error"], "Invalid settings were rejected.")

    def test_library_has_every_game_with_its_settings_and_unmatched_profiles(self):
        data = {"version": 2, "global": {}, "profile": [
            {"name": "Nine Sols", "active_in": "1809540", "multiplier": 3},
            {"name": "genshin", "active_in": ["GenshinImpact.exe"]},
            {"name": "empty", "active_in": []}]}
        games = [{"appid": 1809540, "name": "Nine Sols", "exe": ""}, {"appid": 1145360, "name": "Hades", "exe": ""},
                 {"appid": 0x80000001, "name": "Ärger", "exe": "Arger.exe"}]
        library = {e["name"]: e for e in main._library(games, data)}
        self.assertEqual(sorted(library), ["Hades", "Nine Sols", "genshin", "Ärger"], "no 'empty' profile without ids")
        self.assertEqual(library["Nine Sols"]["settings"]["multiplier"], 3)
        self.assertIsNone(library["Hades"]["settings"])
        self.assertEqual((library["genshin"]["appid"], library["genshin"]["ids"]), (0, ["GenshinImpact.exe"]))
        self.assertEqual(library["Ärger"]["ids"], [str(0x80000001), "Arger.exe"])
        self.assertTrue(all(e["settings"] is None for e in main._library(games, None)))

    def test_non_steam_games_are_matched_by_exe_too(self):
        self.assertEqual(main._ids(1809540, "NineSols.exe"), ["1809540"])
        self.assertEqual(main._ids(0x80000001, "Game.exe"), [str(0x80000001), "Game.exe"])
        self.assertEqual(main._ids(0x80000001, ""), [str(0x80000001)])


if __name__ == "__main__":
    unittest.main()

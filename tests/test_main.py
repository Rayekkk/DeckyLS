# SPDX-License-Identifier: BSD-3-Clause
import asyncio
import os
import tomllib
import unittest

import _harness  # noqa: F401
import lsfg_config
import main


def settings(**changes):
    return {"multiplier": 2, "flow_scale": 1.0, "performance_mode": True, "override_present_mode": True,
            "preserve_swapchain_image_count": False, **changes}


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

    def saved(self):
        with open(self.plugin.config_path, "rb") as f:
            return tomllib.load(f)

    def test_running_game_gets_a_profile_and_its_state(self):
        state = self.call(["1809540"], "Nine Sols", settings(multiplier=8, flow_scale=0.8,
                                                             preserve_swapchain_image_count=True), appid=1809540)
        self.assertEqual(state["error"], "")
        self.assertEqual(state["game"]["settings"]["multiplier"], 8)
        self.assertEqual(state["game"]["ids"], ["1809540"])
        profile = self.saved()["profile"][0]
        self.assertEqual((profile["flow_scale"], profile["preserve_swapchain_image_count"], profile["override_present_mode"]),
                         (0.8, True, True))

    def test_bad_input_from_the_panel_never_reaches_the_file(self):
        bad = [settings(multiplier=9), settings(multiplier=0), settings(multiplier=True), settings(multiplier=2.0),
               settings(flow_scale=0.1), settings(flow_scale=float("nan")), settings(flow_scale=True),
               settings(performance_mode="yes"), settings(override_present_mode=1),
               settings(preserve_swapchain_image_count=None), settings(extra=1), {"multiplier": 2}, None]
        for value in bad:
            self.assertEqual(self.call(["1"], "x", value)["error"], "Invalid settings were rejected.", value)
        for ids, name in (([], "x"), ([1], "x"), ("1", "x"), (["1"], None)):
            self.assertEqual(self.call(ids, name, settings())["error"], "Invalid settings were rejected.", ids)
        self.assertEqual(asyncio.run(self.plugin.set_fp16("no"))["error"], "Invalid settings were rejected.")
        self.assertFalse(os.path.exists(self.plugin.config_path))

    def test_fp16_is_a_global_switch_that_keeps_the_profiles(self):
        self.assertTrue(asyncio.run(self.plugin.get_state())["allow_fp16"], "lsfg-vk's default is on")
        self.call(["1"], "x", settings())
        state = asyncio.run(self.plugin.set_fp16(False))
        self.assertFalse(state["allow_fp16"])
        self.assertEqual(self.saved()["global"], {"allow_fp16": False})
        self.assertEqual(self.saved()["profile"][0]["name"], "x")

    def test_fps_counter_switch_is_remembered_and_shows_nothing_while_off(self):
        self.assertFalse(asyncio.run(self.plugin.get_state())["fps_counter"])
        self.plugin.fps.fps, self.plugin.fps.at = 120.0, main.time.monotonic()
        self.assertEqual(asyncio.run(self.plugin.get_fps(1809540)), {"fps": None, "multiplier": 1})
        try:
            self.assertTrue(asyncio.run(self.plugin.set_fps_counter(True))["fps_counter"])
            self.plugin.fps.fps, self.plugin.fps.at = 120.0, main.time.monotonic()
            # lsfg-vk has not joined this game (no such process here), so no base rate is claimed.
            self.assertEqual(asyncio.run(self.plugin.get_fps(1809540)), {"fps": 120.0, "multiplier": 1})
            again = main.Plugin()
            asyncio.run(again._main())
            self.assertTrue(again.fps_counter, "the switch survives a restart")
            again.fps.stop()
            self.assertEqual(asyncio.run(self.plugin.set_fps_counter("on"))["error"], "Invalid settings were rejected.")
        finally:
            asyncio.run(self.plugin.set_fps_counter(False))

    def test_counter_uses_the_multiplier_of_the_profile_lsfg_vk_joined(self):
        self.call(["1809540"], "Nine Sols", settings(multiplier=3))
        self.plugin.live = {1809540: {"ids": ["1809540"], "attached": ("Nine Sols", "Steam App ID"),
                                      "checked": main.time.monotonic()}}
        self.assertEqual(asyncio.run(self.plugin._live_multiplier(1809540)), 3)
        self.call(["1809540"], "Nine Sols", settings(multiplier=1))
        self.assertEqual(asyncio.run(self.plugin._live_multiplier(1809540)), 1)
        self.assertEqual(asyncio.run(self.plugin._live_multiplier(0)), 1)

    def test_list_switch_prepares_and_removes_a_game_without_touching_the_running_one(self):
        self.call(["1145360"], "Hades", settings(multiplier=1), appid=1809540, game_name="Nine Sols")
        state = asyncio.run(self.plugin.remove_profile(["1145360"], 1809540, "Nine Sols"))
        self.assertEqual((state["error"], state["game"]["name"]), ("", "Nine Sols"))
        self.assertEqual(self.saved()["profile"], [lsfg_config.PLACEHOLDER])
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
        # Keys a profile leaves out show what lsfg-vk itself uses, not DeckyLS's choices for new games.
        self.assertEqual({k: v for k, v in library["Nine Sols"]["settings"].items() if k not in ("name", "ids")},
                         {**main.LSFG_DEFAULTS, "multiplier": 3})
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

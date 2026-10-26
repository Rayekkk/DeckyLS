# SPDX-License-Identifier: BSD-3-Clause
import asyncio
import os
import tomllib
import unittest
from unittest import mock

import _harness  # noqa: F401
import lsfg_config
import main
from test_install import archive


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

    def test_update_replaces_old_files_and_remove_cleans_up(self):
        local = os.path.join(main._home(), ".local")
        old = archive(("./bin/lsfg-vk-cli", "cli 1"), ("./lib/liblsfg-vk-layer.so", "v1"), ("./lib/only-in-v1.so", "x"))
        new = archive(("./bin/lsfg-vk-cli", "cli 2"), ("./lib/liblsfg-vk-layer.so", "v2"), ("./lib/only-in-v2.so", "y"))
        other = os.path.join(local, "lib", "someone-elses.so")
        os.makedirs(os.path.dirname(other), exist_ok=True)
        with open(other, "w") as f:
            f.write("keep")
        path = lambda *p: os.path.join(local, *p)  # noqa: E731
        try:
            with mock.patch.object(main.lsfg_install, "download", return_value=old):
                self.assertEqual(asyncio.run(self.plugin.install_lsfg())["error"], "")
            self.assertTrue(os.path.exists(path("lib", "only-in-v1.so")))
            with mock.patch.object(main.lsfg_install, "download", return_value=new):
                self.assertEqual(asyncio.run(self.plugin.install_lsfg())["error"], "", "an update of our own install")
            self.assertFalse(os.path.exists(path("lib", "only-in-v1.so")), "files the new release dropped go")
            for name in ("only-in-v2.so", "liblsfg-vk-layer.so"):
                self.assertTrue(os.path.exists(path("lib", name)), name)
            with open(path("lib", "liblsfg-vk-layer.so")) as f:
                self.assertEqual(f.read(), "v2")
            asyncio.run(self.plugin.remove_lsfg())
            self.assertEqual([n for n in os.listdir(path("lib"))], ["someone-elses.so"])
            self.assertFalse(os.path.exists(path("bin", "lsfg-vk-cli")))
            self.assertFalse(self.plugin.manifest.files)
        finally:
            os.remove(other)

    def test_healthcheck_and_journal_are_not_redone_on_every_poll(self):
        cli = os.path.join(main._home(), "lsfg-vk-cli")
        os.makedirs(main._home(), exist_ok=True)
        with open(cli, "w") as f:
            f.write("cli")
        game = {"exe": "", "started": 1000.0}
        joined = ["steam: (lsfg-vk) [INFO]: Using profile with name 'Nine Sols' (identified via Steam App ID)"]
        with mock.patch.object(main.lsfg_install, "find_cli", return_value=cli), \
                mock.patch.object(main.lsfg_install, "healthcheck", return_value={"ok": True, "text": "", "version": "2"}) as health, \
                mock.patch.object(main.lsfg_status, "find_game", return_value=game), \
                mock.patch.object(main.lsfg_status, "journal_since", return_value=[]) as journal:
            # A game without a profile, or set to Off, shows "Off": the journal is not read at all.
            asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.call(["1809540"], "Nine Sols", settings(multiplier=1))
            asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.assertEqual(journal.call_count, 0)
            self.call(["1809540"], "Nine Sols", settings(multiplier=2))
            for _ in range(3):
                asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.assertEqual((health.call_count, journal.call_count), (1, 1), "no rereads within seconds")
            os.utime(cli, ns=(0, 10 ** 9))  # lsfg-vk replaced: checked again
            asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.assertEqual(health.call_count, 2)
            # Not joined yet: looked up again after 10 s; once joined, remembered for the session.
            journal.return_value = joined
            with mock.patch.object(main.time, "monotonic", return_value=main.time.monotonic() + 11):
                for _ in range(3):
                    state = asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.assertEqual(journal.call_count, 2)
            self.assertEqual(state["game"]["attached"], {"profile": "Nine Sols", "via": "Steam App ID"})
            game["started"] = 2000.0  # the game was restarted: a new session is looked up
            asyncio.run(self.plugin.get_state(1809540, "Nine Sols"))
            self.assertEqual(journal.call_count, 3)
        os.remove(cli)

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

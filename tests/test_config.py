# SPDX-License-Identifier: BSD-3-Clause
import os
import tempfile
import tomllib
import unittest

import _harness  # noqa: F401
import lsfg_config as c

USER_FILE = """# my own notes
version = 2

[global]
allow_fp16 = false
dll = "/games/Lossless Scaling/lsfg-vk.dll"

[[profile]]
name = "Genshin \\"Impact\\""
active_in = ["GenshinImpact.exe", "vkcube"]
multiplier = 3
pacing_mode = "none"
"""


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "lsfg-vk", "conf.toml")

    def write(self, text):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_new_file_gets_one_profile_lsfg_vk_accepts(self):
        data = c.load(self.path)
        c.set_profile(data, "Nine Sols", ["1809540"], {"multiplier": 2, "flow_scale": 1.0, "performance_mode": True})
        c.save(self.path, data)
        with open(self.path, "rb") as f:
            saved = tomllib.load(f)
        self.assertEqual(saved, {"version": 2, "global": {}, "profile": [
            {"name": "Nine Sols", "active_in": "1809540", "multiplier": 2, "flow_scale": 1.0,
             "performance_mode": True}]})
        self.assertFalse(os.path.exists(self.path + c.BACKUP_SUFFIX))

    def test_user_profiles_and_keys_survive_and_original_is_backed_up(self):
        self.write(USER_FILE)
        data = c.load(self.path)
        c.set_profile(data, "Nine Sols", ["1809540"], {"multiplier": 3, "flow_scale": 0.85, "performance_mode": False})
        c.save(self.path, data)
        with open(self.path, "rb") as f:
            saved = tomllib.load(f)
        self.assertEqual(saved["global"], {"allow_fp16": False, "dll": "/games/Lossless Scaling/lsfg-vk.dll"})
        self.assertEqual(saved["profile"][0], tomllib.loads(USER_FILE)["profile"][0])
        self.assertEqual(saved["profile"][1]["flow_scale"], 0.85)
        with open(self.path + c.BACKUP_SUFFIX, encoding="utf-8") as f:
            self.assertEqual(f.read(), USER_FILE)

    def test_existing_profile_is_changed_in_place_and_gains_new_ids(self):
        self.write(USER_FILE)
        data = c.load(self.path)
        c.set_profile(data, "ignored", ["vkcube", "123"], {"multiplier": 1, "flow_scale": 1.0, "performance_mode": True})
        self.assertEqual(len(data["profile"]), 1)
        p = data["profile"][0]
        self.assertEqual(p["name"], 'Genshin "Impact"')
        self.assertEqual(p["active_in"], ["GenshinImpact.exe", "vkcube", "123"])
        self.assertEqual((p["multiplier"], p["pacing_mode"]), (1, "none"))

    def test_turning_a_game_off_removes_only_its_ids_and_never_leaves_the_file_without_profiles(self):
        self.write(USER_FILE)
        data = c.load(self.path)
        c.set_profile(data, "Nine Sols", ["1809540"], {"multiplier": 1, "flow_scale": 1.0, "performance_mode": True})
        c.remove_ids(data, ["vkcube"])
        self.assertEqual(data["profile"][0]["active_in"], "GenshinImpact.exe", "the shared profile keeps its other game")
        c.remove_ids(data, ["GenshinImpact.exe", "1809540"])
        self.assertEqual(data["profile"], [c.PLACEHOLDER])
        c.save(self.path, data)
        self.assertTrue(c.is_placeholder(c.load(self.path)["profile"][0]))
        data = c.load(self.path)
        c.set_profile(data, "Hades", ["1145360"], {"multiplier": 1, "flow_scale": 1.0, "performance_mode": True})
        self.assertEqual([p["name"] for p in data["profile"]], ["Hades"], "the placeholder goes once a game is back")

    def test_unreadable_or_foreign_file_is_never_overwritten(self):
        for text in ("version = 2\n[global\n", "version = 1\n", "version = 2\nglobal = 3\n"):
            self.write(text)
            with self.assertRaises(c.ConfigError):
                c.load(self.path)

    def test_a_file_that_cannot_be_opened_is_named_without_its_full_path(self):
        os.makedirs(self.path)  # a folder where the file should be: opening it fails with an OSError
        with self.assertRaises(c.ConfigError) as caught:
            c.load(self.path)
        self.assertTrue(str(caught.exception).startswith("~/.config/lsfg-vk/conf.toml cannot be read ("))
        self.assertNotIn(self.dir, str(caught.exception))

    def test_values_toml_cannot_round_trip_are_refused_before_writing(self):
        self.write(USER_FILE)
        data = c.load(self.path)
        data["global"]["weird"] = {"nested": 1}
        with self.assertRaises(c.ConfigError):
            c.save(self.path, data)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), USER_FILE)

    def test_names_with_quotes_newlines_and_unicode_round_trip(self):
        data = c.load(self.path)
        name = 'Ä "quoted" \\ back\nslash ✓ del\x7f'
        c.set_profile(data, name, ["1"], {"multiplier": 2, "flow_scale": 1.0, "performance_mode": True})
        self.assertEqual(tomllib.loads(c.dumps(data))["profile"][0]["name"], name)


if __name__ == "__main__":
    unittest.main()

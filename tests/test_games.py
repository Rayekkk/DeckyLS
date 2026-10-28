# SPDX-License-Identifier: BSD-3-Clause
import os
import pathlib
import struct
import tempfile
import unittest
from unittest import mock

import _harness  # noqa: F401
import lsfg_games as g


def manifest(appid, name):
    return (f'"AppState"\n{{\n\t"appid"\t\t"{appid}"\n\t"name"\t\t"{name}"\n\t"InstalledDepots"\n\t{{\n'
            f'\t\t"1"\n\t\t{{\n\t\t\t"name"\t\t"depot"\n\t\t}}\n\t}}\n}}\n')


def kv(entries):
    """Binary KeyValues for a dict of str/int/dict values."""
    out = b""
    for key, value in entries.items():
        k = key.encode() + b"\0"
        if isinstance(value, dict):
            out += b"\x00" + k + kv(value) + b"\x08"
        elif isinstance(value, int):
            out += b"\x02" + k + struct.pack("<I", value)
        else:
            out += b"\x01" + k + value.encode() + b"\0"
    return out


class GamesTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.steam = pathlib.Path(self.home, ".local/share/Steam")
        (self.steam / "steamapps").mkdir(parents=True)

    def test_apps_in_every_library_without_lossless_scaling(self):
        # Steam tools stay in this list; the panel leaves them out by the app type Steam gives it.
        sd = pathlib.Path(self.home, "sd")
        (sd / "steamapps").mkdir(parents=True)
        (self.steam / "steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % sd.as_posix())
        for folder, appid, name in ((self.steam, 1809540, "Nine Sols"), (sd, 1145360, 'Hades \\"II\\"'),
                                    (self.steam, 993090, "Lossless Scaling"), (sd, 1493710, "Proton Experimental")):
            (folder / f"steamapps/appmanifest_{appid}.acf").write_text(manifest(appid, name), encoding="utf-8")
        (self.steam / "steamapps/appmanifest_1.acf").write_text("broken")
        found = sorted((x["appid"], x["name"], x["exe"]) for x in g.steam_games(self.home))
        self.assertEqual(found, [(1145360, 'Hades "II"', ""), (1493710, "Proton Experimental", ""),
                                 (1809540, "Nine Sols", "")])

    def test_shortcuts_give_their_windows_exe(self):
        config = self.steam / "userdata/123/config"
        config.mkdir(parents=True)
        (config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\0" + kv({
            "0": {"appid": 0x80000001, "AppName": "Game", "Exe": '"/games/My Game/Game.EXE"', "tags": {"0": "fav"}},
            "1": {"appid": 0x80000002, "AppName": "Emulator", "Exe": '"/usr/bin/flatpak"', "LaunchOptions": "run x"},
            "2": {"AppName": "no id"},
        }) + b"\x08\x08")
        self.assertEqual(sorted(g.shortcut_games(self.home), key=lambda x: x["appid"]), [
            {"appid": 0x80000001, "name": "Game", "exe": "Game.EXE"},
            {"appid": 0x80000002, "name": "Emulator", "exe": ""}])

    def test_library_is_read_again_only_when_a_game_or_shortcut_comes_or_goes(self):
        apps = self.steam / "steamapps"
        (apps / "appmanifest_1809540.acf").write_text(manifest(1809540, "Nine Sols"), encoding="utf-8")
        self.assertEqual([x["name"] for x in g.installed(self.home)], ["Nine Sols"])
        with mock.patch.object(g, "steam_games", wraps=g.steam_games) as scan:
            g.installed(self.home)
            self.assertEqual(scan.call_count, 0, "the 5 s poll does not scan the libraries")
            (apps / "appmanifest_1145360.acf").write_text(manifest(1145360, "Hades"), encoding="utf-8")
            os.utime(apps, ns=(0, os.stat(apps).st_mtime_ns + 10 ** 9))
            self.assertEqual(sorted(x["name"] for x in g.installed(self.home)), ["Hades", "Nine Sols"])
            config = self.steam / "userdata/123/config"
            config.mkdir(parents=True)
            (config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\0" + kv({
                "0": {"appid": 0x80000001, "AppName": "Game", "Exe": "Game.exe"}}) + b"\x08\x08")
            self.assertIn("Game", [x["name"] for x in g.installed(self.home)], "a new shortcut is seen")
            self.assertEqual(scan.call_count, 2)

    def test_unreadable_shortcuts_are_skipped(self):
        config = self.steam / "userdata/123/config"
        config.mkdir(parents=True)
        (config / "shortcuts.vdf").write_bytes(b"\x00shortcuts\0\x09bad")
        self.assertEqual(g.shortcut_games(self.home), [])


if __name__ == "__main__":
    unittest.main()

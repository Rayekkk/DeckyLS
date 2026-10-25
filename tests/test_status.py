# SPDX-License-Identifier: BSD-3-Clause
import json
import os
import pathlib
import tempfile
import unittest

import _harness  # noqa: F401
import lsfg_status as s

REAPER_PROTON = ["/bin/bash", "/home/deck/.dlo/run"], [
    "/home/deck/.local/share/Steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=1809540", "--",
    "/x/SteamLinuxRuntime_4/_v2-entry-point", "--verb=waitforexitandrun", "--", "/x/Proton 11.0/proton",
    "waitforexitandrun", "/games/Nine Sols/NineSols.exe", "-screen-fullscreen", ""]
REAPER_NATIVE = ["/home/deck/.local/share/Steam/ubuntu12_32/reaper", "SteamLaunch", "AppId=3000000001", "--",
                 "/x/_v2-entry-point", "--verb=waitforexitandrun", "--", "/emu/RetroArch.AppImage", "-f", ""]


class StatusTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def proc(self, pid, argv, starttime=500):
        d = pathlib.Path(self.root, "proc", str(pid))
        d.mkdir(parents=True)
        (d / "cmdline").write_bytes("\0".join(argv).encode())
        fields = ["S"] + ["0"] * 18 + [str(starttime)]
        (d / "stat").write_text(f"{pid} (rea per) " + " ".join(fields))

    def test_running_game_is_found_by_its_reaper_with_the_launched_exe(self):
        pathlib.Path(self.root, "proc").mkdir()
        pathlib.Path(self.root, "proc", "stat").write_text("cpu 1 2\nbtime 1700000000\n")
        wrapper, reaper = REAPER_PROTON
        self.proc(10, wrapper + ["AppId=1809540"])  # the wrapper is not the reaper
        self.proc(11, reaper)
        self.proc(12, REAPER_NATIVE)
        game = s.find_game(1809540, os.path.join(self.root, "proc"))
        self.assertEqual(game["exe"], "NineSols.exe")
        self.assertAlmostEqual(game["started"], 1700000000 + 500 / os.sysconf("SC_CLK_TCK")
                               if hasattr(os, "sysconf") else 0.0)
        self.assertEqual(s.find_game(3000000001, os.path.join(self.root, "proc"))["exe"], "RetroArch.AppImage")
        self.assertIsNone(s.find_game(180954, os.path.join(self.root, "proc")))  # AppId=1809540 is not 180954
        self.assertIn(s.running_appid(os.path.join(self.root, "proc")), (1809540, 3000000001), "a reaper, not the wrapper")
        self.assertEqual(s.running_appid(os.path.join(self.root, "nothing")), 0)

    def test_latest_using_profile_line_wins(self):
        lines = ["steam: (lsfg-vk) [INFO]: Using profile with name 'Old' (identified via executable)",
                 "steam: (lsfg-vk) [INFO]:   Multiplier: 2",
                 "steam: (lsfg-vk) [INFO]: Using profile with name 'It's (2)' (identified via Steam App ID)"]
        self.assertEqual(s.attached_profile(lines), ("It's (2)", "Steam App ID"))
        self.assertIsNone(s.attached_profile(lines[1:2]))

    def test_lossless_scaling_branch_is_told_apart(self):
        home = self.root
        common = pathlib.Path(home, ".local/share/Steam/steamapps/common")
        sd = pathlib.Path(home, "sd")
        common.mkdir(parents=True)
        pathlib.Path(home, ".local/share/Steam/steamapps/libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % sd.as_posix())
        self.assertEqual(s.lossless_scaling(home), {"installed": False, "dll": ""})
        (sd / "steamapps/common/Lossless Scaling").mkdir(parents=True)
        self.assertEqual(s.lossless_scaling(home), {"installed": True, "dll": ""})
        dll = sd / "steamapps/common/Lossless Scaling/lsfg-vk.dll"
        dll.write_bytes(b"MZ")
        found = s.lossless_scaling(home)
        self.assertTrue(found["installed"])
        self.assertTrue(os.path.samefile(found["dll"], dll))

    def test_other_lsfg_plugins_are_named_but_not_this_one(self):
        plugins = pathlib.Path(self.root, "plugins")
        for folder, name in (("DeckyLS", "DeckyLS"), ("decky-lsfg-vk", "Decky LSFG-VK"), ("Mako", "MAKO Decky"),
                             ("FSR4Injector", "FSR4 Injector")):
            (plugins / folder).mkdir(parents=True)
            (plugins / folder / "plugin.json").write_text(json.dumps({"name": name}))
        (plugins / "broken").mkdir()
        (plugins / "broken" / "plugin.json").write_text("{")
        self.assertEqual(s.rival_plugins(str(plugins / "DeckyLS")), ["MAKO Decky", "Decky LSFG-VK"])


if __name__ == "__main__":
    unittest.main()

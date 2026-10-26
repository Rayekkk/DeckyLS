# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""Installed games, read from Steam's files without starting anything: app manifests in every library, and
the non-Steam shortcuts with the executable they start (lsfg-vk can match those by it)."""

import glob
import os
import re
import struct

import lsfg_status

LOSSLESS_SCALING = 993090  # Steam tools (Proton, runtimes...) are left out by the panel, which knows app types
_FIELD = re.compile(r'^\s*"(appid|name)"\s+"((?:[^"\\]|\\.)*)"\s*$', re.M)


def _unescape(text):
    return re.sub(r"\\(.)", r"\1", text)


def steam_games(home):
    games = {}
    for library in lsfg_status.steam_libraries(home):
        for path in glob.glob(os.path.join(library, "steamapps", "appmanifest_*.acf")):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read(65536)
            except OSError:
                continue
            fields = {}
            for key, value in _FIELD.findall(text):
                fields.setdefault(key, _unescape(value))  # the app's own keys come before nested sections
            appid, name = fields.get("appid", ""), fields.get("name", "")
            if appid.isdecimal() and name and int(appid) != LOSSLESS_SCALING:
                games[int(appid)] = {"appid": int(appid), "name": name, "exe": ""}
    return list(games.values())


def _binary_vdf(data, i=0):
    """Steam's binary KeyValues: (dict, next offset). Raises ValueError on anything it does not know."""
    out = {}
    while i < len(data):
        kind = data[i]
        i += 1
        if kind == 0x08:
            return out, i
        end = data.index(b"\0", i)
        key = data[i:end].decode("utf-8", "replace")
        i = end + 1
        if kind == 0x00:
            out[key], i = _binary_vdf(data, i)
        elif kind == 0x01:
            end = data.index(b"\0", i)
            out[key], i = data[i:end].decode("utf-8", "replace"), end + 1
        elif kind == 0x02:
            out[key], i = struct.unpack_from("<I", data, i)[0], i + 4
        elif kind == 0x03:
            out[key], i = struct.unpack_from("<f", data, i)[0], i + 4
        elif kind == 0x07:
            out[key], i = struct.unpack_from("<Q", data, i)[0], i + 8
        else:
            raise ValueError(f"unknown KeyValues type {kind}")
    return out, i


def shortcut_games(home):
    """Non-Steam shortcuts of every Steam user on the device."""
    games = {}
    pattern = os.path.join(home, ".local", "share", "Steam", "userdata", "*", "config", "shortcuts.vdf")
    for path in glob.glob(pattern):
        try:
            with open(path, "rb") as f:
                root, _ = _binary_vdf(f.read())
        except (OSError, ValueError, struct.error):
            continue
        shortcuts = next((v for k, v in root.items() if k.lower() == "shortcuts"), {})
        for entry in shortcuts.values() if isinstance(shortcuts, dict) else ():
            if not isinstance(entry, dict):
                continue
            fields = {k.lower(): v for k, v in entry.items()}
            appid, name = fields.get("appid"), fields.get("appname")
            if not isinstance(appid, int) or not isinstance(name, str) or not name:
                continue
            exe = str(fields.get("exe", "")).strip().strip('"').replace("\\", "/").rsplit("/", 1)[-1]
            # Only a Windows .exe is a name lsfg-vk will see; a launcher such as flatpak or a script is not.
            games[appid] = {"appid": appid, "name": name, "exe": exe if exe.lower().endswith(".exe") else ""}
    return list(games.values())


def installed(home):
    return steam_games(home) + shortcut_games(home)

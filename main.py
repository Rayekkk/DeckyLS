# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""DeckyLS - Lossless Scaling frame generation (official lsfg-vk 2.0) for the game you are playing.

lsfg-vk is a Vulkan layer that picks its profile by Steam App ID or executable and reloads its config file in
running games. So DeckyLS only installs lsfg-vk and edits that file: no launch options, no environment variables.
"""

import asyncio
import json
import math
import os
import sys

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import lsfg_config  # noqa: E402
import lsfg_games  # noqa: E402
import lsfg_install  # noqa: E402
import lsfg_status  # noqa: E402

try:
    with open(os.path.join(PLUGIN_DIR, "plugin.json"), encoding="utf-8") as _f:
        VERSION = json.load(_f)["version"]
except (OSError, ValueError, KeyError):
    VERSION = "0.0.0"

MAX_MULTIPLIER = 8  # lsfg-vk has no limit; past 8x a handheld's base frame rate is too low to be worth it
# What lsfg-vk uses for a key a profile leaves out (lsfg-vk.dev/docs/configuration/configuration-options).
LSFG_DEFAULTS = {"multiplier": 2, "flow_scale": 1.0, "performance_mode": False, "override_present_mode": True,
                 "preserve_swapchain_image_count": False}
SWITCHES = ("performance_mode", "override_present_mode", "preserve_swapchain_image_count")
SHORTCUT_BIT = 0x80000000  # non-Steam shortcuts have the top bit of their app id set


def _home():
    return getattr(decky, "DECKY_USER_HOME", os.path.expanduser("~"))


def _ids(appid, exe):
    """What lsfg-vk should match the game by: the App ID, plus the executable for non-Steam games, whose
    App ID Steam may not pass to the game."""
    ids = [str(appid)]
    if appid & SHORTCUT_BIT and exe:
        ids.append(exe)
    return ids


def _valid_ids(ids):
    return isinstance(ids, list) and 1 <= len(ids) <= 8 and all(isinstance(i, str) and 0 < len(i) <= 128 for i in ids)


def _settings(value):
    """The panel's settings for one game, checked and normalised, or None when anything is off."""
    if not isinstance(value, dict) or value.keys() != LSFG_DEFAULTS.keys():
        return None
    multiplier, flow = value["multiplier"], value["flow_scale"]
    if (type(multiplier) is not int or not 1 <= multiplier <= MAX_MULTIPLIER
            or type(flow) not in (int, float) or not math.isfinite(flow) or not 0.25 <= flow <= 1.0
            or any(type(value[k]) is not bool for k in SWITCHES)):
        return None
    return {**value, "flow_scale": round(float(flow), 2)}


def _view(profile):
    return {k: profile.get(k, v) for k, v in LSFG_DEFAULTS.items()} | {"name": profile.get("name", ""),
                                                                         "ids": lsfg_config.profile_ids(profile)}


def _library(games, data):
    """Every installed game with its settings (None = never set up), plus profiles that match no installed game
    (made by hand or by another tool), so they can be set up before they are started. The panel sorts them."""
    entries, matched = [], set()
    for game in games:
        ids = _ids(game["appid"], game["exe"])
        profile = lsfg_config.find(data, ids) if data else None
        if profile is not None:
            matched.add(id(profile))
        entries.append({"appid": game["appid"], "name": game["name"], "ids": ids,
                        "settings": _view(profile) if profile else None})
    for profile in data["profile"] if data else ():
        ids = lsfg_config.profile_ids(profile)
        if ids and id(profile) not in matched and not lsfg_config.is_placeholder(profile):
            entries.append({"appid": 0, "name": str(profile.get("name") or ids[0]), "ids": ids,
                            "settings": _view(profile)})
    return entries


class Plugin:
    async def _main(self):
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        self.manifest = lsfg_install.Manifest(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "installed.json"))
        self.config_path = lsfg_config.config_path(_home())
        self.lock = asyncio.Lock()
        self.busy = ""
        self.error = ""

    async def get_state(self, appid: int = 0, name: str = "") -> dict:
        home = _home()
        health = await asyncio.to_thread(lsfg_install.healthcheck, lsfg_install.find_cli(home))
        state = {
            "version": VERSION,
            "pinned": lsfg_install.LSFG_VERSION,
            "lsfg": health,
            "managed": bool(self.manifest.files),
            "managed_version": self.manifest.version,
            "busy": self.busy,
            "error": self.error,
            "lossless_scaling": lsfg_status.lossless_scaling(home),
            "rivals": lsfg_status.rival_plugins(PLUGIN_DIR),
            "config_error": "",
            "games": [],
            "game": None,
        }
        try:
            data = lsfg_config.load(self.config_path)
        except lsfg_config.ConfigError as e:
            state["config_error"] = str(e)
            data = None
        state["allow_fp16"] = bool(data["global"].get("allow_fp16", True)) if data else True
        state["games"] = _library(await asyncio.to_thread(lsfg_games.installed, home), data)
        if isinstance(appid, int) and appid > 0:
            running = await asyncio.to_thread(lsfg_status.find_game, appid)
            ids = _ids(appid, running["exe"] if running else "")
            profile = lsfg_config.find(data, ids) if data else None
            attached = None
            if running and running["started"]:
                lines = await asyncio.to_thread(lsfg_status.journal_since, running["started"])
                attached = lsfg_status.attached_profile(lines)
            state["game"] = {
                "appid": appid, "name": str(name)[:128], "ids": ids, "running": running is not None,
                "settings": _view(profile) if profile else None,
                "attached": {"profile": attached[0], "via": attached[1]} if attached else None,
            }
        return state

    async def _change(self, change, what, appid, game_name):
        """Apply change(data) to the config file; returns the state for the running game (appid, game_name)."""
        async with self.lock:
            try:
                data = lsfg_config.load(self.config_path)
                change(data)
                await asyncio.to_thread(lsfg_config.save, self.config_path, data)
                self.error = ""
                decky.logger.info(what)
            except (lsfg_config.ConfigError, OSError) as e:
                self.error = str(e)
                decky.logger.error(f"saving the lsfg-vk config failed: {e}")
        return await self.get_state(appid, game_name)

    async def set_profile(self, ids: list, name: str, settings: dict, appid: int = 0, game_name: str = "") -> dict:
        """Create or change the profile matching ids."""
        clean = _settings(settings)
        if not _valid_ids(ids) or not isinstance(name, str) or clean is None:
            self.error = "Invalid settings were rejected."
            return await self.get_state(appid, game_name)
        return await self._change(
            lambda data: lsfg_config.set_profile(data, name.strip()[:128] or ids[0], ids, clean),
            f"profile {ids}: {clean}", appid, game_name)

    async def set_fp16(self, allowed: bool, appid: int = 0, game_name: str = "") -> dict:
        """lsfg-vk's global allow_fp16: half precision, much faster on AMD GPUs at the same quality."""
        if type(allowed) is not bool:
            self.error = "Invalid settings were rejected."
            return await self.get_state(appid, game_name)
        return await self._change(lambda data: data["global"].update(allow_fp16=allowed),
                                  f"allow_fp16 = {allowed}", appid, game_name)

    async def remove_profile(self, ids: list, appid: int = 0, game_name: str = "") -> dict:
        """Keep lsfg-vk out of the game matching ids (the list's switch turned off)."""
        if not _valid_ids(ids):
            self.error = "Invalid settings were rejected."
            return await self.get_state(appid, game_name)
        return await self._change(lambda data: lsfg_config.remove_ids(data, ids), f"profile {ids}: removed",
                                  appid, game_name)

    async def install_lsfg(self, appid: int = 0, name: str = "") -> dict:
        async with self.lock:
            home = _home()
            cli = lsfg_install.find_cli(home)
            if cli and not self.manifest.files:
                self.error = "lsfg-vk is already installed by something else; DeckyLS uses that installation."
                return await self.get_state(appid, name)
            self.busy, self.error = "Downloading lsfg-vk…", ""
            try:
                archive = await asyncio.to_thread(lsfg_install.download)
                self.busy = "Installing lsfg-vk…"
                written = await asyncio.to_thread(lsfg_install.install, archive, os.path.join(home, ".local"))
                stale = [p for p in self.manifest.files if p not in written]
                await asyncio.to_thread(lsfg_install.uninstall, stale)
                self.manifest.save(lsfg_install.LSFG_VERSION, written)
                decky.logger.info(f"installed lsfg-vk {lsfg_install.LSFG_VERSION} ({len(written)} files)")
            except (lsfg_install.InstallError, OSError) as e:
                self.error = str(e)
                decky.logger.error(f"installing lsfg-vk failed: {e}")
            finally:
                self.busy = ""
        return await self.get_state(appid, name)

    async def remove_lsfg(self, appid: int = 0, name: str = "") -> dict:
        """Remove the lsfg-vk files DeckyLS installed. The config file stays: it is the user's settings."""
        async with self.lock:
            await asyncio.to_thread(lsfg_install.uninstall, self.manifest.files)
            decky.logger.info(f"removed lsfg-vk ({len(self.manifest.files)} files)")
            self.manifest.clear()
            self.error = ""
        return await self.get_state(appid, name)

    async def _unload(self):
        pass

    async def _uninstall(self):
        # Decky runs this on every plugin update too (uninstall + install), so lsfg-vk stays; "Remove lsfg-vk"
        # in the panel is the full cleanup.
        decky.logger.info("uninstall/update: leaving lsfg-vk installed")

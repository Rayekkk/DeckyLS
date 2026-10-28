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
import time

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import dk_rpc  # noqa: E402
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
INVALID = "Invalid settings were rejected."

_ready = asyncio.Event()
rpc = dk_rpc.boundary(decky.logger, _ready)


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
        try:
            self.lock = asyncio.Lock()
            self.busy = ""
            self.error = ""  # the last failed change, shown in the panel until the next change succeeds
            # The panel asks for the state every 5 s; these change rarely, so they are worked out only when needed.
            self.health = (None, None)  # (cli path and its mtime, healthcheck result)
            self.joined = {}  # (appid, game start) -> {"attached": ..., "checked": monotonic time}
            self.config_path = lsfg_config.config_path(_home())
            os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
            self.manifest = lsfg_install.Manifest(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "installed.json"))
            if self.manifest.problem:
                self.error = self.manifest.problem
                decky.logger.error(self.manifest.problem)
        finally:
            _ready.set()  # even after a failure: the calls then answer with an error instead of hanging

    async def _healthcheck(self, home):
        cli = lsfg_install.find_cli(home)
        try:
            key = (cli, os.stat(cli).st_mtime_ns) if cli else None
        except OSError:
            key = None
        if key is None or self.health[0] != key:
            self.health = (key, await asyncio.to_thread(lsfg_install.healthcheck, cli))
        return self.health[1]

    async def _attached(self, appid, started):
        """The profile lsfg-vk joined the game with: read from the journal until it has joined (at most every
        10 s), then remembered for that game session instead of rereading a journal that grows all session."""
        known = self.joined.get((appid, started))
        if known is None or (known["attached"] is None and time.monotonic() - known["checked"] >= 10):
            lines = await asyncio.to_thread(lsfg_status.journal_since, started)
            known = {"attached": lsfg_status.attached_profile(lines), "checked": time.monotonic()}
            self.joined = {(appid, started): known}
        return known["attached"]

    async def _state(self, appid, name):
        home = _home()
        health = await self._healthcheck(home)
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
            # Only a game set to 2x or more needs to know whether lsfg-vk joined it; the others show "Off".
            multiplier = profile.get("multiplier", LSFG_DEFAULTS["multiplier"]) if profile else 1
            wanted = type(multiplier) is int and multiplier > 1 and running and running["started"]
            attached = await self._attached(appid, running["started"]) if wanted else None
            state["game"] = {
                "appid": appid, "name": str(name)[:128], "ids": ids, "running": running is not None,
                "settings": _view(profile) if profile else None,
                "attached": {"profile": attached[0], "via": attached[1]} if attached else None,
            }
        return state

    async def _reply(self, appid, name):
        """The answer to a change: the new state, and the change's error when it failed."""
        state = await self._state(appid, name)
        return dk_rpc.fail(self.error, state) if self.error else dk_rpc.ok(state)

    @rpc
    async def get_state(self, appid: int = 0, name: str = "") -> dict:
        return dk_rpc.ok(await self._state(appid, name))

    async def _change(self, change, what, appid, game_name):
        """Apply change(data) to the config file; answers with the state for the running game (appid, game_name)."""
        async with self.lock:
            try:
                data = lsfg_config.load(self.config_path)
                change(data)
                await asyncio.to_thread(lsfg_config.save, self.config_path, data)
                self.error = ""
                decky.logger.info(what)
            except (lsfg_config.ConfigError, OSError, ValueError) as e:  # ValueError: a text TOML cannot hold
                self.error = str(e)
                decky.logger.error(f"saving the lsfg-vk config failed: {e}")
        return await self._reply(appid, game_name)

    @rpc
    async def set_profile(self, ids: list, name: str, settings: dict, appid: int = 0, game_name: str = "") -> dict:
        """Create or change the profile matching ids."""
        clean = _settings(settings)
        if not _valid_ids(ids) or not isinstance(name, str) or clean is None:
            self.error = INVALID
            return await self._reply(appid, game_name)
        return await self._change(
            lambda data: lsfg_config.set_profile(data, name.strip()[:128] or ids[0], ids, clean),
            f"profile {ids}: {clean}", appid, game_name)

    @rpc
    async def set_fp16(self, allowed: bool, appid: int = 0, game_name: str = "") -> dict:
        """lsfg-vk's global allow_fp16: half precision, much faster on AMD GPUs at the same quality."""
        if type(allowed) is not bool:
            self.error = INVALID
            return await self._reply(appid, game_name)
        return await self._change(lambda data: data["global"].update(allow_fp16=allowed),
                                  f"allow_fp16 = {allowed}", appid, game_name)

    @rpc
    async def remove_profile(self, ids: list, appid: int = 0, game_name: str = "") -> dict:
        """Keep lsfg-vk out of the game matching ids (the list's switch turned off)."""
        if not _valid_ids(ids):
            self.error = INVALID
            return await self._reply(appid, game_name)
        return await self._change(lambda data: lsfg_config.remove_ids(data, ids), f"profile {ids}: removed",
                                  appid, game_name)

    @rpc
    async def install_lsfg(self, appid: int = 0, name: str = "") -> dict:
        async with self.lock:
            home = _home()
            cli = lsfg_install.find_cli(home)
            if cli and not self.manifest.files:
                self.error = "lsfg-vk is already installed by something else; DeckyLS uses that installation."
                return await self._reply(appid, name)
            self.busy, self.error = "Downloading lsfg-vk…", ""
            try:
                archive = await asyncio.to_thread(lsfg_install.download)
                self.busy = "Installing lsfg-vk…"
                files = await asyncio.to_thread(lsfg_install.plan, archive, os.path.join(home, ".local"))
                # Recorded before the first write, so an interrupted install can still be finished or removed.
                planned = list(dict.fromkeys(self.manifest.files + [path for path, _, _ in files]))
                await asyncio.to_thread(self.manifest.save, self.manifest.version, planned)
                written = await asyncio.to_thread(lsfg_install.install, files)
                stale = await asyncio.to_thread(lsfg_install.uninstall, [p for p in planned if p not in written])
                for path, reason in stale.items():
                    decky.logger.warning(f"could not remove the old lsfg-vk file {path}: {reason}")
                await asyncio.to_thread(self.manifest.save, lsfg_install.LSFG_VERSION, written + list(stale))
                decky.logger.info(f"installed lsfg-vk {lsfg_install.LSFG_VERSION} ({len(written)} files)")
            except (lsfg_install.InstallError, OSError) as e:
                self.error = str(e)
                decky.logger.error(f"installing lsfg-vk failed: {e}")
            finally:
                self.busy = ""
                self.health = (None, None)
        return await self._reply(appid, name)

    @rpc
    async def remove_lsfg(self, appid: int = 0, name: str = "") -> dict:
        """Remove the lsfg-vk files DeckyLS installed. The config file stays: it is the user's settings."""
        async with self.lock:
            files = self.manifest.files
            try:
                failed = await asyncio.to_thread(lsfg_install.uninstall, files)
                if failed:  # still recorded, so pressing the button again finishes the job
                    await asyncio.to_thread(self.manifest.save, self.manifest.version, list(failed))
                    path, reason = next(iter(failed.items()))
                    self.error = f"Could not remove {len(failed)} lsfg-vk file(s), such as {path}: {reason}"
                    decky.logger.error(self.error)
                else:
                    await asyncio.to_thread(self.manifest.clear)
                    self.error = ""
                    decky.logger.info(f"removed lsfg-vk ({len(files)} files)")
            except OSError as e:
                self.error = f"Could not remove lsfg-vk: {e}"
                decky.logger.error(self.error)
            finally:
                self.health = (None, None)
        return await self._reply(appid, name)

    async def _unload(self):
        pass  # nothing runs in the background; a call still in to_thread ends by its own timeout

    async def _uninstall(self):
        # Decky runs this on every plugin update too (uninstall + install), so lsfg-vk stays; "Remove lsfg-vk"
        # in the panel is the full cleanup.
        decky.logger.info("uninstall/update: leaving lsfg-vk installed")

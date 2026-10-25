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
import subprocess
import sys
import time

import decky

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import lsfg_config  # noqa: E402
import lsfg_fps  # noqa: E402
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
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            saved = {}
        self.fps_counter = isinstance(saved, dict) and saved.get("fps_counter") is True
        self.fps = lsfg_fps.Reader(lsfg_fps.pipe_pattern() if hasattr(os, "getuid") else "")
        self.live = {}  # appid -> what the FPS counter knows about that game's session
        self.fps_task = None
        self.fps_label = ""  # what the counter shows right now
        if self.fps_counter:
            self._start_counter()

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
            "fps_counter": self.fps_counter,
            "fps_label": self.fps_label if self.fps_counter else "",
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

    async def set_fps_counter(self, enabled: bool, appid: int = 0, game_name: str = "") -> dict:
        if type(enabled) is not bool:
            self.error = "Invalid settings were rejected."
            return await self.get_state(appid, game_name)
        tmp = self.settings_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fps_counter": enabled}, f)
        os.replace(tmp, self.settings_path)
        self.fps_counter = enabled
        if enabled:
            self._start_counter()
        else:
            self._stop_counter()
        return await self.get_state(appid, game_name)

    def _start_counter(self):
        self.fps.start()
        if self.fps_task is None or self.fps_task.done():
            self.fps_task = asyncio.get_running_loop().create_task(self._counter())

    def _stop_counter(self):
        self.fps.stop()
        self.fps_label = ""
        if self.fps_task:
            self.fps_task.cancel()

    async def _counter(self):
        """Keep the overlay window's label current while the counter is on: a new gamescope reading arrives a few
        times a second; the running game and its X server are looked up every 2 s."""
        overlay, sent, appid, display, next_scan, retry_at = None, None, 0, "", 0.0, 0.0
        try:
            while True:
                now = time.monotonic()
                if now >= next_scan:
                    appid = await asyncio.to_thread(lsfg_status.running_appid)
                    game = await asyncio.to_thread(lsfg_status.find_game, appid) if appid else None
                    display = (game and game["display"]) or display
                    next_scan = now + 2
                fps = self.fps.current() if appid else None
                label = lsfg_fps.label(fps, await self._live_multiplier(appid) if fps else 1)
                self.fps_label = label
                if overlay is not None and overlay.poll() is None and overlay.display != display:
                    # A game on another X server: the window has to move there.
                    await asyncio.to_thread(self._close_overlay, overlay)
                    overlay, retry_at = None, 0.0
                if label and display and (overlay is None or overlay.poll() is not None) and now >= retry_at:
                    if overlay is not None:
                        decky.logger.warning(f"FPS overlay ended with {overlay.returncode}; restarting")
                    overlay, sent, retry_at = self._spawn_overlay(display), None, now + 10
                if overlay is not None and overlay.poll() is None and label != sent:
                    try:
                        overlay.stdin.write(label + "\n")
                        overlay.stdin.flush()
                        sent = label
                    except OSError:
                        sent = None
                await asyncio.sleep(0.25)
        finally:
            if overlay is not None:
                await asyncio.to_thread(self._close_overlay, overlay)

    @staticmethod
    def _close_overlay(overlay):
        if overlay.poll() is None:
            try:
                overlay.stdin.close()  # the window closes with its input
                overlay.wait(3)
            except (OSError, subprocess.TimeoutExpired):
                overlay.kill()

    def _spawn_overlay(self, display):
        # On the game's own X server: gamescope shows an X server's overlays only while that server has the focus,
        # so a window on Steam's server (:0) would appear only with the Steam UI open. The system python3 with a
        # clean environment, so Decky's own libraries (LD_LIBRARY_PATH) do not leak in.
        env = {"DISPLAY": display, "HOME": _home(), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        try:
            log = open(os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "overlay.log"), "w", encoding="utf-8")
            with log:
                overlay = subprocess.Popen(["/usr/bin/python3", "-I", os.path.join(PLUGIN_DIR, "lsfg_overlay.py")],
                                           stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log, env=env,
                                           text=True)
        except OSError as e:
            decky.logger.error(f"FPS overlay could not start: {e}")
            return None
        overlay.display = display
        return overlay

    async def _live_multiplier(self, appid):
        if type(appid) is not int or appid <= 0:
            return 1
        # lsfg-vk joins a game only when it starts; until its log says it did, the file's multiplier is not on
        # screen. The journal is read once per game, and again every few seconds while lsfg-vk has not joined.
        now = time.monotonic()
        known = self.live.get(appid)
        if known is None or (known["attached"] is None and now - known["checked"] > 5):
            running = await asyncio.to_thread(lsfg_status.find_game, appid)
            attached = None
            if running and running["started"]:
                attached = lsfg_status.attached_profile(
                    await asyncio.to_thread(lsfg_status.journal_since, running["started"]))
            known = {"ids": _ids(appid, running["exe"] if running else ""), "attached": attached, "checked": now}
            self.live = {appid: known}
        if known["attached"] is None:
            return 1
        try:
            profile = lsfg_config.find(lsfg_config.load(self.config_path), known["ids"])
        except lsfg_config.ConfigError:
            return 1
        multiplier = profile.get("multiplier", LSFG_DEFAULTS["multiplier"]) if profile else 1
        return multiplier if type(multiplier) is int and multiplier >= 1 else 1

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
        self._stop_counter()
        if self.fps_task:
            await asyncio.gather(self.fps_task, return_exceptions=True)

    async def _uninstall(self):
        # Decky runs this on every plugin update too (uninstall + install), so lsfg-vk stays; "Remove lsfg-vk"
        # in the panel is the full cleanup.
        decky.logger.info("uninstall/update: leaving lsfg-vk installed")

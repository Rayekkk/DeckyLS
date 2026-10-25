# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""The FPS counter's place on screen: a line in Steam's own performance overlay (mangoapp, MangoHud).

gamescope shows only Steam's performance overlay over games reliably, so DeckyLS adds one line to it instead of
drawing its own window. ~/.config/MangoHud/presets.conf extends Steam's built-in levels 2-4 with `inherit` and puts
first (MangoHud draws in file order) an `exec` item that prints the plugin's text file while it is fresh. mangoapp
runs that command itself every half second; with no fresh text, as without frame generation, nothing is shown.
Level 1 (the FPS number alone, sized to fit it) is left as Steam makes it.

Only a presets.conf DeckyLS wrote is ever changed or removed.
"""

import glob
import os

MARKER = "# Managed by DeckyLS"
LEVELS = (2, 3, 4)
STALE_S = 3  # the plugin rewrites the text at least every second


def presets_path(home):
    return os.path.join(home, ".config", "MangoHud", "presets.conf")


def text_path(runtime_dir):
    return os.path.join(runtime_dir, "deckyls", "fps")


def presets():
    command = f'find "$XDG_RUNTIME_DIR/deckyls/fps" -newermt "-{STALE_S} seconds" -exec cat {{}} +'
    sections = [f"[preset {level}]\nexec={command}\ninherit\n" for level in LEVELS]
    return (f"{MARKER}: adds lsfg-vk frame generation to Steam's performance overlay. "
            "Turn off DeckyLS's FPS counter, or delete this file, to undo.\n" + "\n".join(sections))


def is_ours(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.readline().startswith(MARKER)
    except FileNotFoundError:
        return True  # nothing there to keep
    except OSError:
        return False


def install(path):
    """Write the presets; False when the user has a presets.conf of their own, which stays untouched."""
    if not is_ours(path):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".deckyls-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(presets())
    os.replace(tmp, path)
    return True


def remove(path):
    if os.path.exists(path) and is_ours(path):
        os.remove(path)


def write_text(path, text):
    """The line mangoapp shows; "" removes it, so the overlay shows nothing extra."""
    if not text:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.replace(tmp, path)


def reload_overlay(runtime_dir):
    """mangoapp rereads its presets when Steam's overlay config changes; rewrite it unchanged to get there now."""
    for config in glob.glob(os.path.join(runtime_dir, "gamescope.*", "mangohud.config")):
        try:
            with open(config, encoding="utf-8") as f:
                content = f.read()
            with open(config, "w", encoding="utf-8") as f:
                f.write(content)
        except OSError:
            continue

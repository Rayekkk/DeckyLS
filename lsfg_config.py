# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""lsfg-vk's ~/.config/lsfg-vk/conf.toml: read it, change one game's profile, write it back.

lsfg-vk watches the file and reloads it in running games, so a write takes effect within a second.
Profiles and keys DeckyLS does not manage are written back unchanged; comments are not (tomllib drops them),
so the user's own file is copied once to conf.toml.bak-deckyls before the first write.
"""

import json
import math
import os
import re
import shutil
import tomllib

import dk_fs

VERSION = 2
BACKUP_SUFFIX = ".bak-deckyls"
# lsfg-vk rejects a file without profiles; this one stands in for the last removed game and matches nothing.
PLACEHOLDER = {"name": "DeckyLS: no game", "active_in": "deckyls-no-game", "multiplier": 1}
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


class ConfigError(Exception):
    pass


def config_path(home):
    return os.path.join(home, ".config", "lsfg-vk", "conf.toml")


def load(path):
    """The parsed file, or an empty lsfg-vk 2 configuration when there is none yet."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return {"version": VERSION, "global": {}, "profile": []}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise ConfigError(f"{path} cannot be read ({e}). Fix or delete it; DeckyLS will not overwrite it.") from e
    if data.get("version") != VERSION:
        raise ConfigError(f"{path} is not an lsfg-vk 2 configuration (version = {data.get('version')!r}). "
                          "Delete it or update it for lsfg-vk 2; DeckyLS will not overwrite it.")
    data.setdefault("global", {})
    data.setdefault("profile", [])
    if not isinstance(data["global"], dict) or not isinstance(data["profile"], list) \
            or not all(isinstance(p, dict) for p in data["profile"]):
        raise ConfigError(f"{path} has an unexpected layout; DeckyLS will not overwrite it.")
    return data


def profile_ids(profile):
    value = profile.get("active_in")
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def find(data, ids):
    """The first profile that matches any of ids, as lsfg-vk itself picks the first match."""
    wanted = set(ids)
    return next((p for p in data["profile"] if wanted & set(profile_ids(p))), None)


def is_placeholder(profile):
    return profile_ids(profile) == [PLACEHOLDER["active_in"]]


def remove_ids(data, ids):
    """Take ids out of every profile, so lsfg-vk stays out of that game; a profile left without ids goes."""
    wanted = set(ids)
    kept = []
    for profile in data["profile"]:
        known = profile_ids(profile)
        rest = [i for i in known if i not in wanted]
        if len(rest) == len(known):
            kept.append(profile)
        elif rest:
            profile["active_in"] = rest[0] if len(rest) == 1 else rest
            kept.append(profile)
    data["profile"] = kept or [dict(PLACEHOLDER)]


def set_profile(data, name, ids, settings):
    """Create or change the profile matching ids; settings are lsfg-vk profile keys and their values."""
    data["profile"] = [p for p in data["profile"] if not is_placeholder(p)]
    profile = find(data, ids)
    if profile is None:
        profile = {"name": name, "active_in": ids[0] if len(ids) == 1 else list(ids)}
        data["profile"].append(profile)
    else:
        known = profile_ids(profile)
        missing = [i for i in ids if i not in known]
        if missing:
            profile["active_in"] = known + missing
    profile.update(settings)
    return profile


def _key(key):
    return key if _BARE_KEY.fullmatch(key) else _value(key)


def _value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, str):
        # JSON string escapes are valid TOML basic-string escapes; TOML also forbids a raw DEL, which JSON keeps.
        return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")
    if isinstance(value, list):
        return "[" + ", ".join(_value(v) for v in value) + "]"
    raise ConfigError(f"DeckyLS cannot write a value of type {type(value).__name__} back; the file is left as it is.")


def _table(table):
    return [f"{_key(k)} = {_value(v)}" for k, v in table.items()]


def dumps(data):
    top = {k: v for k, v in data.items() if k not in ("global", "profile")}
    lines = _table(top) + ["", "[global]"] + _table(data["global"])
    for profile in data["profile"]:
        lines += ["", "[[profile]]"] + _table(profile)
    text = "\n".join(lines) + "\n"
    if tomllib.loads(text) != data:  # never write something that reads back differently
        raise ConfigError("DeckyLS could not write the configuration without changing it; the file is left as it is.")
    return text


def save(path, data):
    text = dumps(data).encode("utf-8")  # fails here, before any file is touched, on text UTF-8 cannot hold
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup = path + BACKUP_SUFFIX
    if os.path.exists(path) and not os.path.exists(backup):
        shutil.copy2(path, backup)
    dk_fs.write_atomic(path, text)

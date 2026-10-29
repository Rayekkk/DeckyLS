# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""What is true on the device right now: Lossless Scaling's DLL, the running game, whether lsfg-vk attached to it,
and other plugins that also manage lsfg-vk."""

import glob
import json
import os
import re
import subprocess

import dk_process

LS_DIR = "Lossless Scaling"
LS_DLL = "lsfg-vk.dll"  # only the "lsfg-vk" beta branch of Lossless Scaling has it
_LIBRARY_PATH = re.compile(r'^\s*"path"\s+"(.*)"\s*$', re.M)
_USING = re.compile(r"\(lsfg-vk\) \[INFO\]: Using profile with name '(.*)' \(identified via (.*)\)")
# Sibling plugins that install or configure lsfg-vk too; two managers of one config file confuse users.
_RIVALS = re.compile(r"lsfg|mako", re.I)


def steam_libraries(home):
    root = os.path.join(home, ".local", "share", "Steam")
    try:
        with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8", errors="replace") as f:
            paths = [p.replace("\\\\", "\\") for p in _LIBRARY_PATH.findall(f.read())]
    except OSError:
        paths = []
    return list(dict.fromkeys([root, *paths]))


def lossless_scaling(home):
    """{"installed": bool, "dll": path or ""}: installed without the DLL means the wrong Steam branch."""
    installed = False
    for library in steam_libraries(home):
        folder = os.path.join(library, "steamapps", "common", LS_DIR)
        if os.path.isdir(folder):
            installed = True
            dll = os.path.join(folder, LS_DLL)
            if os.path.isfile(dll):
                return {"installed": True, "dll": dll}
    return {"installed": installed, "dll": ""}


def _read(path):
    with open(path, "rb") as f:
        return f.read()


def find_game(appid, proc="/proc"):
    """Steam's reaper for appid: {"exe": basename of what it launched, "started": epoch seconds}, or None."""
    key = f"AppId={appid}".encode()
    for path in glob.glob(os.path.join(proc, "[0-9]*", "cmdline")):
        try:
            argv = _read(path).split(b"\0")
            if not argv or not argv[0].endswith(b"/reaper") or key not in argv:
                continue
            return {"exe": _launched_exe(argv), "started": _started(os.path.dirname(path), proc)}
        except OSError:
            continue  # the process ended while being read
    return None


def _launched_exe(argv):
    """The game's file name: the last Windows .exe (Proton), else the program after the last "--" (native)."""
    args = [a.decode(errors="replace") for a in argv if a]
    exe = next((a for a in reversed(args) if a.lower().endswith(".exe")), "")
    if not exe and "--" in args:
        tail = args[len(args) - args[::-1].index("--"):]
        exe = tail[0] if tail else ""
    return exe.replace("\\", "/").rsplit("/", 1)[-1]


def _started(pid_dir, proc):
    """Process start time in epoch seconds (from /proc/<pid>/stat and the boot time)."""
    try:
        ticks = int(_read(os.path.join(pid_dir, "stat")).rsplit(b")", 1)[1].split()[19])
        boot = next(int(line.split()[1]) for line in _read(os.path.join(proc, "stat")).splitlines()
                    if line.startswith(b"btime "))
        return boot + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration, AttributeError):
        return 0.0


def journal_since(since):
    """lsfg-vk's log lines since an epoch time; it logs through the Steam client into the user journal."""
    try:
        result = dk_process.run(["journalctl", "--user", "--no-pager", "-o", "cat", f"--since=@{int(since)}",
                                 "SYSLOG_IDENTIFIER=steam"], timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        return []
    return [line for line in result.stdout.splitlines() if "(lsfg-vk)" in line]


def attached_profile(lines):
    """(profile name, how it was identified) from the latest "Using profile" line, or None."""
    for line in reversed(lines):
        match = _USING.search(line)
        if match:
            return match.group(1), match.group(2)
    return None


_rivals = {}  # plugins folder -> (its mtime, names found)


def rival_plugins(plugin_dir):
    """Names of other installed Decky plugins that also manage lsfg-vk. Read again only when a plugin is added or
    removed (the folder's mtime): Decky's file watcher logs every file opened in there, and the panel asks every 5 s."""
    own = os.path.realpath(plugin_dir)
    folder = os.path.dirname(own)
    try:
        stamp = os.stat(folder).st_mtime_ns
    except OSError:
        return []
    if folder in _rivals and _rivals[folder][0] == stamp:
        return _rivals[folder][1]
    found = []
    for manifest in sorted(glob.glob(os.path.join(folder, "*", "plugin.json"))):
        if os.path.realpath(os.path.dirname(manifest)) == own:
            continue
        try:
            with open(manifest, encoding="utf-8-sig") as f:
                name = json.load(f).get("name", "")
        except (OSError, ValueError, AttributeError):
            continue  # a plugin without a readable manifest cannot be told apart, so it is not named
        if isinstance(name, str) and _RIVALS.search(name):
            found.append(name)
    _rivals[folder] = (stamp, found)
    return found

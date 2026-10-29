# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""Install, check and remove the official lsfg-vk build in ~/.local.

DeckyLS never ships or changes lsfg-vk (CC BY-NC-ND 4.0): it downloads the author's unmodified release archive
from builds.lsfg-vk.dev, checks it against the hash pinned here and unpacks it the way the author's install guide
does (`tar -xf ... -C ~/.local`). The files it wrote are recorded so that removal deletes exactly those.
"""

import io
import os
import posixpath
import shutil
import subprocess
import tarfile

import dk_fs
import dk_net
import dk_process

LSFG_VERSION = "2.0.0"
URL = f"https://builds.lsfg-vk.dev/lsfg-vk-{LSFG_VERSION}.tar.xz"
HOSTS = {"builds.lsfg-vk.dev"}  # the download and any redirect stay on the author's build server
SHA256 = "08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74"
MAX_DOWNLOAD = 16 * 1024 * 1024  # the 2.0.0 archive is 0.5 MiB
TOP_DIRS = ("bin", "lib", "share")
HEALTHY = "did not find any issues"


class InstallError(Exception):
    pass


def download(url=URL, sha256=SHA256, max_size=MAX_DOWNLOAD):
    try:
        return dk_net.get(url, max_size, sha256, hosts=HOSTS)
    except dk_net.TooLarge as e:
        raise InstallError("The lsfg-vk download is larger than expected; nothing was installed.") from e
    except dk_net.Mismatch as e:
        raise InstallError("The lsfg-vk download does not match the expected release; nothing was installed.") from e
    except dk_net.NetError as e:
        raise InstallError(f"Could not download lsfg-vk from builds.lsfg-vk.dev: {e}") from e


def _members(archive):
    """(relative path, member) for every file, refusing anything that could land outside its prefix."""
    try:
        tar = tarfile.open(fileobj=io.BytesIO(archive), mode="r:xz")
        members = tar.getmembers()
    except (tarfile.TarError, EOFError, OSError) as e:
        raise InstallError(f"The lsfg-vk archive cannot be read: {e}") from e
    files = []
    for member in members:
        name = posixpath.normpath(member.name)
        if name == ".":
            continue
        if member.name.startswith("/") or name.startswith("..") or name.split("/")[0] not in TOP_DIRS:
            raise InstallError(f"Unexpected path in the lsfg-vk archive: {member.name}")
        if member.isdir():
            continue
        if not member.isfile():
            raise InstallError(f"Unexpected entry type in the lsfg-vk archive: {member.name}")
        files.append((name, tar.extractfile(member).read(), member.mode))
    if not files:
        raise InstallError("The lsfg-vk archive is empty.")
    return files


def plan(archive, prefix):
    """[(absolute path, content, mode)] for every file of the archive under prefix (~/.local), all checked before
    anything is written."""
    return [(os.path.join(prefix, *name.split("/")), content, mode) for name, content, mode in _members(archive)]


def install(files):
    """Write the planned files; returns their paths."""
    for dest, content, mode in files:
        dk_fs.write_atomic(dest, content, mode & 0o755)
    return [dest for dest, _, _ in files]


def uninstall(files):
    """Delete the recorded files; folders such as ~/.local/bin stay, other software uses them. Returns
    {path: reason} for the files that could not be deleted."""
    failed = {}
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass  # already gone, which is what removing it was for
        except OSError as e:
            failed[path] = e.strerror or str(e)
    return failed


def _valid_manifest(data):
    if not (isinstance(data, dict) and isinstance(data.get("version"), str) and isinstance(data.get("files"), list)
            and all(isinstance(p, str) for p in data["files"])):
        raise ValueError("not a list of installed files")


class Manifest:
    """What DeckyLS installed: {"version": ..., "files": [...]}, kept in the plugin's settings folder."""

    def __init__(self, path):
        self.path = path
        self.problem = ""  # why the list could not be read; the panel shows it
        try:
            loaded = dk_fs.load_json(path, validate=_valid_manifest)
        except OSError as e:  # unreadable for now (permissions, I/O): nothing is touched, nothing is assumed
            loaded = dk_fs.Loaded(None, "lost", e.strerror or type(e).__name__)
        if loaded.status == "lost":
            self.problem = f"DeckyLS's list of installed lsfg-vk files cannot be read ({loaded.detail})."
        data = loaded.value or {"version": "", "files": []}
        self.version, self.files = data["version"], list(data["files"])

    def save(self, version, files):
        dk_fs.write_json(self.path, {"version": version, "files": list(files)})
        self.version, self.files = version, list(files)

    def clear(self):
        dk_fs.remove_json(self.path)
        self.version, self.files = "", []


def find_cli(home):
    local = os.path.join(home, ".local", "bin", "lsfg-vk-cli")
    return local if os.access(local, os.X_OK) else shutil.which("lsfg-vk-cli") or ""


def healthcheck(cli):
    """lsfg-vk's own verdict on the installation; None when lsfg-vk is not installed."""
    if not cli:
        return None
    try:
        result = dk_process.run([cli, "healthcheck"], timeout=20, capture_output=True)
        text = (result.stdout + result.stderr).strip()
    except subprocess.TimeoutExpired:  # its text has the program's full path, with the user's name in it
        return {"ok": False, "text": "lsfg-vk-cli did not answer within 20 s.", "version": ""}
    except (OSError, subprocess.SubprocessError) as e:
        reason = e.strerror if isinstance(e, OSError) and e.strerror else type(e).__name__
        return {"ok": False, "text": f"lsfg-vk-cli could not run: {reason}", "version": ""}
    version = ""
    for line in text.splitlines():
        if line.startswith("Installed lsfg-vk-layer version:"):
            version = line.split(":", 1)[1].strip()
    return {"ok": result.returncode == 0 and HEALTHY in text, "text": text, "version": version}

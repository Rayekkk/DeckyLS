# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""Install, check and remove the official lsfg-vk build in ~/.local.

DeckyLS never ships or changes lsfg-vk (CC BY-NC-ND 4.0): it downloads the author's unmodified release archive
from builds.lsfg-vk.dev, checks it against the hash pinned here and unpacks it the way the author's install guide
does (`tar -xf ... -C ~/.local`). The files it wrote are recorded so that removal deletes exactly those.
"""

import hashlib
import io
import json
import os
import posixpath
import shutil
import ssl
import subprocess
import tarfile
import urllib.request

LSFG_VERSION = "2.0.0"
URL = f"https://builds.lsfg-vk.dev/lsfg-vk-{LSFG_VERSION}.tar.xz"
SHA256 = "08bdbdf373a111022df87dac7aa87e3b564bb841f961552e3ca85fea12b5aa74"
MAX_DOWNLOAD = 16 * 1024 * 1024  # the 2.0.0 archive is 0.5 MiB
TOP_DIRS = ("bin", "lib", "share")
HEALTHY = "did not find any issues"
CA_FILES = ("/etc/ssl/certs/ca-certificates.crt", "/etc/ssl/cert.pem")


class InstallError(Exception):
    pass


def _ssl_context():
    """Verified TLS. Decky's frozen Python has no CA store of its own, so use certifi (bundled with Decky) or the
    system bundle; verification is never turned off."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        pass
    for cafile in CA_FILES:
        if os.path.isfile(cafile):
            return ssl.create_default_context(cafile=cafile)
    return ssl.create_default_context()


def download(url=URL, sha256=SHA256, max_size=MAX_DOWNLOAD):
    try:
        with urllib.request.urlopen(url, timeout=30, context=_ssl_context()) as response:
            data = response.read(max_size + 1)
    except OSError as e:
        raise InstallError(f"Could not download lsfg-vk from builds.lsfg-vk.dev: {e}") from e
    if len(data) > max_size:
        raise InstallError("The lsfg-vk download is larger than expected; nothing was installed.")
    if hashlib.sha256(data).hexdigest() != sha256:
        raise InstallError("The lsfg-vk download does not match the expected release; nothing was installed.")
    return data


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


def install(archive, prefix):
    """Unpack into prefix (~/.local); returns the absolute paths written."""
    written = []
    for name, content, mode in _members(archive):
        dest = os.path.join(prefix, *name.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        tmp = dest + ".deckyls-tmp"
        with open(tmp, "wb") as f:
            f.write(content)
        os.chmod(tmp, mode & 0o755)
        os.replace(tmp, dest)
        written.append(dest)
    return written


def uninstall(files):
    """Delete the recorded files; folders such as ~/.local/bin stay, other software uses them."""
    for path in files:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


class Manifest:
    """What DeckyLS installed: {"version": ..., "files": [...]}, kept in the plugin's settings folder."""

    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.version = str(data["version"])
            self.files = [str(p) for p in data["files"]]
        except (OSError, ValueError, KeyError, TypeError):
            self.version, self.files = "", []

    def save(self, version, files):
        self.version, self.files = version, list(files)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": version, "files": self.files}, f, indent=1)
        os.replace(tmp, self.path)

    def clear(self):
        self.version, self.files = "", []
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


def find_cli(home):
    local = os.path.join(home, ".local", "bin", "lsfg-vk-cli")
    return local if os.access(local, os.X_OK) else shutil.which("lsfg-vk-cli") or ""


def healthcheck(cli):
    """lsfg-vk's own verdict on the installation; None when lsfg-vk is not installed."""
    if not cli:
        return None
    try:
        result = subprocess.run([cli, "healthcheck"], capture_output=True, text=True, timeout=20)
        text = (result.stdout + result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "text": f"lsfg-vk-cli could not run: {e}", "version": ""}
    version = ""
    for line in text.splitlines():
        if line.startswith("Installed lsfg-vk-layer version:"):
            version = line.split(":", 1)[1].strip()
    return {"ok": result.returncode == 0 and HEALTHY in text, "text": text, "version": version}

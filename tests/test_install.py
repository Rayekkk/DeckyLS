# SPDX-License-Identifier: BSD-3-Clause
import hashlib
import io
import os
import pathlib
import tarfile
import tempfile
import unittest

import _harness  # noqa: F401
import lsfg_install as i


def archive(*entries):
    """tar.xz bytes; entries are (name, content) for files, (name, None) for folders, (name, "->target") symlinks."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz") as tar:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            if content is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(info)
            elif content.startswith("->"):
                info.type, info.linkname = tarfile.SYMTYPE, content[2:]
                tar.addfile(info)
            else:
                data = content.encode()
                info.size, info.mode = len(data), 0o4755 if name.startswith("./bin") else 0o644
                tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


GOOD = archive(("./", None), ("./bin/", None), ("./bin/lsfg-vk-cli", "cli"), ("./lib/liblsfg-vk-layer.so", "so"),
               ("./share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json", "{}"))


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.prefix = tempfile.mkdtemp()

    def test_official_layout_lands_in_prefix_and_is_recorded(self):
        written = i.install(GOOD, self.prefix)
        self.assertEqual(sorted(os.path.relpath(p, self.prefix).replace("\\", "/") for p in written),
                         ["bin/lsfg-vk-cli", "lib/liblsfg-vk-layer.so",
                          "share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json"])
        self.assertEqual(pathlib.Path(self.prefix, "lib", "liblsfg-vk-layer.so").read_text(), "so")
        if os.name == "posix":  # setuid never survives, executables stay executable
            self.assertEqual(os.stat(os.path.join(self.prefix, "bin", "lsfg-vk-cli")).st_mode & 0o7777, 0o755)

    def test_entries_that_could_escape_the_prefix_are_refused_before_any_write(self):
        for bad in (archive(("./bin/ok", "x"), ("../evil", "x")), archive(("/etc/evil", "x")),
                    archive(("./etc/evil", "x")), archive(("./bin/a/../../../evil", "x")),
                    archive(("./bin/link", "->/etc/passwd")), b"not an archive", archive(("./", None))):
            with self.assertRaises(i.InstallError):
                i.install(bad, self.prefix)
        self.assertEqual(os.listdir(self.prefix), [])

    def test_download_is_checked_against_the_pinned_hash(self):
        path = os.path.join(self.prefix, "a.tar.xz")
        pathlib.Path(path).write_bytes(GOOD)
        url = pathlib.Path(path).as_uri()
        self.assertEqual(i.download(url, hashlib.sha256(GOOD).hexdigest()), GOOD)
        with self.assertRaises(i.InstallError):
            i.download(url, "0" * 64)
        with self.assertRaises(i.InstallError):
            i.download(url, hashlib.sha256(GOOD).hexdigest(), max_size=10)

    def test_removal_deletes_only_recorded_files(self):
        written = i.install(GOOD, self.prefix)
        other = os.path.join(self.prefix, "bin", "someone-elses-tool")
        pathlib.Path(other).write_text("keep")
        manifest = i.Manifest(os.path.join(self.prefix, "installed.json"))
        manifest.save("2.0.0", written)
        reloaded = i.Manifest(manifest.path)
        self.assertEqual((reloaded.version, reloaded.files), ("2.0.0", written))
        i.uninstall(reloaded.files + [os.path.join(self.prefix, "already-gone")])
        self.assertTrue(all(not os.path.exists(p) for p in written))
        self.assertTrue(os.path.exists(other))
        reloaded.clear()
        self.assertEqual(i.Manifest(manifest.path).files, [])


if __name__ == "__main__":
    unittest.main()

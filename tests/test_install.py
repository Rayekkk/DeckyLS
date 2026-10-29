# SPDX-License-Identifier: BSD-3-Clause
import io
import os
import pathlib
import tarfile
import tempfile
import unittest
from unittest import mock

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
        written = i.install(i.plan(GOOD, self.prefix))
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
                i.install(i.plan(bad, self.prefix))
        self.assertEqual(os.listdir(self.prefix), [])

    def test_download_is_pinned_to_its_host_hash_and_size(self):
        with mock.patch.object(i.dk_net, "get", return_value=GOOD) as get:
            self.assertEqual(i.download(), GOOD)
        self.assertEqual(get.call_args.args, (i.URL, i.MAX_DOWNLOAD, i.SHA256))
        self.assertEqual(get.call_args.kwargs, {"hosts": {"builds.lsfg-vk.dev"}})
        for error, text in ((i.dk_net.Mismatch("x"), "does not match the expected release"),
                            (i.dk_net.TooLarge("x"), "larger than expected"),
                            (i.dk_net.NetError("[Errno -3] Temporary failure in name resolution"),
                             r"Could not download lsfg-vk from builds\.lsfg-vk\.dev: \[Errno -3\]")):
            with mock.patch.object(i.dk_net, "get", side_effect=error), self.assertRaisesRegex(i.InstallError, text):
                i.download()
        self.assertEqual(i.dk_net.check_url(i.URL, i.HOSTS), i.URL, "the pinned URL passes dk_net's own checks")

    def test_errors_for_the_panel_name_no_path(self):
        path = os.path.join(self.prefix, "installed.json")
        with mock.patch.object(i.dk_fs, "load_json", side_effect=PermissionError(13, "Permission denied", path)):
            self.assertEqual(i.Manifest(path).problem,
                             "DeckyLS's list of installed lsfg-vk files cannot be read (Permission denied).")
        cli = os.path.join(self.prefix, "bin", "lsfg-vk-cli")
        for error, text in ((i.subprocess.TimeoutExpired([cli, "healthcheck"], 20), "did not answer within 20 s."),
                            (PermissionError(13, "Permission denied", cli), "could not run: Permission denied")):
            with mock.patch.object(i.dk_process, "run", side_effect=error):
                result = i.healthcheck(cli)
            self.assertFalse(result["ok"])
            self.assertTrue(result["text"].endswith(text), result["text"])
            self.assertNotIn(self.prefix, result["text"])

    def test_an_unreadable_list_of_installed_files_is_reported_not_guessed(self):
        path = os.path.join(self.prefix, "installed.json")
        pathlib.Path(path).write_text('{"version": "2.0.0", "files": [1')
        manifest = i.Manifest(path)
        self.assertEqual((manifest.version, manifest.files), ("", []))
        self.assertIn("cannot be read", manifest.problem)
        pathlib.Path(path).write_text('{"version": "2.0.0", "files": "not a list"}')
        self.assertIn("cannot be read", i.Manifest(path).problem)
        self.assertTrue(os.path.exists(path), "kept for the user, never overwritten by a guess")

    def test_removal_deletes_only_recorded_files(self):
        written = i.install(i.plan(GOOD, self.prefix))
        other = os.path.join(self.prefix, "bin", "someone-elses-tool")
        pathlib.Path(other).write_text("keep")
        manifest = i.Manifest(os.path.join(self.prefix, "installed.json"))
        manifest.save("2.0.0", written)
        reloaded = i.Manifest(manifest.path)
        self.assertEqual((reloaded.version, reloaded.files), ("2.0.0", written))
        self.assertEqual(i.uninstall(reloaded.files + [os.path.join(self.prefix, "already-gone")]), {})
        self.assertTrue(all(not os.path.exists(p) for p in written))
        self.assertTrue(os.path.exists(other))
        reloaded.clear()
        self.assertEqual(i.Manifest(manifest.path).files, [])


if __name__ == "__main__":
    unittest.main()

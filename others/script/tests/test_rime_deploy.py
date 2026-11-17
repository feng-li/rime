"""Exercise deployment against temporary cloud/local directories, never real Rime."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / "deploy.sh"


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rime deploy test ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "Nextcloud/shared rime"
        self.target = self.root / "local/Rime"
        self.backups = self.root / "private backups"
        self.source.mkdir(parents=True)
        self.environment = dict(os.environ, HOME=str(self.root / "home"))
        self.environment["XDG_CONFIG_HOME"] = str(self.root / "config")
        self.environment["XDG_DATA_HOME"] = str(self.root / "data")
        self.environment["XDG_STATE_HOME"] = str(self.root / "state")
        self.write("rime_ice.schema.yaml", "schema:\n  schema_id: rime_ice\n")
        self.write("english_booster.schema.yaml", "translator:\n  user_dict: english_booster\n")
        self.write("default.custom.yaml", "patch:\n  menu/page_size: 5\n")
        self.write("lua/english_booster.lua", "return {}\n")
        self.write("en_dicts/mw2015_synonyms.lua", "return {test = {}}\n")
        self.write("opencc/emoji.txt", "test\tTEST\n")
        self.write("installation.yaml", 'installation_id: "shared-old-id"\n')
        self.write("user.yaml", "var:\n  previous_schema: rime_ice\n")
        self.write("build/cache.bin", "compiled source cache")
        self.write("rime_ice.userdb/LOCK", "")
        self.write("rime_ice.userdb/data.ldb", "Chinese personal data")
        self.write("english_booster.userdb/LOCK", "")
        self.write("english_booster.userdb/data.ldb", "English personal data")
        self.write("sync/other/rime_ice.userdb.txt", "other device snapshot")

    def write(self, relative, text):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_deploy(self, *extra, ok=True):
        result = subprocess.run(["bash", str(SCRIPT), "--source", str(self.source),
                                 "--frontend", "squirrel", "--user-dir", str(self.target),
                                 "--backup-dir", str(self.backups), *extra],
                                env=self.environment, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def local_id(self):
        text = (self.target / "installation.yaml").read_text()
        return next(json.loads(line.partition(":")[2]) for line in text.splitlines()
                    if line.startswith("installation_id:"))

    def make_old_link(self):
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(self.source, target_is_directory=True)

    def test_fresh_deployment_copies_sources_not_cloud_runtime(self):
        self.write("#editor-backup.yaml#", "ignore")
        self.write("local (conflicted copy 2026).yaml", "ignore")
        self.write("ibus_rime.custom.yaml", "platform: ibus\n")
        self.write("squirrel.custom.yaml", "platform: squirrel\n")
        self.run_deploy()
        self.assertTrue(self.target.is_dir())
        self.assertFalse(self.target.is_symlink())
        for path in ("rime_ice.schema.yaml", "default.custom.yaml", "lua/english_booster.lua",
                     "en_dicts/mw2015_synonyms.lua", "opencc/emoji.txt", "squirrel.custom.yaml"):
            self.assertEqual((self.target / path).read_bytes(), (self.source / path).read_bytes())
        for path in ("build", "sync", "user.yaml", "rime_ice.userdb", "english_booster.userdb",
                     "ibus_rime.custom.yaml", "local (conflicted copy 2026).yaml"):
            self.assertFalse((self.target / path).exists(), path)
        self.assertNotEqual(self.local_id(), "shared-old-id")
        self.assertIn(str(self.source / "sync"), (self.target / "installation.yaml").read_text())

    def test_dry_run_has_no_filesystem_side_effects(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        result = self.run_deploy("--dry-run")
        self.assertIn("no files changed", result.stdout)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))

    def test_redeploy_preserves_identity_runtime_and_unchanged_files(self):
        self.run_deploy()
        identity = self.local_id()
        config = self.target / "default.custom.yaml"
        timestamp = config.stat().st_mtime_ns
        db = self.target / "english_booster.userdb"
        db.mkdir()
        (db / "personal.ldb").write_text("keep learned vocabulary")
        (self.target / "build").mkdir()
        (self.target / "build/local.bin").write_text("keep local build")
        (self.target / "user.yaml").write_text("local state")
        (self.target / "my-local.custom.yaml").write_text("local customization")
        self.run_deploy()
        self.assertEqual(self.local_id(), identity)
        self.assertEqual(config.stat().st_mtime_ns, timestamp)
        self.assertEqual((db / "personal.ldb").read_text(), "keep learned vocabulary")
        self.assertEqual((self.target / "build/local.bin").read_text(), "keep local build")
        self.assertEqual((self.target / "user.yaml").read_text(), "local state")
        self.assertEqual((self.target / "my-local.custom.yaml").read_text(), "local customization")

    def test_existing_local_installation_fields_are_preserved(self):
        self.target.mkdir(parents=True)
        (self.target / "installation.yaml").write_text(
            "# local metadata\ninstallation_id: 'my-laptop' # keep identity\n"
            'distribution_code_name: squirrel\nsync_dir: "/old/path"\n')
        self.run_deploy()
        self.assertEqual(self.local_id(), "my-laptop")
        self.assertIn("distribution_code_name: squirrel", (self.target / "installation.yaml").read_text())

    def test_updated_config_is_backed_up(self):
        self.run_deploy()
        self.write("default.custom.yaml", "patch:\n  menu/page_size: 7\n")
        self.run_deploy()
        backups = list(self.backups.glob("*/default.custom.yaml"))
        self.assertEqual(len(backups), 1)
        self.assertIn("page_size: 5", backups[0].read_text())
        self.assertIn("page_size: 7", (self.target / "default.custom.yaml").read_text())

    def test_migration_requires_explicit_flag_and_preserves_data(self):
        self.make_old_link()
        self.run_deploy(ok=False)
        self.assertTrue(self.target.is_symlink())
        self.run_deploy("--migrate")
        self.assertFalse(self.target.is_symlink())
        for name in ("rime_ice", "english_booster"):
            self.assertEqual((self.target / (name + ".userdb/data.ldb")).read_bytes(),
                             (self.source / (name + ".userdb/data.ldb")).read_bytes())
            self.assertFalse((self.target / (name + ".userdb/LOCK")).exists())
        self.assertTrue((self.target / "user.yaml").is_file())
        self.assertFalse((self.target / "build").exists())
        self.assertNotEqual(self.local_id(), "shared-old-id")
        self.assertEqual((self.source / "installation.yaml").read_text(), 'installation_id: "shared-old-id"\n')
        self.assertEqual((self.source / "sync/other/rime_ice.userdb.txt").read_text(), "other device snapshot")
        self.assertTrue(list(self.backups.glob("*/original-user-directory-link"))[0].is_symlink())

    def test_migration_refuses_locked_user_dictionary(self):
        self.make_old_link()
        with (self.source / "english_booster.userdb/LOCK").open("r+") as lock:
            fcntl.lockf(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_deploy("--migrate", ok=False)
        self.assertIn("User dictionary is in use", result.stderr)
        self.assertTrue(self.target.is_symlink())
        self.assertFalse(list(self.target.parent.glob(".rime-deploy-*")))

    def test_migration_refuses_running_frontend(self):
        self.make_old_link()
        executable = self.root / "Squirrel"
        shutil.copy2(shutil.which("sh"), executable)
        process = subprocess.Popen([str(executable), "-c", "while :; do sleep 1; done"],
                                   start_new_session=True)
        try:
            # Include a path with spaces, as in macOS's Input Methods directory.
            for _ in range(30):
                ps = subprocess.run(["ps", "-p", str(process.pid), "-o", "comm="],
                                    text=True, capture_output=True).stdout
                if Path(ps.strip()).name == "Squirrel":
                    break
            self.assertIsNone(process.poll(), "Synthetic frontend must still be running")
            result = self.run_deploy("--migrate", ok=False)
            self.assertIn("running frontend", result.stderr)
            self.assertTrue(self.target.is_symlink())
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait()

    def test_runtime_and_backup_cannot_be_in_shared_source(self):
        self.run_deploy("--user-dir", str(self.source / "runtime"), ok=False)
        self.run_deploy("--backup-dir", str(self.source / "backups"), ok=False)
        self.run_deploy("--sync-dir", str(self.source), ok=False)
        self.assertFalse(self.target.exists())

    def test_directory_symlink_cannot_write_back_into_shared_files(self):
        self.target.mkdir(parents=True)
        (self.target / "lua").symlink_to(self.source / "lua", target_is_directory=True)
        result = self.run_deploy(ok=False)
        self.assertIn("symlink", result.stderr)
        self.assertFalse((self.target / "default.custom.yaml").exists())
        self.assertEqual((self.source / "lua/english_booster.lua").read_text(), "return {}\n")

    def test_two_machines_get_different_stable_ids(self):
        self.run_deploy()
        first = self.local_id()
        other = self.root / "another machine/Rime"
        self.run_deploy("--user-dir", str(other))
        second = next(json.loads(line.partition(":")[2])
                      for line in (other / "installation.yaml").read_text().splitlines()
                      if line.startswith("installation_id:"))
        self.assertNotEqual(first, second)
        self.run_deploy()
        self.assertEqual(self.local_id(), first)

    def test_local_identity_symlink_is_rejected(self):
        self.target.mkdir(parents=True)
        (self.target / "installation.yaml").symlink_to(self.source / "installation.yaml")
        self.run_deploy(ok=False)
        self.assertFalse((self.target / "default.custom.yaml").exists())


if __name__ == "__main__":
    unittest.main()

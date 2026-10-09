"""Etapa 06 offline unit tests: no real DB, network, production secrets, or files."""

import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import backup_securedesk as backup


class FakePaginator:
    def __init__(self, objects):
        self.objects = objects

    def paginate(self, **kwargs):
        assert kwargs["Bucket"] == "private-test"
        yield {"Contents": [{"Key": key, "Size": len(value)} for key, value in self.objects.items()]}


class FakeS3:
    def __init__(self, objects):
        self.objects = objects
        self.read_calls = []
        self.delete_calls = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self.objects)

    def get_object(self, **kwargs):
        assert kwargs["Bucket"] == "private-test"
        self.read_calls.append(kwargs["Key"])
        return {"Body": io.BytesIO(self.objects[kwargs["Key"]])}


def db_args(destination, *, environment="development", extra=None):
    return backup._parser().parse_args([
        "database", "--host", "127.0.0.1", "--dbname", "securedesk",
        "--user", "securedesk", "--out-dir", str(destination),
        "--environment", environment, *(extra or []),
    ])


def s3_args(destination, *, environment="development", extra=None):
    return backup._parser().parse_args([
        "objects", "--out-dir", str(destination), "--environment", environment,
        *(extra or []),
    ])


class BackupSecurityTests(unittest.TestCase):
    def test_does_not_store_backup_inside_repository(self):
        repo = Path(backup.__file__).resolve().parent.parent
        with self.assertRaisesRegex(backup.BackupError, "FORA"):
            backup._backup_root(str(repo / "backups"))

    def test_production_requires_explicit_confirmation_and_tls(self):
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(backup.BackupError, "confirm-production"):
                backup.backup_database(db_args(folder, environment="production"))
            with self.assertRaisesRegex(backup.BackupError, "SSL"):
                backup.backup_database(db_args(folder, environment="production", extra=["--confirm-production"]))
            with self.assertRaisesRegex(backup.BackupError, "confirm-production"):
                backup.backup_objects(s3_args(folder, environment="production"))

    def test_rejects_uri_credentials_and_pooler(self):
        with TemporaryDirectory() as folder:
            args = db_args(folder)
            args.host = "postgresql://user:password@host/db"
            with self.assertRaises(backup.BackupError):
                backup.backup_database(args)
            args = db_args(folder, environment="production", extra=["--confirm-production", "--sslmode", "require"])
            args.host = "neon-pooler.example.com"
            with self.assertRaisesRegex(backup.BackupError, "pooler"):
                backup.backup_database(args)

    def test_database_backup_manifest_and_detects_corruption(self):
        with TemporaryDirectory() as folder:
            def command(command, **kwargs):
                if command[0] == "pg_dump":
                    Path(command[command.index("--file") + 1]).write_bytes(b"PGDMP-test-bytes")
                return subprocess.CompletedProcess(command, 0, b"", b"")

            with patch.object(backup.shutil, "which", return_value="found"), patch.object(
                backup.subprocess, "run", side_effect=command
            ) as runner:
                manifest = backup.backup_database(db_args(folder))
                data = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertEqual(data["kind"], "postgresql")
                self.assertEqual(data["environment"], "development")
                self.assertNotIn("127.0.0.1", manifest.read_text(encoding="utf-8"))
                self.assertEqual(backup.verify_database(str(manifest)), 1)
                self.assertEqual(runner.call_count, 3)
                dump = manifest.parent / data["archive"]["filename"]
                dump.write_bytes(b"CORRUPTED")
                with self.assertRaisesRegex(backup.BackupError, "Integridade"):
                    backup.verify_database(str(manifest))

    def test_failed_dump_leaves_no_artifact(self):
        with TemporaryDirectory() as folder:
            with patch.object(backup.shutil, "which", return_value="found"), patch.object(
                backup.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"secret"),
            ):
                with self.assertRaisesRegex(backup.BackupError, "pg_dump falhou"):
                    backup.backup_database(db_args(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_rejects_manifest_path_traversal(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(backup.BackupError):
                backup._safe_manifest_path(Path(folder), "../secret.dump")
            with self.assertRaises(backup.BackupError):
                backup._safe_manifest_path(Path(folder), "..")


class S3BackupTests(unittest.TestCase):
    def test_real_files_are_hashed_and_verifiable_without_remote_access(self):
        objects = {"private/../../danger.txt": b"hello-world", "deadbeef.txt": b"test\x00data"}
        with TemporaryDirectory() as folder:
            fake = FakeS3(objects)
            with patch.object(backup, "_s3_client_and_bucket", return_value=(fake, "private-test")):
                manifest = backup.backup_objects(s3_args(folder))
            self.assertEqual(backup.verify_objects(str(manifest)), 2)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual({o["key"] for o in data["objects"]}, set(objects))
            self.assertEqual(set(fake.read_calls), set(objects))
            self.assertEqual(fake.delete_calls, [])
            self.assertEqual(len(list((manifest.parent / "objects").glob("*.bin"))), 2)
            object_file = manifest.parent / "objects" / data["objects"][0]["filename"]
            object_file.write_bytes(b"changed")
            with self.assertRaisesRegex(backup.BackupError, "Integridade"):
                backup.verify_objects(str(manifest))

    def test_rejects_empty_bucket_unless_requested(self):
        with TemporaryDirectory() as folder:
            with patch.object(backup, "_s3_client_and_bucket", return_value=(FakeS3({}), "private-test")):
                with self.assertRaisesRegex(backup.BackupError, "vazio"):
                    backup.backup_objects(s3_args(folder))
                manifest = backup.backup_objects(s3_args(folder, extra=["--allow-empty"]))
            self.assertEqual(backup.verify_objects(str(manifest)), 0)

    def test_detects_s3_budget_and_download_mutation(self):
        with TemporaryDirectory() as folder:
            with patch.object(backup, "_s3_client_and_bucket", return_value=(
                FakeS3({"example.txt": b"1234", "other.txt": b"456"}), "private-test"
            )):
                with self.assertRaisesRegex(backup.BackupError, "limite"):
                    backup.backup_objects(s3_args(folder, extra=["--max-objects", "1"]))
            changing = FakeS3({"example.txt": b"abc"})
            changing.get_object = lambda **kwargs: {"Body": io.BytesIO(b"abcEXTRA")}
            with patch.object(backup, "_s3_client_and_bucket", return_value=(changing, "private-test")):
                with self.assertRaisesRegex(backup.BackupError, "mudou"):
                    backup.backup_objects(s3_args(folder))
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_detects_objects_missing_and_extra_files(self):
        with TemporaryDirectory() as folder:
            with patch.object(backup, "_s3_client_and_bucket", return_value=(FakeS3({"foo.txt": b"data"}), "private-test")):
                manifest = backup.backup_objects(s3_args(folder))
            (manifest.parent / "objects" / "orphan.bin").write_bytes(b"bad")
            with self.assertRaisesRegex(backup.BackupError, "extras"):
                backup.verify_objects(str(manifest))




class LegacyLocalBackupTests(unittest.TestCase):
    def test_local_snapshot_and_offline_verification(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "abc.txt").write_bytes(b"legacy-1")
            (source / "def.pdf").write_bytes(b"%PDF-legacy-2")
            manifest = backup._local_snapshot_from_rows(
                source, [("abc.txt", 8), ("def.pdf", 13)], str(root / "private"),
                max_files=10, max_total_mib=1,
            )
            self.assertEqual(backup.verify_local(str(manifest)), 2)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["kind"], "local-attachments")
            self.assertEqual({a["key"] for a in data["objects"]}, {"abc.txt", "def.pdf"})
            self.assertNotIn("abc.txt", str(list((manifest.parent / "objects").iterdir())))
            self.assertEqual((source / "abc.txt").read_bytes(), b"legacy-1")

    def test_detects_tampering_and_extra_or_missing_files(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            (src / "a.txt").write_bytes(b"abcd")
            manifest = backup._local_snapshot_from_rows(
                src, [("a.txt", 4)], str(root / "destination"),
                max_files=2, max_total_mib=1,
            )
            exported = next((manifest.parent / "objects").iterdir())
            exported.write_bytes(b"bad!")
            with self.assertRaisesRegex(backup.BackupError, "Integridade"):
                backup.verify_local(str(manifest))
            exported.write_bytes(b"abcd")
            (manifest.parent / "objects" / "extra.bin").write_bytes(b"extra")
            with self.assertRaisesRegex(backup.BackupError, "extras"):
                backup.verify_local(str(manifest))

    def test_missing_and_wrong_size_rejected_without_snapshot(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            (src / "exists.txt").write_bytes(b"abc")
            destination = root / "backup"
            for rows in ([('missing.txt', 3)], [('exists.txt', 20)]):
                with self.assertRaises(backup.BackupError):
                    backup._local_snapshot_from_rows(
                        src, rows, str(destination), max_files=2, max_total_mib=1,
                    )
            self.assertFalse(destination.exists())

    def test_rejects_traversal_duplicates_and_excess(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            src = root / "src"
            src.mkdir()
            (src / "exists.txt").write_bytes(b"abc")
            bad_sets = [
                [("../outside", 1)],
                [("a\\b", 1)],
                [("exists.txt", 3), ("exists.txt", 3)],
                [("exists.txt", -1)],
                [("exists.txt", 3), ("second.txt", 2)],
            ]
            for rows in bad_sets:
                with self.subTest(rows=rows):
                    with self.assertRaises(backup.BackupError):
                        backup._local_snapshot_from_rows(
                            src, rows, str(root / "out"), max_files=1, max_total_mib=1,
                        )
            with self.assertRaisesRegex(backup.BackupError, "Nao existem"):
                backup._local_snapshot_from_rows(src, [], str(root / "out"), max_files=1, max_total_mib=1)

    def test_disallows_backup_from_production_settings(self):
        from argparse import Namespace
        with self.assertRaisesRegex(backup.BackupError, "development"):
            backup.backup_local(Namespace(environment="production"))
        parser = backup._parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["local", "--out-dir", "private", "--environment", "production"])

if __name__ == "__main__":
    unittest.main()

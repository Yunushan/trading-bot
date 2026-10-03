"""Exercise the actual manifest confinement and source receipt boundary."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.integrations.exchanges.binance.orders import spot_indexed_intent_manifest as manifests
from app.integrations.exchanges.binance.orders.spot_indexed_intent_manifest import (
    decode_indexed_manifest, read_indexed_manifest, validate_indexed_manifest,
)
from app.settings.live_safety import LiveTradingSafetyError


class IndexedManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "synthetic.intents.json"
        self.backend_id, self.migration_id = str(uuid4()), str(uuid4())
        self.payload = {
            "format_version": 3, "storage_kind": "sqlite-spot-intents", "schema_version": 1,
            "store_id": str(uuid4()), "backend_id": self.backend_id,
            "database": f"{self.path.name}.{self.backend_id}.sqlite3",
            "migration_id": self.migration_id,
            "source_backup": f"{self.path.name}.v2-{self.migration_id}.backup",
            "source_sha256": "a" * 64, "created_at": "2026-10-03T00:00:00+00:00",
        }
        self.path.write_text(json.dumps(self.payload), encoding="utf-8")

    def test_generated_paths_require_existing_regular_files(self):
        receipt = read_indexed_manifest(self.path)
        target = self.path.parent / receipt.manifest.database
        with self.assertRaises(LiveTradingSafetyError):
            receipt.database_path(self.path)
        self.assertFalse(target.exists())
        target.mkdir()
        with self.assertRaises(LiveTradingSafetyError):
            receipt.database_path(self.path)
        target.rmdir()
        target.write_bytes(b"synthetic existing database")
        self.assertEqual(receipt.database_path(self.path), target)

    def test_receipt_path_resolvers_reject_other_namespace_and_replacement(self):
        receipt = read_indexed_manifest(self.path)
        other_dir = self.path.parent / "other"
        other_dir.mkdir()
        other_path = other_dir / "different.intents.json"
        for leaf, resolve in (
            (receipt.manifest.database, receipt.database_path),
            (receipt.manifest.source_backup, receipt.source_backup_path),
        ):
            with self.subTest(leaf=leaf):
                (other_dir / leaf).write_bytes(b"existing foreign storage")
                with self.assertRaises(LiveTradingSafetyError):
                    resolve(other_path)
                target = self.path.parent / leaf
                target.write_bytes(b"existing original storage")
                self.assertEqual(resolve(self.path), target)
        replacement = self.path.with_suffix(".replacement")
        replacement.write_bytes(receipt.raw)
        replacement.replace(self.path)
        for resolve in (receipt.database_path, receipt.source_backup_path):
            with self.assertRaises(LiveTradingSafetyError):
                resolve(self.path)

    def test_cross_directory_and_foreign_basename_payloads_reject(self):
        for field in ("database", "source_backup"):
            for value in ("../outside", "..\\outside", "/absolute", "C:\\outside", "foreign.sqlite3", ""):
                with self.subTest(field=field, value=value), self.assertRaises(LiveTradingSafetyError):
                    validate_indexed_manifest({**self.payload, field: value}, logical_path=self.path)

    def test_schema_and_identity_substitution_reject(self):
        mutations = [
            {"format_version": True}, {"schema_version": True}, {"schema_version": 2},
            {"storage_kind": "json"}, {"backend_id": str(uuid4())},
            {"migration_id": str(uuid4())}, {"source_sha256": "bad"}, {"store_id": 1},
            {"created_at": "2026-10-03"}, {"unexpected": "field"},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(LiveTradingSafetyError):
                validate_indexed_manifest({**self.payload, **mutation}, logical_path=self.path)

    def test_duplicate_field_and_oversize_reject(self):
        raw = json.dumps(self.payload).encode()
        with self.assertRaises(LiveTradingSafetyError):
            decode_indexed_manifest(raw[:-1] + b', "store_id": "other"}', logical_path=self.path)
        with self.assertRaises(LiveTradingSafetyError):
            decode_indexed_manifest(b" " * 16385, logical_path=self.path)
        with self.assertRaises(LiveTradingSafetyError):
            decode_indexed_manifest(b'{"nested":' + b'[' * 2000 + b'0' + b']' * 2000 + b'}', logical_path=self.path)

    def test_windows_cross_api_ctime_difference_keeps_content_identity_checks(self):
        original = os.fstat

        def descriptor_stat(descriptor):
            value = original(descriptor)
            return SimpleNamespace(
                st_dev=value.st_dev, st_ino=value.st_ino, st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns, st_ctime_ns=value.st_ctime_ns + 17, st_nlink=value.st_nlink,
            )

        with patch.object(manifests.sys, "platform", "win32"), patch.object(manifests.os, "fstat", descriptor_stat):
            receipt = read_indexed_manifest(self.path)
            receipt.assert_current(self.path)
        calls = 0

        def changed_descriptor(descriptor):
            nonlocal calls
            calls += 1
            value = descriptor_stat(descriptor)
            if calls > 1:
                value.st_mtime_ns += 1
            return value

        with patch.object(manifests.sys, "platform", "win32"), patch.object(manifests.os, "fstat", changed_descriptor):
            with self.assertRaises(LiveTradingSafetyError):
                read_indexed_manifest(self.path)

    def test_hard_linked_manifest_and_database_reject(self):
        receipt = read_indexed_manifest(self.path)
        linked = self.path.with_suffix(".hardlink")
        os.link(self.path, linked)
        with self.assertRaises(LiveTradingSafetyError):
            read_indexed_manifest(self.path)
        linked.unlink()
        database = self.path.parent / receipt.manifest.database
        database.write_bytes(b"synthetic")
        os.link(database, linked)
        with self.assertRaises(LiveTradingSafetyError):
            receipt.database_path(self.path)

    def test_same_bytes_file_replacement_invalidates_receipt(self):
        receipt = read_indexed_manifest(self.path)
        replacement = self.path.with_suffix(".replacement")
        replacement.write_bytes(receipt.raw)
        replacement.replace(self.path)
        with self.assertRaises(LiveTradingSafetyError):
            receipt.assert_current(self.path)

    def test_inplace_content_change_and_other_logical_path_reject(self):
        receipt = read_indexed_manifest(self.path)
        with self.assertRaises(LiveTradingSafetyError):
            receipt.assert_current(self.path.with_name("other.intents.json"))
        self.path.write_text(json.dumps({**self.payload, "store_id": str(uuid4())}), encoding="utf-8")
        with self.assertRaises(LiveTradingSafetyError):
            receipt.assert_current(self.path)


if __name__ == "__main__":
    unittest.main()

"""Actual filesystem change-clock probes for indexed warm validation anchors."""
from __future__ import annotations

import os
import mmap
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.integrations.exchanges.binance.orders import spot_indexed_file_identity as identity
from app.settings.live_safety import LiveTradingSafetyError


class IndexedFileIdentityTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory(prefix="trading-bot-indexed-change-clock-"))
        self.path = Path(directory) / "intents.sqlite3"
        self.path.write_bytes(b"same-length-record-A")

    def test_stable_receipt_uses_absolute_path(self):
        receipt = identity.capture_indexed_file_change(self.path)
        self.assertEqual(receipt.path, self.path.absolute())
        self.assertGreater(receipt.change_time, 0)
        self.assertEqual(receipt, identity.capture_indexed_file_change(self.path, checkpoint=False))
        receipt.assert_current()

    def test_raw_same_length_edit_with_restored_mtime_invalidates_receipt(self):
        receipt = identity.capture_indexed_file_change(self.path)
        previous = self.path.stat()
        with self.path.open("r+b") as handle:
            handle.seek(-1, os.SEEK_END)
            handle.write(b"B")
            handle.flush()
            os.fsync(handle.fileno())
        os.utime(self.path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        current = identity.capture_indexed_file_change(self.path, checkpoint=False)
        self.assertEqual(receipt.identity[:4], current.identity[:4])
        self.assertNotEqual((receipt.change_time, receipt.change_journal), (current.change_time, current.change_journal))
        with self.assertRaises(LiveTradingSafetyError):
            receipt.assert_current()

    def test_actual_sql_commit_with_restored_mtime_invalidates_receipt(self):
        self.path.unlink()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("CREATE TABLE records(value TEXT)")
            connection.execute("INSERT INTO records VALUES ('archived-A')")
            connection.commit()
            receipt = identity.capture_indexed_file_change(self.path)
            previous = self.path.stat()
            connection.execute("UPDATE records SET value='archived-B'")
            connection.commit()
            os.utime(self.path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
            current = identity.capture_indexed_file_change(self.path, checkpoint=False)
            self.assertEqual(receipt.identity[:4], current.identity[:4])
            self.assertNotEqual((receipt.change_time, receipt.change_journal), (current.change_time, current.change_journal))
            with self.assertRaises(LiveTradingSafetyError):
                receipt.assert_current()
        finally:
            connection.close()

    def test_replacement_with_equal_bytes_invalidates_receipt(self):
        receipt = identity.capture_indexed_file_change(self.path)
        replacement = self.path.with_suffix(".replacement")
        replacement.write_bytes(self.path.read_bytes())
        os.replace(replacement, self.path)
        with self.assertRaises(LiveTradingSafetyError):
            receipt.assert_current()

    def test_missing_directory_hardlink_and_directory_fail_closed(self):
        for candidate in (self.path.with_name("missing"), self.path.parent):
            with self.subTest(candidate=candidate), self.assertRaises(LiveTradingSafetyError):
                identity.capture_indexed_file_change(candidate)
        alias = self.path.with_name("hardlink")
        os.link(self.path, alias)
        for candidate in (self.path, alias):
            with self.subTest(candidate=candidate), self.assertRaises(LiveTradingSafetyError):
                identity.capture_indexed_file_change(candidate)

    def test_unavailable_change_clock_does_not_fall_back(self):
        with patch.object(identity, "_change_time", side_effect=LiveTradingSafetyError("Unavailable")):
            with self.assertRaises(LiveTradingSafetyError):
                identity.capture_indexed_file_change(self.path)

    @unittest.skipUnless(sys.platform == "win32", "Windows handle API")
    def test_windows_uses_journal_sequence_despite_unchanged_creation_time(self):
        receipt = identity.capture_indexed_file_change(self.path)
        previous = self.path.stat()
        self.path.write_bytes(b"same-length-record-B")
        os.utime(self.path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        current = identity.capture_indexed_file_change(self.path, checkpoint=False)
        self.assertEqual(receipt.identity[4], current.identity[4])
        self.assertNotEqual((receipt.change_time, receipt.change_journal), (current.change_time, current.change_journal))

    @unittest.skipUnless(sys.platform == "win32", "Windows per-file change journal")
    def test_rapid_raw_changes_with_open_sqlite_handle_and_restored_mtime(self):
        self.path.unlink()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute("CREATE TABLE records(value TEXT)")
            connection.execute("INSERT INTO records VALUES ('archived-A')")
            connection.commit()
            for index in range(300):
                receipt = identity.capture_indexed_file_change(self.path)
                before = self.path.stat()
                raw = self.path.read_bytes()
                old, new = (b"archived-A", b"archived-B") if index % 2 == 0 else (b"archived-B", b"archived-A")
                with self.path.open("r+b") as handle:
                    handle.seek(raw.index(old))
                    handle.write(new)
                    handle.flush()
                os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
                current = identity.capture_indexed_file_change(self.path, checkpoint=False)
                self.assertEqual(receipt.identity[:4], current.identity[:4])
                self.assertNotEqual(receipt.change_journal, current.change_journal)
                with self.assertRaises(LiveTradingSafetyError):
                    receipt.assert_current()
        finally:
            connection.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows per-file change journal")
    def test_unavailable_journal_has_no_clock_only_fallback(self):
        with patch.object(identity, "_windows_journal", side_effect=LiveTradingSafetyError("Unavailable journal")):
            with self.assertRaises(LiveTradingSafetyError):
                identity.capture_indexed_file_change(self.path)

    def test_usn_parser_fences_unsupported_corrupt_or_wrong_file_records(self):
        import struct
        raw = bytearray(64)
        struct.pack_into("<IHH", raw, 0, 64, 2, 0)
        struct.pack_into("<Q", raw, 8, 123)
        struct.pack_into("<q", raw, 24, 456)
        struct.pack_into("<HH", raw, 56, 0, 60)
        self.assertEqual((2, 123, 456), identity._decode_usn_record(bytes(raw), 123))
        corrupt = []
        for offset, format_text, value in ((0, "<I", 63), (4, "<H", 4), (6, "<H", 1),
                                           (8, "<Q", 999), (24, "<q", 0), (56, "<H", 3), (58, "<H", 2)):
            candidate = raw.copy()
            struct.pack_into(format_text, candidate, offset, value)
            corrupt.append(candidate)
        for candidate in [b"", *corrupt]:
            with self.subTest(record=bytes(candidate)), self.assertRaises(LiveTradingSafetyError):
                identity._decode_usn_record(bytes(candidate), 123)

    @unittest.skipUnless(sys.platform == "win32", "Windows native SQLite share guard")
    def test_guarded_sqlite_can_query_metadata_and_commit_while_foreign_handles_fail(self):
        self.path.unlink()
        connection = sqlite3.connect(self.path.as_uri() + "?exclusive=1", uri=True)
        try:
            connection.execute("CREATE TABLE records(value INTEGER)")
            connection.execute("INSERT INTO records VALUES (0)")
            connection.commit()
            for index in range(20):
                identity.assert_indexed_native_guard(self.path)
                before = identity.capture_indexed_file_change(self.path)
                before.assert_current()
                with self.assertRaises(OSError):
                    self.path.read_bytes()
                with self.assertRaises(OSError):
                    self.path.open("r+b")
                connection.execute("UPDATE records SET value=?", (index + 1,))
                connection.commit()
                identity.assert_indexed_native_guard(self.path)
                after = identity.capture_indexed_file_change(self.path)
                after.assert_current()
                self.assertNotEqual(before.change_journal, after.change_journal)
                self.assertEqual(connection.execute("SELECT value FROM records").fetchone(), (index + 1,))
        finally:
            connection.close()
        with self.assertRaises(LiveTradingSafetyError):
            identity.assert_indexed_native_guard(self.path)

    @unittest.skipUnless(sys.platform == "win32", "Windows mapping/share guard")
    def test_closed_descriptor_mapping_blocks_guard_acquisition(self):
        for access in (mmap.ACCESS_READ, mmap.ACCESS_WRITE, mmap.ACCESS_COPY):
            with self.subTest(access=access):
                descriptor = os.open(self.path, os.O_RDWR | os.O_BINARY)
                try:
                    mapping = mmap.mmap(descriptor, 0, access=access)
                finally:
                    os.close(descriptor)
                try:
                    with self.assertRaises(sqlite3.OperationalError):
                        sqlite3.connect(self.path.as_uri() + "?mode=rw&exclusive=1", uri=True)
                finally:
                    mapping.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows native guard proof")
    def test_no_guard_or_permission_denial_cannot_be_accepted_as_exclusion(self):
        original = self.path.read_bytes()
        with self.assertRaises(LiveTradingSafetyError):
            identity.assert_indexed_native_guard(self.path)
        self.assertEqual(original, self.path.read_bytes())
        for replies in (((None, 5),), ((None, 32), (None, 5)),
                        ((None, 32), (None, 32), (None, 5))):
            with self.subTest(replies=replies):
                with patch.object(identity, "_windows_create_file", side_effect=replies):
                    with self.assertRaises(LiveTradingSafetyError):
                        identity.assert_indexed_native_guard(self.path)
        with (patch.object(identity, "_windows_create_file", return_value=(123, 0)),
              patch.object(identity, "_windows_close_file") as close):
            with self.assertRaises(LiveTradingSafetyError):
                identity.assert_indexed_native_guard(self.path)
        close.assert_called_once_with(123)

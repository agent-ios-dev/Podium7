import struct
import unittest
from trust_cache_handoff import serialize
from ramdisk_handoff import attach_memory_file, attach_ramdisk
from test_device_tree_preparation import node


def container(raw, kind=b"rtsc"):
    def der(tag, body):
        length = len(body)
        encoded = bytes([length]) if length < 128 else bytes([0x82]) + length.to_bytes(2, "big")
        return bytes([tag]) + encoded + body
    return der(0x30, der(0x16, b"IM4P") + der(0x16, kind) + der(0x16, b"restore") + der(4, raw))


class TrustCacheTests(unittest.TestCase):
    def module(self, hashes=(bytes(20), bytes([1])*20)):
        return struct.pack("<I16sI", 1, bytes(range(16)), len(hashes)) + b"".join(h + bytes([2, 0]) for h in hashes)

    def test_serialized_region_preserves_official_module_bytes(self):
        raw = self.module()
        region, report = serialize(container(raw))
        self.assertEqual(len(region), 16384)
        self.assertEqual(region[:8], struct.pack("<II", 1, 8))
        self.assertEqual(region[8:8+len(raw)], raw)
        self.assertFalse(any(region[8+len(raw):]))
        self.assertEqual(report["entries"], 2)
        self.assertFalse(report["guest_registration_confirmed"])

    def test_truncated_unsupported_and_unsorted_modules_are_rejected(self):
        for raw in [self.module()[:-1], struct.pack("<I", 2)+self.module()[4:],
                    self.module((bytes([1])*20, bytes(20)))]:
            with self.assertRaises(ValueError): serialize(container(raw))
        with self.assertRaises(ValueError): serialize(container(self.module(), b"krnl"))

    def test_official_duplicate_hash_entries_are_preserved(self):
        raw = self.module((bytes(20), bytes(20)))
        region, report = serialize(container(raw))
        self.assertEqual(region[8:8+len(raw)], raw)
        self.assertEqual(report["entries"], 2)

    def test_system_cache_requires_explicit_correct_container_kind(self):
        raw = self.module()
        region, report = serialize(container(raw, b"trst"), kind=b"trst")
        self.assertEqual(region[8:8+len(raw)], raw)
        self.assertEqual(report["kind"], "trst")
        with self.assertRaises(ValueError):serialize(container(raw, b"trst"))
        with self.assertRaises(ValueError):serialize(container(raw), kind=b"trst")

    def test_trust_cache_and_ramdisk_reservations_coexist(self):
        tree = node([("name", b"device-tree\0")], [node([("name", b"chosen\0")])])
        tree = attach_memory_file(tree, 0x454e0000, 16384, "TrustCache")
        tree = attach_ramdisk(tree, 0x47e00000, 8192)
        for name, address, size in [("TrustCache", 0x454e0000, 16384), ("RAMDisk", 0x47e00000, 8192)]:
            self.assertIn(name.encode().ljust(32, b"\0") + struct.pack("<IQQ", 16, address, size), tree)
        with self.assertRaises(ValueError): attach_memory_file(tree, 0x454e0000, 16384, "TrustCache")
        with self.assertRaises(ValueError): attach_memory_file(tree, 0x454e0000, 16384, "Unrelated")

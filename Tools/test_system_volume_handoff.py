import struct
import unittest
from analyze_firmware import device_tree
from system_volume_handoff import attach
from test_device_tree_preparation import node


def tlv(tag, data):
    return bytes([tag, len(data)]) + data if len(data) < 128 else bytes([tag, 0x81, len(data)]) + data


def container(raw, kind=b"isys"):
    return tlv(0x30, tlv(0x16, b"IM4P") + tlv(0x16, kind) + tlv(0x16, b"0") + tlv(4, raw))


class SystemVolumeTests(unittest.TestCase):
    def setUp(self):
        self.raw = struct.pack("<4I", 2, 0, 1, 32) + bytes(range(192))
        self.tree = node([("name", b"device-tree\0")], [
            node([("name", b"chosen\0"), ("other", b"preserve")]),
            node([("name", b"unrelated\0"), ("reg", bytes(16))])])

    def test_exact_raw_data_at_chosen_and_other_nodes_preserved(self):
        changed, report = attach(self.tree, container(self.raw))
        nodes = device_tree(changed)
        self.assertIn(b"system-volume-auth-blob".ljust(32, b"\0") + struct.pack("<I", 208) + self.raw, changed)
        self.assertIn(b"other".ljust(32, b"\0") + struct.pack("<I", 8) + b"preserve", changed)
        self.assertEqual(next(n for n in nodes if n["path"].endswith("/unrelated")),
                         next(n for n in device_tree(self.tree) if n["path"].endswith("/unrelated")))
        self.assertFalse(report["guest_root_authenticated"])
        with self.assertRaises(ValueError): attach(changed, container(self.raw))

    def test_bad_kind_header_length_and_missing_chosen_rejected(self):
        for obj in [container(self.raw, b"trst"), container(self.raw[:-1]),
                    container(bytes(16)+self.raw[16:]), container(self.raw)[:-1]]:
            with self.assertRaises(ValueError): attach(self.tree, obj)
        with self.assertRaises(ValueError):
            attach(node([("name", b"device-tree\0")]), container(self.raw))

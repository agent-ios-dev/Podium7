import struct
import unittest
from analyze_firmware import device_tree
from prepare_device_tree import prepare


def node(properties, children=()):
    data = struct.pack("<II", len(properties), len(children))
    for name, value in properties:
        data += name.encode().ljust(32, b"\0") + struct.pack("<I", len(value) | 0x80000000) + value + bytes((-len(value)) & 3)
    return data + b"".join(children)


class DeviceTreePreparationTests(unittest.TestCase):
    def test_cpu_clocks_match_counter_and_other_devices_are_preserved(self):
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0"), ("timebase-frequency", bytes(4))])
        uart = node([("name", b"uart0\0"), ("reg", bytes(range(16)))])
        tree = node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]), uart])
        prepared, changes = prepare(tree, 24_000_000, random_seed=bytes(64))
        self.assertEqual(len(changes), 2)
        self.assertEqual(device_tree(prepared)[-1], device_tree(tree)[-1])
        self.assertIn(struct.pack("<Q", 24_000_000), prepared)
        again, _ = prepare(prepared, 24_000_000, random_seed=bytes(64))
        self.assertEqual(prepared, again)
    def test_no_cpu_and_bad_frequency_are_rejected(self):
        tree = node([("name", b"root\0")])
        with self.assertRaises(ValueError): prepare(tree, 24_000_000)
        with self.assertRaises(ValueError): prepare(tree, 0)
    def test_boot_seed_is_fresh_and_has_exact_required_length(self):
        cpu = node([("name", b"cpu0\0"), ("device_type", b"cpu\0")])
        tree = node([("name", b"device-tree\0")], [node([("name", b"cpus\0")], [cpu]), node([("name", b"chosen\0")])])
        first, changes = prepare(tree, 24_000_000)
        second, _ = prepare(tree, 24_000_000)
        self.assertNotEqual(first, second)
        self.assertEqual(changes[-1]["bytes"], 64)
        self.assertIn(b"random-seed", first)
        with self.assertRaises(ValueError): prepare(tree, 24_000_000, random_seed=bytes(32))

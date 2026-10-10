import struct
import unittest
from guest_processes import inspect, HASH_POINTER, HASH_MASK


class GuestProcessesTests(unittest.TestCase):
    def fixture(self, names=("launchd", "SpringBoard")):
        base = 0xffffffe100000000
        nodes = [base + 0x1000 + i * 0x1000 for i in range(len(names))]
        memory = {HASH_POINTER: struct.pack("<Q", base), HASH_MASK: struct.pack("<Q", 0),
                  base: struct.pack("<Q", nodes[0])}
        for i, (node, name) in enumerate(zip(nodes, names)):
            memory[node + 0x68] = struct.pack("<I", i + 1)
            memory[node + 0x370] = name.encode().ljust(32, b"\0")
            memory[node + 0xa8] = struct.pack("<Q", nodes[i+1] if i+1 < len(nodes) else 0)
        return memory, nodes

    def test_names_are_evidence_of_processes_not_visible_desktop(self):
        memory, _ = self.fixture()
        result = inspect(lambda address, size: memory[address])
        self.assertEqual(result["processes"], [{"pid": 1, "name": "launchd"},
                                               {"pid": 2, "name": "SpringBoard"}])
        self.assertTrue(result["springboard_process_seen"])
        self.assertFalse(result["visible_springboard_confirmed"])

    def test_cycle_rejected(self):
        memory, nodes = self.fixture()
        memory[nodes[-1] + 0xa8] = struct.pack("<Q", nodes[0])
        with self.assertRaisesRegex(ValueError, "cyclic"):
            inspect(lambda address, size: memory[address])

    def test_user_pointer_rejected_before_read(self):
        memory, _ = self.fixture()
        memory[HASH_POINTER] = struct.pack("<Q", 0x100000000)
        with self.assertRaisesRegex(ValueError, "hash layout"):
            inspect(lambda address, size: memory[address])

    def test_invalid_or_excessive_hash_mask_rejected(self):
        for mask in (2, 16383):
            memory, _ = self.fixture()
            memory[HASH_MASK] = struct.pack("<Q", mask)
            with self.assertRaisesRegex(ValueError, "hash layout"):
                inspect(lambda address, size: memory[address])

    def test_short_read_and_binary_name_rejected(self):
        memory, nodes = self.fixture()
        memory[nodes[0] + 0x370] = b"bad\x01".ljust(32, b"\0")
        with self.assertRaisesRegex(ValueError, "identity"):
            inspect(lambda address, size: memory[address])
        memory[HASH_POINTER] = b"short"
        with self.assertRaisesRegex(ValueError, "incomplete"):
            inspect(lambda address, size: memory[address])

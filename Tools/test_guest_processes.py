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
            memory[node + 0x28] = struct.pack("<I", i)
            memory[node + 0x20] = struct.pack("<Q", node + 0x500)
            memory[node + 0x500] = struct.pack("<Q", node)
            memory[node + 0x520] = struct.pack("<Q", node + 0x600)
            memory[node + 0x618] = struct.pack("<I", 0 if i == 0 else 501)
            memory[node + 0x370] = name.encode().ljust(32, b"\0")
            memory[node + 0xa8] = struct.pack("<Q", nodes[i+1] if i+1 < len(nodes) else 0)
        return memory, nodes

    def test_names_are_evidence_of_processes_not_visible_desktop(self):
        memory, _ = self.fixture()
        result = inspect(lambda address, size: memory[address])
        self.assertEqual(result["processes"], [{"pid": 1, "ppid": 0, "uid": 0, "name": "launchd"},
                                               {"pid": 2, "ppid": 1, "uid": 501, "name": "SpringBoard"}])
        self.assertTrue(result["springboard_process_seen"])
        self.assertFalse(result["visible_springboard_confirmed"])

    def test_cycle_rejected(self):
        memory, nodes = self.fixture()
        memory[nodes[-1] + 0xa8] = struct.pack("<Q", nodes[0])
        with self.assertRaisesRegex(ValueError, "cyclic"):
            inspect(lambda address, size: memory[address])

    def thread_fixture(self):
        memory, nodes = self.fixture(("xpcproxy",))
        task = nodes[0] + 0x10000
        thread = task + 0x1000
        for address, value in ((nodes[0] + 0x10, task), (task + 0x58, thread),
                               (thread + 0x3a8, task + 0x58),
                               (thread + 0x458, 123),
                               (thread + 0xd0, 0xfffffff0071ee97c)):
            memory[address] = struct.pack('<Q', value)
        memory[thread + 0x198] = struct.pack('<I', 1)
        return memory, task, thread

    def test_bounded_thread_metadata_without_user_memory(self):
        memory, _, _ = self.thread_fixture()
        result = inspect(lambda address, size: memory[address], thread_metadata=True)
        self.assertEqual(result['processes'][0]['threads'], [
            {'tid': 123, 'scheduler_state': 1,
             'kernel_continuation': '0xfffffff0071ee97c'}])
        self.assertFalse(result['backboardd_process_seen'])

    def test_thread_cycle_does_not_discard_process_identity(self):
        memory, _, thread = self.thread_fixture()
        memory[thread + 0x3a8] = struct.pack('<Q', thread)
        result = inspect(lambda address, size: memory[address], thread_metadata=True)
        self.assertEqual(result['processes'][0]['name'], 'xpcproxy')
        self.assertIn('cyclic', result['processes'][0]['thread_capture_error'])

    def test_user_continuation_rejected_and_empty_queue_allowed(self):
        memory, task, thread = self.thread_fixture()
        memory[thread + 0xd0] = struct.pack('<Q', 0x100000000)
        result = inspect(lambda address, size: memory[address], thread_metadata=True)
        self.assertIn('continuation', result['processes'][0]['thread_capture_error'])
        memory[task + 0x58] = struct.pack('<Q', task + 0x58)
        result = inspect(lambda address, size: memory[address], thread_metadata=True)
        self.assertEqual(result['processes'][0]['threads'], [])

    def test_credential_requires_kernel_pointer_and_matching_process(self):
        memory, nodes = self.fixture()
        memory[nodes[0] + 0x500] = struct.pack('<Q', nodes[1])
        with self.assertRaisesRegex(ValueError, 'back-reference'):
            inspect(lambda address, size: memory[address])
        memory[nodes[0] + 0x500] = struct.pack('<Q', nodes[0])
        memory[nodes[0] + 0x520] = struct.pack('<Q', 0x1000)
        with self.assertRaisesRegex(ValueError, 'bounded kernel'):
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

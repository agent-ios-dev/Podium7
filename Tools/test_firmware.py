import pathlib
import struct
import unittest
from analyze_firmware import der, payload, macho, device_tree, arm64_slice
from fetch_firmware import RemoteZIP


class FirmwareTests(unittest.TestCase):
    def test_fat_arm64_slice_and_bounds(self):
        header = struct.pack(">7I", 0xcafebabe, 1, 0x100000c, 0, 28, 4, 0)
        self.assertEqual(arm64_slice(header + b"test"), b"test")
        with self.assertRaises(ValueError):
            arm64_slice(header)
        with self.assertRaises(ValueError):
            arm64_slice(struct.pack(">II", 0xcafebabe, 100))
    def test_truncated_der(self):
        for data in [b"", b"\x30", b"\x30\x80", b"\x30\x05hi", b"\x30\x84\x01"]:
            with self.assertRaises(ValueError):
                der(data)

    def test_im4p_type_and_trailing_bytes(self):
        body = b"\x16\x04IM4P\x16\x04krnl\x16\x00\x04\x03abc"
        container = bytes([0x30, len(body)]) + body
        self.assertEqual(payload(container, b"krnl"), b"abc")
        for data, kind in [(container + b"x", b"krnl"), (container, b"dtre")]:
            with self.assertRaises(ValueError):
                payload(data, kind)

    def test_macho_bounds(self):
        for data in [b"", bytes(32), struct.pack("<8I", 0xfeedfacf, 0x100000c, 0, 2, 1, 72, 0, 0)]:
            with self.assertRaises(ValueError):
                macho(data)

    def test_device_tree_depth_and_bounds(self):
        self.assertEqual(device_tree(bytes(8)), [{"path": "/?", "properties": {}}])
        with self.assertRaises(ValueError):
            device_tree(struct.pack("<II", 1, 0))
        with self.assertRaises(ValueError):
            device_tree(bytes(9))

    def test_remote_zip_rejects_negative_seek(self):
        reader = RemoteZIP("https://example.invalid", 10)
        with self.assertRaises(ValueError):
            reader.seek(-1)
        reader.seek(9)
        reader.seek(-2, 1)
        self.assertEqual(reader.tell(), 7)


if __name__ == "__main__":
    unittest.main()

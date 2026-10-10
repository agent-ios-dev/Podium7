import io
import struct
import unittest
import zlib
from prepare_os_disk import relocate_gpt
from inspect_system_disk import inspect as inspect_disk
from inspect_system_disk import compare_readback
from fetch_firmware import RemoteZIP
from unittest.mock import patch
from qemu_probe import boot_args, make_probe, run_probe
import pathlib


class OSDiskTests(unittest.TestCase):
    def test_system_boot_profile_cannot_silently_use_ramdisk_or_blank_storage(self):
        with self.assertRaises(ValueError):
            boot_args(0, 0, 0, 0, ramdisk=True, system_root='disk0s1s1')
        with self.assertRaises(ValueError):
            make_probe(pathlib.Path('not-read'), ramdisk=pathlib.Path('not-read'), research_system_root='disk0s1s1')
        with self.assertRaisesRegex(ValueError, 'prepared 16 GiB'):
            run_probe(pathlib.Path('not-read'), research_system_root='disk0s1s1')
        args = boot_args(0, 0, 0, 0, system_root='disk0s1s1')
        self.assertIn(b'rd=disk0s1s1', args)
        self.assertNotIn(b'rd=md0', args)

    def disk(self):
        data = io.BytesIO(bytes(4096 * 512))
        mbr = bytearray(512);mbr[450] = 0xee;mbr[510:] = b'\x55\xaa'
        data.write(mbr)
        table = bytearray(16384);table[:16] = bytes(range(16))
        struct.pack_into('<QQ', table, 32, 34, 4000)
        data.seek(1024);data.write(table)
        data.seek((4095 - 32) * 512);data.write(table)
        for own, other, table_lba in ((1, 4095, 2), (4095, 1, 4095 - 32)):
            h = bytearray(512);h[:8] = b'EFI PART'
            struct.pack_into('<II', h, 8, 0x10000, 92)
            struct.pack_into('<QQQQ', h, 24, own, other, 34, 4062)
            struct.pack_into('<QIII', h, 72, table_lba, 128, 128, zlib.crc32(table))
            struct.pack_into('<I', h, 16, zlib.crc32(h[:92]))
            data.seek(own * 512);data.write(h)
        return data, table

    def test_expansion_relocates_backup_with_valid_crcs_and_preserves_partition(self):
        disk, table = self.disk()
        result = relocate_gpt(disk, 8192 * 512)
        self.assertEqual(result['new_last_lba'], 8191)
        disk.seek((8191 - 32) * 512);self.assertEqual(disk.read(16384), table)
        for lba in (1, 8191):
            disk.seek(lba * 512);h = bytearray(disk.read(512))
            crc = struct.unpack_from('<I', h, 16)[0];struct.pack_into('<I', h, 16, 0)
            self.assertEqual(zlib.crc32(h[:92]), crc)
        disk.seek(1024);self.assertEqual(disk.read(16384), table)

    def test_corrupt_primary_crc_rejected_before_writing(self):
        disk, _ = self.disk();disk.seek(512 + 24);disk.write(b'\x03')
        before = disk.getvalue()
        with self.assertRaisesRegex(ValueError, 'CRC'):relocate_gpt(disk, 8192 * 512)
        self.assertEqual(before, disk.getvalue())

    def test_read_only_disk_evidence_checks_crc_and_detects_real_apfs_prefix(self):
        disk, _ = self.disk()
        disk.seek(34 * 512 + 32); disk.write(b'NXSB')
        before = disk.getvalue()
        report = inspect_disk(disk)
        self.assertEqual(disk.getvalue(), before)
        self.assertEqual(report['partitions'][0]['first_lba'], 34)
        self.assertTrue(report['partitions'][0]['nxsb_at_offset32'])
        self.assertEqual(bytes.fromhex(report['sectors']['1'])[:8], b'EFI PART')
        disk.seek(1024); disk.write(b'\xff')
        with self.assertRaisesRegex(ValueError, 'table CRC'): inspect_disk(disk)

    def test_guest_dma_must_match_source_bytes_not_just_completion(self):
        layout = {'sectors': {'1': '454649'}}
        trace = 'PODIUM7 NVME-READBACK cid=6 lba=1 result=0 bytes=454649\n'
        self.assertTrue(compare_readback(layout, trace)['all_observed_match'])
        self.assertFalse(compare_readback(layout, trace.replace('454649', '000000'))['all_observed_match'])
        self.assertFalse(compare_readback(layout, trace.replace('result=0', 'result=1'))['all_observed_match'])
        self.assertFalse(compare_readback(layout, '')['all_observed_match'])

    def test_large_download_cache_stays_bounded_and_checks_ranges(self):
        payload = bytes(range(96))
        class Response(io.BytesIO):
            status = 206
            def __init__(self, start, end):
                super().__init__(payload[start:end + 1])
                self.headers = {'Content-Range': f'bytes {start}-{end}/96'}
        def fetch(request, timeout):
            start, end = map(int, request.headers['Range'][6:].split('-'))
            return Response(start, end)
        stream = RemoteZIP('https://example.test/firmware', 96, max_cache_blocks=2)
        stream.block = 16
        with patch('fetch_firmware.urllib.request.urlopen', side_effect=fetch):
            self.assertEqual(stream.read(96), payload)
            self.assertLessEqual(len(stream.cache), 2)
            stream.seek(0);self.assertEqual(stream.read(16), payload[:16])
            self.assertLessEqual(len(stream.cache), 2)

    def test_interleaved_readback_is_incomplete_not_a_source_mismatch(self):
        layout = {'sectors': {'1': '454649'}}
        broken = 'PODIUM7 NVME-READBACK cid=6 lba=1 result=0 bytes=4546PODIUM7 OTHER\n49\n'
        result = compare_readback(layout, broken)
        self.assertEqual(result['samples'], [])
        self.assertEqual(result['incomplete_records'], 1)
        self.assertFalse(result['all_observed_match'])

    def test_readback_source_range_uses_actual_transfer_length(self):
        disk, _ = self.disk()
        layout = inspect_disk(disk)
        disk.seek(512); data = disk.read(4096).hex()
        trace = 'PODIUM7 NVME-READBACK cid=6 lba=1 result=0 bytes=' + data + '\n'
        before = disk.getvalue()
        self.assertTrue(compare_readback(layout, trace, disk)['all_observed_match'])
        self.assertEqual(disk.getvalue(), before)


if __name__ == '__main__':unittest.main()

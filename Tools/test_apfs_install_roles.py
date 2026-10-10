import io
import struct
import unittest
import uuid

from apfs_install_roles import BLOCK, PROTECTED, ROLES, checksum, format_roles


def valid_checksum(block):
    # APFS verifies payload followed by the two checksum words.
    first = second = 0
    for (word,) in struct.iter_unpack('<I', block[8:] + block[:8]):
        first = (first + word) % 0xffffffff
        second = (second + first) % 0xffffffff
    return first == second == 0


class RoleFormattingTests(unittest.TestCase):
    def fixture(self):
        targets = [{'Name': name, 'APFSVolumeUUID': str(uuid.uuid4()), 'Roles': []}
                   for name in ROLES]
        blocks = [bytearray(BLOCK)]
        blocks[0][32:36] = b'NXSB'
        struct.pack_into('<I', blocks[0], 36, BLOCK)
        # Two historical versions per volume, plus the protected System.
        for target in targets + [{'Name': 'System', 'APFSVolumeUUID': str(uuid.UUID(bytes=PROTECTED))}]:
            for xid in (1, 2):
                block = bytearray(BLOCK)
                struct.pack_into('<Q', block, 16, xid)
                struct.pack_into('<I', block, 24, 13)
                block[32:36] = b'APSB'
                block[240:256] = uuid.UUID(target['APFSVolumeUUID']).bytes
                struct.pack_into('<Q', block, 264, 1)
                name = target['Name'].encode()
                block[704:704 + len(name)] = name
                if target['Name'] == 'System': struct.pack_into('<H', block, 964, 1)
                block[:8] = checksum(block)
                blocks.append(block)
        struct.pack_into('<Q', blocks[0], 40, len(blocks))
        blocks[0][:8] = checksum(blocks[0])
        return io.BytesIO(b''.join(blocks)), targets

    def test_history_roles_and_checksums_preserve_system_and_other_fields(self):
        stream, targets = self.fixture()
        before = stream.getvalue()
        self.assertTrue(all(valid_checksum(before[i:i + BLOCK]) for i in range(0, len(before), BLOCK)))
        report = format_roles(stream, targets, partition_start=0)
        after = stream.getvalue()
        self.assertEqual(len(report['superblock_edits']), 8)
        self.assertEqual(before[:BLOCK], after[:BLOCK])
        self.assertEqual(before[-2 * BLOCK:], after[-2 * BLOCK:])
        for edit in report['superblock_edits']:
            offset = edit['offset']
            old, new = before[offset:offset + BLOCK], after[offset:offset + BLOCK]
            self.assertTrue(valid_checksum(new))
            self.assertEqual(new[8:964], old[8:964])
            self.assertEqual(new[966:], old[966:])
            self.assertEqual(struct.unpack_from('<H', new, 964)[0], ROLES[edit['name']])

    def test_corruption_rejected_before_any_write(self):
        stream, targets = self.fixture()
        damaged = bytearray(stream.getvalue())
        damaged[8 * BLOCK + 1100] ^= 1
        stream = io.BytesIO(damaged)
        with self.assertRaisesRegex(ValueError, 'checksum'):
            format_roles(stream, targets, partition_start=0)
        self.assertEqual(stream.getvalue(), damaged)

    def test_encrypted_grouped_wrong_name_and_existing_role_rejected(self):
        for field in ('encryption', 'group', 'name', 'role'):
            with self.subTest(field=field):
                stream, targets = self.fixture()
                damaged = bytearray(stream.getvalue())
                block = damaged[BLOCK:2 * BLOCK]
                if field == 'encryption': struct.pack_into('<Q', block, 264, 0)
                if field == 'group': block[1008] = 1
                if field == 'name': block[704] ^= 1
                if field == 'role': struct.pack_into('<H', block, 964, 64)
                block[:8] = checksum(block)
                damaged[BLOCK:2 * BLOCK] = block
                stream = io.BytesIO(damaged)
                with self.assertRaises(ValueError): format_roles(stream, targets, partition_start=0)
                self.assertEqual(stream.getvalue(), damaged)

    def test_missing_uuid_and_protected_system_rejected(self):
        for protected in (False, True):
            stream, targets = self.fixture()
            before = stream.getvalue()
            targets[0]['APFSVolumeUUID'] = str(uuid.UUID(bytes=PROTECTED)) if protected else str(uuid.uuid4())
            with self.assertRaises(ValueError): format_roles(stream, targets, partition_start=0)
            self.assertEqual(stream.getvalue(), before)


if __name__ == '__main__': unittest.main()

"""Offline role formatting of freshly created, unencrypted guest APFS volumes.

Schema: https://developer.apple.com/support/downloads/Apple-File-System-Reference.pdf
Only newly created UUID/name pairs are eligible. System and Preboot are never
modified. Guest fsck and original APFS mount remain mandatory validation.
"""
import struct
import uuid

BLOCK = 4096
MOD = 0xffffffff
PROTECTED = uuid.UUID('C16ECAF9-9EC3-42EB-9553-B3DA1A53090F').bytes
ROLES = {'Data': 0x40, 'Update': 0xc0, 'xART': 0x100, 'Hardware': 0x140}


def checksum(block):
    if len(block) != BLOCK: raise ValueError('only 4096-byte APFS objects supported')
    total = weighted = 0
    for (word,) in struct.iter_unpack('<I', block[8:]):
        total += word
        weighted += total
    first = (MOD - (total + weighted) % MOD) % MOD
    second = (MOD - (total + first) % MOD) % MOD
    return struct.pack('<II', first, second)


def format_roles(stream, targets, *, partition_start=34 * 512):
    identities = {}
    for target in targets:
        name = target['Name']
        identity = uuid.UUID(target['APFSVolumeUUID']).bytes
        if name not in ROLES or identity == PROTECTED or identity in identities or target.get('Roles'):
            raise ValueError('only unique freshly created untagged guest volumes may be formatted')
        identities[identity] = name
    if len(identities) != 4 or set(identities.values()) != set(ROLES):
        raise ValueError('all four original iOS install roles are required')
    stream.seek(partition_start);nx = stream.read(BLOCK)
    if nx[32:36] != b'NXSB' or struct.unpack_from('<I', nx, 36)[0] != BLOCK or nx[:8] != checksum(nx):
        raise ValueError('invalid APFS container superblock')
    count = struct.unpack_from('<Q', nx, 40)[0]
    if not 1 <= count <= (16 << 30) // BLOCK:
        raise ValueError('APFS container outside fixed 16-GiB bounds')
    changes = []
    seen = set()
    # Read in bounded chunks; collect and validate all edits before writing.
    for begin in range(0, count, 256):
        stream.seek(partition_start + begin * BLOCK)
        chunk = stream.read(min(256, count - begin) * BLOCK)
        if len(chunk) != min(256, count - begin) * BLOCK: raise ValueError('truncated APFS container')
        position = chunk.find(b'APSB')
        while position >= 0:
            block_start = position - 32
            if block_start >= 0 and block_start % BLOCK == 0:
                block = chunk[block_start:block_start + BLOCK]
                identity = block[240:256]
                if identity in identities:
                    name = identities[identity]
                    if block[704:960].split(b'\0')[0] != name.encode() or (struct.unpack_from('<I', block, 24)[0] & 0xffff) != 13:
                        raise ValueError('guest volume identity/type mismatch')
                    if block[:8] != checksum(block) or struct.unpack_from('<H', block, 964)[0] != 0:
                        raise ValueError('guest volume checksum invalid or already tagged')
                    if struct.unpack_from('<Q', block, 264)[0] & 3 != 1 or any(block[1008:1024]):
                        raise ValueError('only unencrypted, ungrouped new volumes supported')
                    updated = bytearray(block)
                    struct.pack_into('<H', updated, 964, ROLES[name])
                    updated[:8] = checksum(updated)
                    changes.append((partition_start + begin * BLOCK + block_start, block, bytes(updated), name))
                    seen.add(identity)
                    if len(changes) > 1024: raise ValueError('unexpected volume history size')
            position = chunk.find(b'APSB', position + 4)
    if seen != set(identities): raise ValueError('not all fresh volume superblocks found')
    for offset, before, after, name in changes:
        stream.seek(offset)
        if stream.read(BLOCK) != before: raise ValueError('offline image changed during scan')
    for offset, before, after, name in changes:
        stream.seek(offset);stream.write(after)
    stream.flush()
    for offset, before, after, name in changes:
        stream.seek(offset)
        if stream.read(BLOCK) != after: raise ValueError('role metadata readback failed')
    return {'offline_guest_role_formatting': True,
            'superblock_edits': [{'offset': off, 'name': name, 'role': ROLES[name]}
                                 for off, before, after, name in changes],
            'system_volume_modified': False, 'preboot_volume_modified': False,
            'guest_fsck_required': True, 'authenticated_boot_confirmed': False}

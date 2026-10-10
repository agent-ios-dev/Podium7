"""Read-only GPT/APFS evidence from the prepared system disk."""
import argparse
import json
import pathlib
import re
import struct
import uuid
import zlib


def inspect(stream):
    stream.seek(0); mbr = stream.read(512)
    stream.seek(512); header = bytearray(stream.read(512))
    if header[:8] != b'EFI PART':
        raise ValueError('GPT signature missing')
    size, expected = struct.unpack_from('<II', header, 12)
    if not 92 <= size <= 512:
        raise ValueError('GPT header length invalid')
    checked = bytearray(header[:size]); struct.pack_into('<I', checked, 16, 0)
    if zlib.crc32(checked) != expected:
        raise ValueError('GPT header CRC invalid')
    table_lba, count, entry_size, crc = struct.unpack_from('<QIII', header, 72)
    if count != 128 or entry_size != 128:
        raise ValueError('unexpected GPT table dimensions')
    stream.seek(table_lba * 512); table = stream.read(count * entry_size)
    if zlib.crc32(table) != crc:
        raise ValueError('GPT table CRC invalid')
    result = {'sectors': {'0': mbr.hex(), '1': header.hex(), '2': table.hex()},
              'partitions': [], 'booted_ios': False}
    for index in range(count):
        entry = table[index * entry_size:(index + 1) * entry_size]
        if not any(entry[:16]): continue
        start, end, flags = struct.unpack_from('<QQQ', entry, 32)
        if start > end: raise ValueError('reversed partition extent')
        stream.seek(start * 512); prefix = stream.read(4096)
        result['partitions'].append({
            'index': index + 1, 'type_guid': str(uuid.UUID(bytes_le=entry[:16])),
            'first_lba': start, 'last_lba': end, 'attributes': hex(flags),
            'name': entry[56:128].decode('utf-16le').rstrip('\0'),
            'prefix_hex': prefix[:64].hex(), 'nxsb_at_offset32': prefix[32:36] == b'NXSB'})
    return result


def compare_readback(layout, trace, stream=None):
    samples = []
    for cid, lba, status, payload in re.findall(
            r'^PODIUM7 NVME-READBACK cid=(\d+) lba=(\d+) result=(-?\d+) bytes=([0-9a-f]*)\r?$', trace, re.MULTILINE):
        expected = layout['sectors'].get(lba)
        if stream is not None and len(payload) % 2 == 0 and 0 < len(payload) <= 32768 and int(lba) <= 2:
            stream.seek(int(lba) * 512)
            expected = stream.read(len(payload) // 2).hex()
        samples.append({'cid': int(cid), 'lba': int(lba), 'readback_status': int(status),
                        'bytes': len(payload) // 2,
                        'matches_source': status == '0' and bool(payload) and payload == expected})
    incomplete = trace.count('PODIUM7 NVME-READBACK cid=') - len(samples)
    return {'samples': samples, 'incomplete_records': incomplete,
            'all_observed_match': bool(samples) and not incomplete and all(
        s['matches_source'] for s in samples), 'booted_ios': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('disk', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--trace', type=pathlib.Path)
    args = parser.parse_args()
    with args.disk.open('rb') as stream:
        result = inspect(stream)
        if args.trace:
            result['dma_readback'] = compare_readback(result, args.trace.read_text(errors='replace'), stream)
    args.output.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'sectors'}, indent=2))

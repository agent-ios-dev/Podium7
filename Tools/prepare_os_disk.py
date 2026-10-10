"""Fetch official n112ap OS DMG with bounded RAM; convert on macOS.

Creates a fresh research disk only. No existing virtual machine is modified.
This prepares storage; it does not claim an iOS desktop has booted.
"""
import argparse
import hashlib
import json
import pathlib
import plistlib
import shutil
import struct
import subprocess
import sys
import zipfile
import zlib

from fetch_firmware import RemoteZIP, URL, SIZE

DISK_BYTES = 16 << 30


def relocate_gpt(stream, disk_bytes=DISK_BYTES):
    """Move the verified backup GPT to the new end; leave APFS extents intact."""
    stream.seek(512)
    primary = bytearray(stream.read(512))
    if primary[:8] != b'EFI PART':
        raise ValueError('primary GPT signature missing')
    header_size, crc = struct.unpack_from('<II', primary, 12)
    if not 92 <= header_size <= 512:
        raise ValueError('invalid GPT header size')
    checked = bytearray(primary[:header_size]);struct.pack_into('<I', checked, 16, 0)
    if zlib.crc32(checked) != crc:
        raise ValueError('GPT header CRC mismatch')
    table_lba, count, size, table_crc = struct.unpack_from('<QIII', primary, 72)
    if count != 128 or size != 128 or table_lba != 2:
        raise ValueError('unexpected official GPT table layout')
    stream.seek(table_lba * 512);table = stream.read(count * size)
    if zlib.crc32(table) != table_crc:
        raise ValueError('GPT table CRC mismatch')
    last = disk_bytes // 512 - 1
    old_last = struct.unpack_from('<Q', primary, 32)[0]
    if not 34 < old_last < last:
        raise ValueError('only expansion of a valid smaller disk is supported')
    stream.seek(old_last * 512);backup = bytearray(stream.read(512))
    if backup[:8] != b'EFI PART' or struct.unpack_from('<Q', backup, 24)[0] != old_last:
        raise ValueError('backup GPT missing')
    backup_size, backup_crc = struct.unpack_from('<II', backup, 12)
    checked = bytearray(backup[:backup_size]);struct.pack_into('<I', checked, 16, 0)
    if backup_size != header_size or zlib.crc32(checked) != backup_crc:
        raise ValueError('backup GPT header CRC mismatch')
    struct.pack_into('<Q', primary, 32, last)
    struct.pack_into('<QQ', backup, 24, last, 1)
    struct.pack_into('<Q', backup, 72, last - 32)
    for header in (primary, backup):
        struct.pack_into('<I', header, 16, 0)
        struct.pack_into('<I', header, 16, zlib.crc32(header[:header_size]))
    stream.truncate(disk_bytes)
    stream.seek(512);stream.write(primary)
    stream.seek((last - 32) * 512);stream.write(table);stream.write(backup)
    # Protective MBR describes the expanded disk; APFS/GPT partitions unchanged.
    stream.seek(0);mbr = bytearray(stream.read(512))
    if mbr[450] != 0xee or mbr[510:512] != b'\x55\xaa':
        raise ValueError('protective MBR missing')
    struct.pack_into('<I', mbr, 458, min(last, 0xffffffff))
    stream.seek(0);stream.write(mbr)
    return {'old_last_lba': old_last, 'new_last_lba': last,
            'partition_extents_unchanged': True, 'disk_bytes': disk_bytes}


def prepare(output):
    if sys.platform != 'darwin':
        raise RuntimeError('official LZFSE DMG conversion currently requires macOS hdiutil')
    output.mkdir(parents=True, exist_ok=True)
    dmg = output / 'SystemOS.dmg'
    raw = output / 'storage-16g.raw'
    if raw.exists():
        raise FileExistsError('existing research disk preserved')
    remote = RemoteZIP(URL, SIZE, max_cache_blocks=4)
    remote.block = 8 << 20
    with zipfile.ZipFile(remote) as archive:
        manifest = plistlib.loads(archive.read('BuildManifest.plist'))
        if manifest.get('SupportedProductTypes') != ['iPod9,1']:
            raise ValueError('wrong product')
        identity = next(i for i in manifest['BuildIdentities'] if
            i.get('Info', {}).get('DeviceClass') == 'n112ap' and 'Erase' in i['Info'].get('Variant', ''))
        member = identity['Manifest']['OS']['Info']['Path']
        info = archive.getinfo(member)
        if not 0 < info.file_size < 8 << 30:
            raise ValueError('unexpected OS size')
        report = {'source': URL, 'member': member, 'bytes': info.file_size,
                  'crc32': f'{info.CRC:08x}', 'booted_ios': False}
        if shutil.disk_usage(output).free < info.file_size + DISK_BYTES:
            raise RuntimeError('insufficient workspace disk capacity')
        if dmg.exists():
            saved = json.loads((output / 'os-download.json').read_text())
            if saved.get('crc32') != report['crc32'] or saved.get('bytes') != info.file_size:
                raise ValueError('cached official image metadata mismatch')
            digest = hashlib.sha256()
            with dmg.open('rb') as stream:
                while chunk := stream.read(8 << 20):digest.update(chunk)
            if dmg.stat().st_size != info.file_size or digest.hexdigest() != saved['sha256']:
                raise ValueError('cached OS digest mismatch')
        else:
            partial = dmg.with_suffix('.dmg.partial')
            digest = hashlib.sha256();total = 0
            with archive.open(info) as source, partial.open('xb') as target:
                while chunk := source.read(8 << 20):
                    target.write(chunk);digest.update(chunk);total += len(chunk)
                    if total % (256 << 20) < len(chunk):print(f'Official OS {total}/{info.file_size}', flush=True)
            if total != info.file_size:raise ValueError('truncated OS member')
            # ZipExtFile verifies the entire member CRC before EOF.
            report['sha256'] = digest.hexdigest()
            (output / 'os-download.json').write_text(json.dumps(report, indent=2))
            partial.rename(dmg)
    converted = output / 'converted-system'
    subprocess.run(['hdiutil', 'convert', str(dmg), '-format', 'UDTO', '-o', str(converted)], check=True)
    source = converted.with_suffix('.cdr')
    partial = raw.with_suffix('.raw.partial')
    with source.open('rb') as original, partial.open('xb+') as target:
        while chunk := original.read(1 << 20):
            if any(chunk):target.write(chunk)
            else:target.seek(len(chunk), 1)
        target.truncate(original.tell())
        gpt = relocate_gpt(target)
    partial.rename(raw)
    report['gpt'] = gpt
    report['disk_allocated_bytes'] = raw.stat().st_blocks * 512
    report['full_system_volume_prepared'] = True
    (output / 'os-disk.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    prepare(parser.parse_args().output)

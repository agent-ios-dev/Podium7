"""Read-only, bounded analysis of original keybag diagnostics; no binary export."""
import argparse
import hashlib
import json
import mmap
import pathlib
import plistlib
import struct
import subprocess
from prepare_install_layout import SYSTEM_UUID, command, fixture_container, mount_volume

MARKERS = (b'DIAGNOSTICS MODE ENABLED, SKIP INIT', b'DEVICE HAS EPHEMERAL DATA VOLUME',
           b'No SEP present', b'Gigalocker', b'MKBInitialize')


def mappings(data):
    if len(data) < 32 or not data[:16].startswith(b'dyld_v1'):
        raise ValueError('not a dyld shared cache')
    offset, count = struct.unpack_from('<II', data, 16)
    if not 1 <= count <= 64 or offset < 32 or offset + count * 32 > len(data):
        raise ValueError('invalid cache mapping table')
    result = []
    for index in range(count):
        address, size, file_offset, maximum, initial = struct.unpack_from('<QQQII', data, offset + index * 32)
        if file_offset + size > len(data) or address + size > 1 << 64 or initial & ~maximum:
            raise ValueError('cache mapping exceeds file or protection bounds')
        result.append((address, size, file_offset, initial))
    for index, item in enumerate(result):
        for other in result[:index]:
            if max(item[0], other[0]) < min(item[0] + item[1], other[0] + other[1]):
                raise ValueError('overlapping cache virtual mappings')
    return result


def adrp_page(word, pc):
    if word & 0x9f000000 != 0x90000000:
        return None
    immediate = ((word >> 5 & 0x7ffff) << 2) | (word >> 29 & 3)
    if immediate & (1 << 20): immediate -= 1 << 21
    return (pc & ~4095) + (immediate << 12)


def adr_target(word, pc):
    if word & 0x9f000000 != 0x10000000: return None
    immediate = ((word >> 5 & 0x7ffff) << 2) | (word >> 29 & 3)
    if immediate & (1 << 20): immediate -= 1 << 21
    return pc + immediate


def string_references(data, regions, targets):
    """Find bounded ADR and ADRP/ADD references, with matching source register."""
    pages = {target & ~4095 for target in targets}
    references = {target: [] for target in targets}
    for address, size, offset, protection in regions:
        if not protection & 4: continue
        if address % 4 or offset % 4: raise ValueError('unaligned executable cache mapping')
        for chunk_offset in range(0, size - size % 4, 8 << 20):
            length = min(8 << 20, size - chunk_offset)
            length -= length % 4
            chunk = data[offset + chunk_offset:offset + chunk_offset + length]
            for index, (word,) in enumerate(struct.iter_unpack('<I', chunk)):
                position = chunk_offset + index * 4
                target = adr_target(word, address + position)
                if target in references and len(references[target]) < 8:
                    references[target].append({'address': address + position, 'offset': offset + position,
                                               'mapping_start': offset, 'mapping_end': offset + size})
                if word & 0x9f000000 != 0x90000000: continue
                page = adrp_page(word, address + position)
                if page not in pages: continue
                register = word & 31
                # Only adjacent matching ADD is conclusive without dataflow.
                if position + 8 > size: continue
                next_word = struct.unpack_from('<I', data, offset + position + 4)[0]
                if next_word & 0xff000000 != 0x91000000 or (next_word >> 5 & 31) != register:
                    continue
                immediate = next_word >> 10 & 0xfff
                if next_word & (1 << 22): immediate <<= 12
                target = page + immediate
                if target in references and len(references[target]) < 8:
                    references[target].append({'address': address + position, 'offset': offset + position,
                                               'mapping_start': offset, 'mapping_end': offset + size})
    return references


def inspect_bytes(data, *, cache=False):
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
    regions = mappings(data) if cache else []
    symbol_table = indirect_table = None
    stub_sections, import_targets = [], {}
    if not cache:
        if len(data) < 32 or struct.unpack_from('<II', data) != (0xfeedfacf, 0x100000c):
            raise ValueError('expected original ARM64 executable')
        count, command_bytes = struct.unpack_from('<II', data, 16)
        if count > 4096 or command_bytes > len(data) - 32: raise ValueError('Mach-O commands out of bounds')
        cursor = 32
        for _ in range(count):
            if cursor + 8 > 32 + command_bytes: raise ValueError('truncated Mach-O command')
            kind, size = struct.unpack_from('<II', data, cursor)
            if size < 8 or cursor + size > 32 + command_bytes: raise ValueError('invalid Mach-O command')
            if kind == 0x19:
                if size < 72: raise ValueError('short Mach-O segment')
                address, _, offset, file_size, maximum, initial = struct.unpack_from('<QQQQII', data, cursor + 24)
                if offset + file_size > len(data): raise ValueError('Mach-O segment exceeds file')
                if file_size: regions.append((address, file_size, offset, initial))
                section_count = struct.unpack_from('<I', data, cursor + 64)[0]
                if 72 + section_count * 80 > size: raise ValueError('Mach-O sections exceed command')
                for section in range(section_count):
                    position = cursor + 72 + section * 80
                    section_address, section_size = struct.unpack_from('<QQ', data, position + 32)
                    flags, first_index, stride = struct.unpack_from('<III', data, position + 64)
                    if flags & 255 == 8:
                        if not 4 <= stride <= 64 or section_size % stride: raise ValueError('invalid symbol stub stride')
                        stub_sections.append((section_address, section_size // stride, first_index, stride))
            elif kind == 2:
                if size < 24: raise ValueError('short symbol table command')
                symbol_table = struct.unpack_from('<IIII', data, cursor + 8)
            elif kind == 0xb:
                if size < 80: raise ValueError('short indirect symbol command')
                indirect_table = struct.unpack_from('<II', data, cursor + 56)
            cursor += size
        if symbol_table and indirect_table:
            symbols, symbol_count, strings, string_size = symbol_table
            indirect, indirect_count = indirect_table
            if symbols + symbol_count * 16 > len(data) or strings + string_size > len(data) or indirect + indirect_count * 4 > len(data):
                raise ValueError('symbol table exceeds file')
            for address, count, first, stride in stub_sections:
                if first + count > indirect_count or count > 10000: raise ValueError('stub index exceeds table')
                for index in range(count):
                    symbol = struct.unpack_from('<I', data, indirect + (first + index) * 4)[0]
                    if symbol & 0xc0000000: continue
                    if symbol >= symbol_count: raise ValueError('indirect symbol exceeds table')
                    name_index = struct.unpack_from('<I', data, symbols + symbol * 16)[0]
                    if name_index >= string_size: raise ValueError('symbol string exceeds table')
                    end = data.find(b'\0', strings + name_index, min(strings + string_size, strings + name_index + 256))
                    if end < 0: continue
                    name = data[strings + name_index:end].decode('ascii', errors='replace')
                    import_targets[address + index * stride] = name
    found = []
    for marker in MARKERS:
        cursor = 0
        for _ in range(8):
            position = data.find(marker, cursor)
            if position < 0: break
            cursor = position + len(marker)
            owners = [r for r in regions if r[2] <= position < r[2] + r[1]]
            if len(owners) != 1: continue
            region = owners[0]
            # A marker may follow a log prefix; code references the C-string start.
            start = data.rfind(b'\0', max(region[2], position - 128), position) + 1
            if start < max(region[2], position - 128): start = position
            found.append({'marker': marker.decode(), 'address': region[0] + start - region[2], 'offset': start})
    references = string_references(data, regions, {item['address'] for item in found}) if found else {}
    decoder = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    for item in found:
        item['references'] = []
        for ref in references[item['address']]:
            # A small decoded window for branch conditions, never raw bytes.
            start = max(ref['mapping_start'], ref['offset'] - 128)
            end = min(ref['mapping_end'], ref['offset'] + 128)
            pc = ref['address'] + start - ref['offset']
            instructions = [{'address': hex(ins.address), 'mnemonic': ins.mnemonic, 'operands': ins.op_str}
                            for ins in decoder.disasm(data[start:end], pc)]
            for instruction in instructions:
                if instruction['mnemonic'] in ('bl', 'b') and instruction['operands'].startswith('#0x'):
                    callee = import_targets.get(int(instruction['operands'][1:], 16))
                    if callee: instruction['imported_callee'] = callee
            item['references'].append({'address': hex(ref['address']), 'instructions': instructions})
        item['address'] = hex(item['address'])
    return {'bytes': len(data), 'markers': found, 'binary_exported': False}


def inspect(image):
    root = pathlib.Path.cwd().resolve() / '.firmware'
    image = pathlib.Path(image).resolve()
    if image != root / 'system-disk/storage-16g.raw' or image.stat().st_size != 16 << 30:
        raise ValueError('only isolated fixed 16-GiB downloaded fixture is permitted')
    attached = plistlib.loads(command(['hdiutil', 'attach', '-readonly', '-nomount', '-plist',
                                      '-imagekey', 'diskimage-class=CRawDiskImage', str(image)]))
    devices = [entry['dev-entry'] for entry in attached.get('system-entities', []) if entry.get('dev-entry')]
    if not devices: raise ValueError('fixture attachment returned no device')
    whole = min(devices, key=len)
    report = {'read_only': True, 'binary_exported': False, 'files': []}
    try:
        container = fixture_container(whole)
        systems = [volume for volume in container.get('Volumes', [])
                   if volume.get('APFSVolumeUUID') == SYSTEM_UUID and volume.get('Roles') == ['System']]
        if len(systems) != 1 or len(container.get('Volumes', [])) != 1:
            raise ValueError('expected unchanged official single System-volume fixture')
        source = mount_volume(systems[0], root / 'keybag-system', readonly=True)
        candidates = [source / 'usr/libexec' / name for name in ('keybagd', 'init_data_protection')]
        cache_directory = source / 'System/Library/Caches/com.apple.dyld'
        if not cache_directory.resolve().is_relative_to(source): raise ValueError('cache path escapes image')
        if cache_directory.is_dir():
            candidates += sorted(cache_directory.glob('dyld_shared_cache_arm64*'))[:16]
        for candidate in candidates:
            if not candidate.resolve().is_relative_to(source): raise ValueError('analysis path escapes image')
            if not candidate.is_file(): continue
            if candidate.stat().st_size > 4 << 30: raise ValueError('unexpected cache/executable size')
            if candidate.name.endswith('.map'): continue
            print('Inspecting ' + str(candidate.relative_to(source)), flush=True)
            with candidate.open('rb') as stream:
                with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                    item = {'path': str(candidate.relative_to(source)), 'sha256': hashlib.sha256(data).hexdigest()}
                    try: item.update(inspect_bytes(data, cache=candidate.name.startswith('dyld_shared_cache')))
                    except ValueError as error: item['unsupported_layout'] = str(error)
                    report['files'].append(item)
    finally:
        command(['hdiutil', 'detach', whole])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try: report = inspect(args.disk)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report = {'inspection_error': str(error), 'binary_exported': False}
        if isinstance(error, subprocess.CalledProcessError): report['command_output'] = error.output.decode(errors='replace')
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    if 'inspection_error' in report: raise SystemExit(1)

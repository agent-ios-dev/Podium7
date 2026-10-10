"""Recover only an allowlisted launch label from original xpcproxy argv.

No argv/environment bytes are returned. Layout is for the hash-gated 19H422
kernel: sysctl procargs2 0xfffffff0075ed578, get_task_pmap 0xfffffff007229280,
and original 16-KiB pmap walker 0xfffffff0072cc610.
"""
import struct


def inspect(proc, read_kernel, read_physical, allowed_labels):
    def word(address):
        if not 0xffffffe000000000 <= address < 0xfffffffffffffff8 or address % 8:
            raise ValueError('invalid proxy kernel metadata pointer')
        return struct.unpack('<Q', read_kernel(address, 8))[0]

    def physical(address, size):
        # This research machine has exactly 2 GiB DRAM at 0x40000000.
        # Never inspect MMIO or use an unconstrained descriptor address.
        if not 0x40000000 <= address <= 0xc0000000 - size:
            raise ValueError('proxy translation is outside research DRAM')
        value = read_physical(address, size)
        if len(value) != size:
            raise ValueError('incomplete proxy physical read')
        return value

    argslen, argc = struct.unpack('<II', read_kernel(proc + 0x340, 8))
    stack = word(proc + 0x348)
    if not 2 <= argc <= 16 or not 32 <= argslen <= 262144 or not argslen < stack < (1 << 39):
        raise ValueError('invalid bounded proxy argument layout')
    task = word(proc + 0x10)
    pmap = word(word(task + 0x28) + 0x40)
    root = word(pmap)
    cache = {}

    def byte(address):
        aligned = address & ~7
        if aligned not in cache:
            if len(cache) >= 128:
                raise ValueError('proxy argument metadata limit exceeded')
            descriptor = word(root + ((aligned >> 36) & 7) * 8)
            for shift in (36, 25, 14):
                kind = descriptor & 3
                if kind == 1 and shift != 14:
                    pa = (descriptor & 0xfffffffff000 & ~((1 << shift) - 1)) | (aligned & ((1 << shift) - 1))
                    break
                if kind != 3:
                    raise ValueError('unmapped proxy argument page')
                if shift == 14:
                    pa = (descriptor & 0xffffffffc000) | (aligned & 0x3fff)
                    break
                next_shift = 25 if shift == 36 else 14
                entry = (descriptor & 0xffffffffc000) + ((aligned >> next_shift) & 0x7ff) * 8
                descriptor = struct.unpack('<Q', physical(entry, 8))[0]
            cache[aligned] = physical(pa, 8)
        return cache[aligned][address & 7]

    cursor, end = stack - argslen, stack
    def string():
        nonlocal cursor
        result = bytearray()
        while cursor < end and len(result) <= 255:
            value = byte(cursor); cursor += 1
            if not value:
                return bytes(result)
            result.append(value)
        raise ValueError('invalid bounded proxy argument string')

    executable = string()
    if executable != b'executable_path=/usr/libexec/xpcproxy':
        raise ValueError('unexpected proxy executable argument layout')
    while cursor < end and not byte(cursor):
        cursor += 1
    if string() != b'/usr/libexec/xpcproxy':
        raise ValueError('unexpected proxy argv0')
    label_bytes = string()
    try:
        label = label_bytes.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('invalid proxy service label') from None
    if label not in allowed_labels:
        raise ValueError('proxy label is absent from original launch metadata')
    return label

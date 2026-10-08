"""Strict IM4P/LZFSE, Mach-O and Apple device-tree inspection (macOS).

Uses the OS compression library. Produces evidence, never a claimed iOS boot.
"""
import argparse
import ctypes
import hashlib
import json
import pathlib
import struct


def der(data, offset=0):
    if offset + 2 > len(data):
        raise ValueError("truncated DER")
    tag, length = data[offset], data[offset + 1]
    cursor = offset + 2
    if length & 128:
        count = length & 127
        if count == 0 or count > 4 or cursor + count > len(data):
            raise ValueError("unsupported DER length")
        length = int.from_bytes(data[cursor:cursor + count], "big")
        cursor += count
    end = cursor + length
    if end > len(data):
        raise ValueError("truncated DER body")
    return tag, data[cursor:end], end


def payload(data, expected):
    tag, body, end = der(data)
    if tag != 0x30 or end != len(data):
        raise ValueError("expected complete IM4P sequence")
    cursor, fields = 0, []
    while cursor < len(body):
        tag, value, cursor = der(body, cursor)
        fields.append((tag, value))
    if len(fields) < 4 or fields[0] != (0x16, b"IM4P") or fields[1] != (0x16, expected) or fields[3][0] != 4:
        raise ValueError("incorrect IM4P type/fields")
    return fields[3][1]


def decompress(data):
    if data[:4] != b"bvx2" and data[:4] != b"bvx-" and data[:4] != b"bvxn":
        raise ValueError("expected unencrypted LZFSE payload")
    library = ctypes.CDLL("/usr/lib/libcompression.dylib")
    decode = library.compression_decode_buffer
    decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_int]
    decode.restype = ctypes.c_size_t
    source = ctypes.create_string_buffer(data)
    maximum = 128 * 1024 * 1024
    destination = ctypes.create_string_buffer(maximum)
    count = decode(destination, maximum, source, len(data), None, 0x801)
    if count == 0 or count == maximum:
        raise ValueError("LZFSE decode failed or output exceeded limit")
    return destination.raw[:count]


def arm64_slice(data):
    if data[:4] not in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
        return data
    if len(data) < 8:
        raise ValueError("truncated fat Mach-O")
    count = struct.unpack_from(">I", data, 4)[0]
    wide = data[:4] == b"\xca\xfe\xba\xbf"
    stride = 32 if wide else 20
    if count > 64 or 8 + count * stride > len(data):
        raise ValueError("fat architecture bounds")
    slices = []
    for index in range(count):
        cursor = 8 + index * stride
        cpu, subtype = struct.unpack_from(">II", data, cursor)
        offset, size = struct.unpack_from(">QQ" if wide else ">II", data, cursor + 8)
        if offset > len(data) or size > len(data) - offset or offset < 8 + count * stride:
            raise ValueError("fat slice out of file bounds")
        if cpu == 0x100000c and subtype & 0xffffff in (0, 1):
            slices.append(data[offset:offset + size])
    if len(slices) != 1:
        raise ValueError("expected one ARM64 (non-arm64e) kernel slice")
    return slices[0]


def macho(data):
    if len(data) < 32:
        raise ValueError("truncated Mach-O")
    magic, cpu, subtype, filetype, commands, command_bytes, flags, reserved = struct.unpack_from("<8I", data)
    if magic != 0xfeedfacf or cpu != 0x100000c or commands > 10000 or command_bytes > len(data) - 32:
        raise ValueError(f"not bounded ARM64 Mach-O: magic={magic:x} cpu={cpu:x} bytes={len(data)} commands={commands}/{command_bytes}")
    cursor, segments, entry = 32, [], None
    for _ in range(commands):
        if cursor + 8 > 32 + command_bytes:
            raise ValueError("truncated load command")
        command, size = struct.unpack_from("<II", data, cursor)
        if size < 8 or cursor + size > 32 + command_bytes:
            raise ValueError("invalid command size")
        if command == 0x19:
            if size < 72:
                raise ValueError("truncated segment")
            name = data[cursor + 8:cursor + 24].rstrip(b"\0").decode("ascii")
            address, length, offset, file_size = struct.unpack_from("<4Q", data, cursor + 24)
            if file_size > length or offset > len(data) or file_size > len(data) - offset:
                raise ValueError("segment out of file bounds")
            segments.append({"name": name, "address": hex(address), "length": length, "offset": offset, "file_size": file_size})
        if command == 5:
            if size < 288 or struct.unpack_from("<II", data, cursor + 8) != (6, 68):
                raise ValueError("unsupported thread state")
            entry = struct.unpack_from("<Q", data, cursor + 16 + 32 * 8)[0]
        cursor += size
    if cursor != 32 + command_bytes or entry is None:
        raise ValueError("command table incomplete or kernel entry absent")
    for segment in segments:
        address = int(segment["address"], 16)
        if address <= entry < address + segment["file_size"]:
            offset = segment["offset"] + entry - address
            opcode = struct.unpack_from("<I", data, offset)[0]
            windows = {}
            if opcode & 0xfc000000 == 0x14000000:
                displacement = opcode & 0x3ffffff
                if displacement & 0x2000000:
                    displacement -= 0x4000000
                target = entry + displacement * 4
                for destination in segments:
                    base = int(destination["address"], 16)
                    if base <= target and target + 256 <= base + destination["file_size"]:
                        start = destination["offset"] + target - base
                        windows[hex(target)] = [hex(x[0]) for x in struct.iter_unpack("<I", data[start:start + 256])]
            return {"entry": hex(entry), "segments": segments, "entry_words": [hex(x[0]) for x in struct.iter_unpack("<I", data[offset:offset + 64])], "bootstrap_windows": windows, "sha256": hashlib.sha256(data).hexdigest()}
    raise ValueError("entry not backed by segment bytes")


def device_tree(data, *, clear_bootloader_flags=False):
    nodes = []
    prepared = bytearray(data)
    def node(cursor, parent, depth):
        if depth > 64 or cursor + 8 > len(data) or len(nodes) > 10000:
            raise ValueError("device tree bounds/depth exceeded")
        count, children = struct.unpack_from("<II", data, cursor)
        cursor += 8
        if count > 10000 or children > 10000:
            raise ValueError("invalid device tree counts")
        properties = {}
        for _ in range(count):
            if cursor + 36 > len(data):
                raise ValueError("truncated device tree property")
            name = data[cursor:cursor + 32].split(b"\0")[0].decode("ascii")
            size = struct.unpack_from("<I", data, cursor + 32)[0] & 0x7fffffff
            if clear_bootloader_flags:
                struct.pack_into("<I", prepared, cursor + 32, size)
            cursor += 36
            if cursor + size > len(data):
                raise ValueError("truncated property body")
            properties[name] = data[cursor:cursor + size]
            cursor += (size + 3) & ~3
        path = parent + "/" + properties.get("name", b"?").split(b"\0")[0].decode("ascii", errors="replace")
        interesting = {key: value.hex() for key, value in properties.items() if path == "/device-tree/arm-io/pmgr" or key in ("reg", "ranges", "compatible", "device_type", "interrupts", "ipid-mask", "chip-id", "board-id", "model")}
        nodes.append({"path": path, "properties": interesting})
        for _ in range(children):
            cursor = node(cursor, path, depth + 1)
        return cursor
    consumed = node(0, "", 0)
    if consumed != len(data):
        raise ValueError("trailing device tree data")
    return bytes(prepared) if clear_bootloader_flags else nodes


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=pathlib.Path, default=pathlib.Path(".firmware"))
    directory = parser.parse_args().directory
    kernel = arm64_slice(decompress(payload((directory / "KernelCache.im4p").read_bytes(), b"krnl")))
    tree = decompress(payload((directory / "DeviceTree.im4p").read_bytes(), b"dtre"))
    analysis = {"kernel": macho(kernel), "device_tree": device_tree(tree)}
    (directory / "KernelCache.macho").write_bytes(kernel)
    (directory / "DeviceTree.bin").write_bytes(tree)
    (directory / "analysis.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print(json.dumps(analysis["kernel"], indent=2))
    print("Device-tree nodes:", len(analysis["device_tree"]))

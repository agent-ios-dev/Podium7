"""Raw HFS restore disk handoff; never reports a successful guest mount.
Apple xnu-8019.80.24 iokit/bsddev/IOKitBSDInit.cpp consumes two uintptr_t
values at /chosen/memory-map/RAMDisk and selects the device with rd=md0.
"""
import struct
from analyze_firmware import device_tree


def validate_hfs(image):
    if len(image) < 1536 or len(image) % 512:
        raise ValueError("ramdisk must be a sector-aligned raw HFS image")
    signature, version = struct.unpack_from(">HH", image, 1024)
    if (signature, version) not in [(0x482b, 4), (0x4858, 5)]:
        raise ValueError("ramdisk is not raw HFS+/HFSX")
    block_size, blocks = struct.unpack_from(">II", image, 1064)
    if block_size < 512 or block_size & (block_size - 1) or not blocks:
        raise ValueError("invalid HFS allocation geometry")
    if not block_size * blocks <= len(image) < block_size * (blocks + 1):
        raise ValueError("HFS allocation geometry differs from image length")
    return {"filesystem": "HFSX" if signature == 0x4858 else "HFS+",
            "bytes": len(image), "block_size": block_size, "blocks": blocks}


def attach_ramdisk(tree, address, size):
    device_tree(tree)
    if address < 0 or address % 16384 or size <= 0 or size % 4096 or address + size > 2**64:
        raise ValueError("invalid ramdisk physical range")
    def prop(name, value):
        return name.encode().ljust(32, b"\0") + struct.pack("<I", len(value)) + value + bytes((-len(value)) & 3)
    def memory_node():
        return struct.pack("<II", 2, 0) + prop("name", b"memory-map\0") + prop("RAMDisk", struct.pack("<QQ", address, size))
    found = False
    def walk(cursor, parent):
        nonlocal found
        count, children = struct.unpack_from("<II", tree, cursor)
        cursor += 8
        properties = []
        for _ in range(count):
            key = tree[cursor:cursor+32].split(b"\0", 1)[0].decode("ascii")
            length = struct.unpack_from("<I", tree, cursor+32)[0] & 0x7fffffff
            cursor += 36
            value = tree[cursor:cursor+length]
            cursor += (length+3) & ~3
            properties.append((key, value))
        path = parent + "/" + dict(properties).get("name", b"?").split(b"\0", 1)[0].decode("ascii")
        parts = []
        child_names = []
        for _ in range(children):
            encoded, cursor, child_path = walk(cursor, path)
            parts.append(encoded)
            child_names.append(child_path)
        if path == "/device-tree/chosen/memory-map":
            if any(key == "RAMDisk" for key, _ in properties):
                raise ValueError("existing RAMDisk reservation must not be overwritten")
            properties.append(("RAMDisk", struct.pack("<QQ", address, size)))
            found = True
        if path == "/device-tree/chosen" and path + "/memory-map" not in child_names:
            parts.append(memory_node())
            found = True
        encoded = struct.pack("<II", len(properties), len(parts))
        encoded += b"".join(prop(key, value) for key, value in properties) + b"".join(parts)
        return encoded, cursor, path
    result, _, _ = walk(0, "")
    if not found:
        raise ValueError("device tree has no chosen node")
    device_tree(result)
    return result

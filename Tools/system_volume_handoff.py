"""Forward the official isys payload as /chosen/system-volume-auth-blob.

The original 19H422 APFS extractor reads OSData from /chosen, not a memory
reservation or an IM4P wrapper. This does not authenticate an iBoot chain.
"""
import hashlib
import struct
from analyze_firmware import device_tree, payload


def attach(tree, container):
    raw = payload(container, b"isys")
    # Observed official v2 SHA256 structure: 16-byte header and three
    # 64-byte digest slots. Preserve every byte, including reserved fields.
    if len(raw) != 208 or struct.unpack_from("<4I", raw) != (2, 0, 1, 32):
        raise ValueError("unsupported official SystemVolume auth payload")
    device_tree(tree)
    found = False
    def walk(cursor, parent):
        nonlocal found
        count, children = struct.unpack_from("<II", tree, cursor)
        cursor += 8
        props = []
        for _ in range(count):
            key = tree[cursor:cursor+32]
            length = struct.unpack_from("<I", tree, cursor+32)[0] & 0x7fffffff
            cursor += 36
            props.append((key, tree[cursor:cursor+length]))
            cursor += (length+3) & ~3
        names = {k.split(b"\0")[0]: v for k, v in props}
        path = parent + "/" + names.get(b"name", b"?").split(b"\0")[0].decode("ascii")
        parts = []
        for _ in range(children):
            encoded, cursor = walk(cursor, path)
            parts.append(encoded)
        if path == "/device-tree/chosen":
            if b"system-volume-auth-blob" in names:
                raise ValueError("existing system volume auth blob must not be overwritten")
            props.append((b"system-volume-auth-blob".ljust(32, b"\0"), raw))
            found = True
        encoded = struct.pack("<II", len(props), len(parts))
        for key, value in props:
            encoded += key + struct.pack("<I", len(value)) + value + bytes((-len(value)) & 3)
        return encoded + b"".join(parts), cursor
    result, _ = walk(0, "")
    if not found:
        raise ValueError("system volume auth handoff requires /chosen")
    device_tree(result)
    return result, {"path": "/device-tree/chosen", "property": "system-volume-auth-blob",
                    "bytes": len(raw), "payload_sha256": hashlib.sha256(raw).hexdigest(),
                    "container_sha384": hashlib.sha384(container).hexdigest(),
                    "source": "official IPSW SystemVolume isys payload",
                    "authenticated_iboot_handoff": False, "guest_root_authenticated": False}

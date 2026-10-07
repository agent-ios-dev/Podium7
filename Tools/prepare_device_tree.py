"""Prepare iBoot placeholder flags and CPU timer frequencies for kernel handoff.

Leaves non-clock properties and all devices intact. Frequencies must agree
with the selected QEMU counter, not an invented boot-complete marker.
"""
import struct
from analyze_firmware import device_tree


def prepare(data, counter_frequency):
    if not 1_000_000 <= counter_frequency <= 1_000_000_000:
        raise ValueError("invalid counter frequency")
    device_tree(data)  # Fully validate bounds/depth before rewriting.
    changes = []
    def node(cursor, parent):
        count, children = struct.unpack_from("<II", data, cursor)
        cursor += 8
        properties = []
        for _ in range(count):
            raw_name = data[cursor:cursor + 32]
            size = struct.unpack_from("<I", data, cursor + 32)[0] & 0x7fffffff
            cursor += 36
            properties.append((raw_name, data[cursor:cursor + size]))
            cursor += (size + 3) & ~3
        names = {name.split(b"\0")[0]: value for name, value in properties}
        path = parent + "/" + names.get(b"name", b"?").split(b"\0")[0].decode("ascii", errors="replace")
        if names.get(b"device_type", b"").rstrip(b"\0") == b"cpu" or parent.endswith("/cpus"):
            for clock in [b"timebase-frequency", b"fixed-frequency"]:
                value = struct.pack("<Q", counter_frequency)
                existing = next((i for i, (name, _) in enumerate(properties) if name.split(b"\0")[0] == clock), None)
                if existing is None:
                    properties.append((clock.ljust(32, b"\0"), value))
                else:
                    properties[existing] = (properties[existing][0], value)
                changes.append({"path": path, "property": clock.decode(), "frequency": counter_frequency})
        encoded = [struct.pack("<II", len(properties), children)]
        for name, value in properties:
            encoded += [name, struct.pack("<I", len(value)), value, bytes((-len(value)) & 3)]
        for _ in range(children):
            child, cursor = node(cursor, path)
            encoded.append(child)
        return b"".join(encoded), cursor
    prepared, end = node(0, "")
    if end != len(data) or not changes:
        raise ValueError("missing CPU nodes or trailing tree data")
    device_tree(prepared)
    return prepared, changes

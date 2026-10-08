"""Serialize official restore v1 trust cache for XNU boot memory-map handoff.
Format: xnu-8019.80.24 osfmk/arm/trustcache.c and osfmk/kern/trustcache.h.
Keep all supplied cdhashes and flags unchanged; never synthesize trust entries.
"""
import argparse
import hashlib
import json
import pathlib
import struct
from analyze_firmware import payload


def serialize(container):
    raw = payload(container, b"rtsc")
    if len(raw) < 24:
        raise ValueError("short restore trust cache header")
    version, uuid, count = struct.unpack_from("<I16sI", raw)
    if version != 1 or not count or count > 100000:
        raise ValueError("unsupported/empty restore trust cache")
    if len(raw) != 24 + count * 22:
        raise ValueError("restore trust cache entry count differs from payload size")
    hashes = [raw[24+i*22:44+i*22] for i in range(count)]
    if hashes != sorted(hashes):
        raise ValueError("restore trust cache hashes must be sorted")
    # Serialized region contains module count and offsets from region start.
    region = struct.pack("<II", 1, 8) + raw
    region += bytes((-len(region)) & 0x3fff)
    return region, {"version": version, "entries": count, "uuid": uuid.hex(),
                    "module_sha256": hashlib.sha256(raw).hexdigest(),
                    "region_bytes": len(region), "module_offset": 8,
                    "guest_registration_confirmed": False, "authenticated_iboot_handoff": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    args = parser.parse_args()
    data, report = serialize(args.input.read_bytes())
    args.output.write_bytes(data)
    print(json.dumps(report, indent=2))

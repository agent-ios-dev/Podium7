"""Bounded, read-only process metadata for the verified 19H422 kernel only."""
import struct

KERNEL_SHA256 = "115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814"
HASH_POINTER = 0xfffffff007137440
HASH_MASK = 0xfffffff007137448


def pointer(value):
    return 0xffffffe000000000 <= value < 0xfffffffffffffff8 and value % 8 == 0


def inspect(read):
    """read(address, size) returns bytes; never write or export raw memory."""
    def data(address, size):
        if not pointer(address) or not 1 <= size <= 512:
            raise ValueError("invalid bounded kernel metadata read")
        result = read(address, size)
        if len(result) != size:
            raise ValueError("incomplete kernel metadata read")
        return result
    def word(address):
        return struct.unpack("<Q", data(address, 8))[0]
    base, mask = word(HASH_POINTER), word(HASH_MASK)
    if not pointer(base) or mask > 8191 or mask & (mask + 1):
        raise ValueError("invalid process hash layout")
    seen, processes = set(), []
    heads = []
    for start in range(0, mask + 1, 64):
        count = min(64, mask + 1 - start)
        heads.extend(struct.unpack("<" + "Q" * count, data(base + start * 8, count * 8)))
    for head in heads:
        current = head
        chain = set()
        while current:
            if not pointer(current) or current in chain:
                raise ValueError("invalid or cyclic process hash chain")
            if current in seen:
                raise ValueError("process occurs in multiple hash buckets")
            if len(seen) >= 512:
                raise ValueError("process metadata limit exceeded")
            chain.add(current); seen.add(current)
            pid = struct.unpack("<I", data(current + 0x68, 4))[0]
            name_bytes = data(current + 0x370, 32).split(b"\0", 1)[0]
            if pid > 1000000 or any(byte < 32 or byte > 126 for byte in name_bytes):
                raise ValueError("invalid process identity metadata")
            name = name_bytes.decode("ascii")
            processes.append({"pid": pid, "name": name})
            current = word(current + 0xa8)
    return {"source": "stopped original kernel process hash", "read_only": True,
            "processes": sorted(processes, key=lambda item: item["pid"]),
            "springboard_process_seen": any(item["name"] == "SpringBoard" for item in processes),
            "visible_springboard_confirmed": False}

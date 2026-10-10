"""Bounded, read-only process metadata for the verified 19H422 kernel only."""
import struct

KERNEL_SHA256 = "115489dd3e2adbe3e0d646413adb9397cfaf1c47f7b5d03620f78dd7d9371814"
HASH_POINTER = 0xfffffff007137440
HASH_MASK = 0xfffffff007137448


def pointer(value):
    return 0xffffffe000000000 <= value < 0xfffffffffffffff8 and value % 8 == 0


def inspect(read, *, thread_metadata=False, read_physical=None, service_labels=()):
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
    total_threads = 0
    def threads(proc):
        nonlocal total_threads
        task = word(proc + 0x10)
        # Original task_hold path 0xfffffff0071fb1b4/21c walks task +0x58,
        # following thread +0x3a8 until the task queue head sentinel.
        head = task + 0x58
        current = word(head)
        seen_threads, result = set(), []
        while current != head:
            if not pointer(current) or current in seen_threads:
                raise ValueError("invalid or cyclic task thread queue")
            if len(seen_threads) >= 128 or total_threads >= 1024:
                raise ValueError("thread metadata limit exceeded")
            seen_threads.add(current); total_threads += 1
            # _thread_tid 0xfffffff00720aa00; _thread_block_parameter's
            # shared path 0xfffffff0071ea608 saves continuation at +0xd0,
            # and tests scheduler state at +0x198. Do not read parameters,
            # user stacks, credentials, or arbitrary wait-event contents.
            tid = word(current + 0x458)
            continuation = word(current + 0xd0)
            state = struct.unpack("<I", data(current + 0x198, 4))[0]
            if tid > (1 << 48) or continuation and not (
                    0xffffffe000000000 <= continuation < 0xffffffffffffffff
                    and continuation % 4 == 0):
                raise ValueError("invalid thread identity or continuation")
            result.append({"tid": tid, "scheduler_state": state,
                           "kernel_continuation": hex(continuation)})
            current = word(current + 0x3a8)
        return result
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
            # Original _proc_ppid at 0xfffffff0075db0dc returns proc +0x28.
            ppid = struct.unpack("<I", data(current + 0x28, 4))[0]
            # Original _proc_ucred 0xfffffff0075dbca8 validates proc_ro's
            # back-reference then reads its credential pointer at +0x20.
            readonly = word(current + 0x20)
            if word(readonly) != current:
                raise ValueError("invalid process read-only back-reference")
            credential = word(readonly + 0x20)
            # Original _kauth_cred_getuid 0xfffffff0075abadc returns +0x18.
            uid = struct.unpack("<I", data(credential + 0x18, 4))[0]
            name_bytes = data(current + 0x370, 32).split(b"\0", 1)[0]
            if max(pid, ppid) > 1000000 or any(byte < 32 or byte > 126 for byte in name_bytes):
                raise ValueError("invalid process identity metadata")
            name = name_bytes.decode("ascii")
            process = {"pid": pid, "ppid": ppid, "uid": uid, "name": name}
            if name == 'xpcproxy' and read_physical is not None and service_labels:
                from guest_proxy_label import inspect as proxy_label
                try:
                    process['launch_service_label'] = proxy_label(
                        current, data, read_physical, service_labels)
                except (ValueError, KeyError) as error:
                    process['label_capture_error'] = str(error)
            if thread_metadata:
                try:
                    process["threads"] = threads(current)
                except (ValueError, KeyError) as error:
                    process["thread_capture_error"] = str(error)
            processes.append(process)
            current = word(current + 0xa8)
    return {"source": "stopped original kernel process hash", "read_only": True,
            "processes": sorted(processes, key=lambda item: item["pid"]),
            "springboard_process_seen": any(item["name"] == "SpringBoard" for item in processes),
            "backboardd_process_seen": any(item["name"] == "backboardd" for item in processes),
            "visible_springboard_confirmed": False}

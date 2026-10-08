"""Prepare iBoot placeholder flags and CPU timer frequencies for kernel handoff.

Leaves non-clock properties and all devices intact. Frequencies must agree
with the selected QEMU counter, not an invented boot-complete marker.
"""
import struct
import secrets
from analyze_firmware import device_tree


def prepare(data, counter_frequency, *, random_seed=None, dram_base=0x40000000, dram_size=2 * 1024 * 1024 * 1024, research_bridge_handoff=False):
    if not 1_000_000 <= counter_frequency <= 1_000_000_000:
        raise ValueError("invalid counter frequency")
    device_tree(data)  # Fully validate bounds/depth before rewriting.
    seed = secrets.token_bytes(64) if random_seed is None else random_seed
    if len(seed) != 64:
        raise ValueError("XNU requires 64 bootloader seed bytes")
    if dram_base < 0 or dram_size <= 0 or dram_base > 0xffffffffffffffff - dram_size:
        raise ValueError("invalid DRAM range")
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
        if path.endswith("/chosen"):
            name = b"random-seed"
            existing = next((i for i, (raw_name, _) in enumerate(properties) if raw_name.split(b"\0")[0] == name), None)
            if existing is None:
                properties.append((name.ljust(32, b"\0"), seed))
            else:
                properties[existing] = (properties[existing][0], seed)
            # Never put random seed material into diagnostics or the repository.
            changes.append({"path": path, "property": "random-seed", "bytes": 64, "source": "host CSPRNG"})
            for name, value in [(b"dram-base", dram_base), (b"dram-size", dram_size)]:
                encoded_value = struct.pack("<Q", value)
                existing = next((i for i, (raw_name, _) in enumerate(properties) if raw_name.split(b"\0")[0] == name), None)
                if existing is None:
                    properties.append((name.ljust(32, b"\0"), encoded_value))
                else:
                    properties[existing] = (properties[existing][0], encoded_value)
                changes.append({"path": path, "property": name.decode(), "value": hex(value), "source": "QEMU virt RAM"})
        if research_bridge_handoff and path == "/device-tree/arm-io":
            frequencies = names.get(b"clock-frequencies")
            if frequencies is not None and len(frequencies) == 384 and not any(frequencies):
                # AppleARMIO consumes matched arrays of UInt32 frequencies and
                # clock classes. Class 2 selects nclk. TCG clocks are fixed nominal
                # sources, not recovered physical A10 PLL programming.
                count = len(frequencies) // 4
                replacement = struct.pack("<I", counter_frequency) * count
                position = next(i for i, (key, _) in enumerate(properties)
                                if key.split(b"\0")[0] == b"clock-frequencies")
                properties[position] = (properties[position][0], replacement)
                key = b"clock-frequencies-nclk"
                if key not in names:
                    properties.append((key.ljust(32, b"\0"), struct.pack("<I", 2) * count))
                changes.append({"path": path, "property": "clock-frequencies",
                                "source": "synthetic fixed-frequency virtual clock sources",
                                "frequency": counter_frequency, "count": count,
                                "authentic_iboot_handoff": False})
        if research_bridge_handoff and path == "/device-tree/arm-io/pmgr":
            # Synthetic board metadata, not recovered iBoot register tuning.
            # The modeled bridges have no tuning parameters. Keep real settings
            # when present; declare an empty setting list only for absent ones.
            if names.get(b"compatible", b"").rstrip(b"\0") != b"pmgr1,t8010":
                raise ValueError("research bridge handoff requires T8010 PMGR")
            count = names.get(b"#bridges", b"")
            if count != struct.pack("<I", 14):
                raise ValueError("research bridge handoff requires 14 n112ap bridges")
            added = []
            for index in range(14):
                key = f"bridge-settings-{index}".encode()
                if key not in names:
                    properties.append((key.ljust(32, b"\0"), b""))
                    added.append(key.decode())
            # CPU performance table is an all-zero iBoot placeholder in 19H422.
            # Model one fixed nominal state for TCG, not physical CPU voltages.
            levels = names.get(b"voltage-states1")
            if levels is not None and len(levels) == 128 and not any(levels):
                value = struct.pack("<II", counter_frequency, 0) + bytes(120)
                position = next(i for i, (key, _) in enumerate(properties)
                                if key.split(b"\0")[0] == b"voltage-states1")
                properties[position] = (properties[position][0], value)
                changes.append({"path": path, "property": "voltage-states1",
                                "source": "synthetic fixed-frequency TCG performance domain",
                                "nominal_frequency": counter_frequency, "states": 1,
                                "authentic_iboot_handoff": False})
            changes.append({"path": path, "source": "synthetic research bridge model",
                            "properties": added, "bytes_per_property": 0,
                            "authentic_iboot_handoff": False})
        # Minimal one-plane MCC model, using A10 RoRgn offsets documented by
        # hardware research and the n112ap mcc physical aperture. This is not
        # a claim that all real A10 memory planes/cache hardware are modeled.
        handoff = {}
        if path.endswith("/chosen/lock-regs/amcc"):
            handoff = {"aperture-count": (1, 4), "aperture-size": (0x300000, 4),
                "plane-count": (1, 4), "plane-stride": (0, 4),
                "aperture-phys-addr": (0x200000000, 8), "cache-status-reg-offset": (0, 4),
                "cache-status-reg-mask": (1, 4), "cache-status-reg-value": (0, 4)}
        elif path.endswith("/chosen/lock-regs/amcc/amcc-ctrr-a"):
            handoff = {"page-size-shift": (14, 4), "lower-limit-reg-offset": (0x7e4, 4),
                "lower-limit-reg-mask": (0xffffffff, 4), "upper-limit-reg-offset": (0x7e8, 4),
                "upper-limit-reg-mask": (0xffffffff, 4), "lock-reg-offset": (0x7ec, 4),
                "lock-reg-mask": (1, 4), "lock-reg-value": (1, 4)}
        for name, (value, width) in handoff.items():
            raw_name = name.encode()
            encoded_value = value.to_bytes(width, "little")
            existing = next((i for i, (key, _) in enumerate(properties) if key.split(b"\0")[0] == raw_name), None)
            if existing is None:
                properties.append((raw_name.ljust(32, b"\0"), encoded_value))
            else:
                properties[existing] = (properties[existing][0], encoded_value)
        if handoff:
            changes.append({"path": path, "source": "minimal one-plane research MCC model", "properties": list(handoff)})
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
    if research_bridge_handoff and not any(c.get("source") == "synthetic research bridge model" for c in changes):
        raise ValueError("missing T8010 PMGR node for research bridge handoff")
    device_tree(prepared)
    return prepared, changes

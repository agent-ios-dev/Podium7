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
        if research_bridge_handoff and path == "/device-tree/chosen":
            # iBoot normally provides these. Keep real handoff bytes untouched.
            # A proxy initializes IODTNVRAM; a persistent controller is separate.
            missing = b"nvram-bank-size" not in names and b"nvram-proxy-data" not in names
            placeholder = (names.get(b"nvram-bank-size") == bytes(4)
                           and names.get(b"nvram-proxy-data") == bytes(8192))
            if missing or placeholder:
                from nvram_handoff import empty_bank
                bank = empty_bank()
                for key, value in [(b"nvram-bank-size", struct.pack("<I", len(bank))),
                                   (b"nvram-proxy-data", bank)]:
                    existing = next((i for i, (raw, _) in enumerate(properties)
                                     if raw.split(b"\0")[0] == key), None)
                    if existing is None:
                        properties.append((key.ljust(32, b"\0"), value))
                    else:
                        properties[existing] = (properties[existing][0], value)
                changes.append({"path": path, "source": "synthetic volatile CHRP v1 NVRAM proxy",
                                "bytes": len(bank), "persistent_controller": False,
                                "replaced_zero_iboot_placeholder": placeholder,
                                "authentic_iboot_handoff": False})
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
            # Model E/P nominal states for TCG, not physical CPU voltages.
            levels = names.get(b"voltage-states1")
            if levels is not None and len(levels) == 128 and not any(levels):
                requested = names.get(b"mcx-fast-cpu-frequency")
                if requested is None or len(requested) != 4:
                    raise ValueError("synthetic CPU domain requires mcx-fast-cpu-frequency")
                frequency_mhz = int.from_bytes(requested, "little")
                if not 1 <= frequency_mhz <= 10000:
                    raise ValueError("invalid nominal CPU frequency")
                # Type-1 PMGR domains encode a period, not Hz. Original XNU
                # computes MHz as (1000 << 16) / period at 0x0066e0008.
                period = (1000 << 16) // frequency_mhz
                if (1000 << 16) // period != frequency_mhz:
                    raise ValueError("nominal CPU frequency is not exactly representable")
                ecore = names.get(b"ecore-static-vvfc", b"")
                pcore = names.get(b"pcore-static-vvfc", b"")
                if not ecore or len(ecore) % 8 or not pcore or len(pcore) % 8:
                    raise ValueError("synthetic CPU domain requires E/P static VFC tables")
                efficiency = [record[0] >> 16 for record in struct.iter_unpack("<II", ecore)]
                performance = [record[0] >> 16 for record in struct.iter_unpack("<II", pcore)]
                frequencies = [efficiency[0], efficiency[-1], performance[0], frequency_mhz]
                if not (0 < frequencies[0] < frequencies[1] and
                        0 < frequencies[2] < frequencies[1] and frequencies[2] < frequencies[3]):
                    raise ValueError("virtual CPU groups must expose the XNU E/P frequency drop")
                periods = [(1000 << 16) // frequency for frequency in frequencies]
                if any((1000 << 16) // encoded != frequency for encoded, frequency in zip(periods, frequencies)):
                    raise ValueError("CPU frequency is not exactly representable")
                # Generic PMGR detects the first decreasing frequency as P-core
                # boundary, at 0x0066e0018. Nominal voltage is virtual metadata,
                # not a physical rail: nonzero permits its V^2 power calculation.
                value = b"".join(struct.pack("<II", encoded, 900) for encoded in periods) + bytes(96)
                position = next(i for i, (key, _) in enumerate(properties)
                                if key.split(b"\0")[0] == b"voltage-states1")
                properties[position] = (properties[position][0], value)
                changes.append({"path": path, "property": "voltage-states1",
                                "source": "synthetic E/P nominal TCG performance domain",
                                "nominal_frequency_mhz": frequency_mhz, "encoded_period": period, "states": 4,
                                "frequencies_mhz": frequencies, "pcore_boundary": 2,
                                "nominal_virtual_voltage": 900,
                                "efficiency_frequency_mhz": efficiency[0],
                                "efficiency_encoded_period": periods[0],
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

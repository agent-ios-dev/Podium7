"""Prepare iBoot placeholder flags and CPU timer frequencies for kernel handoff.

Default preparation preserves devices; optional FastSim identity is diagnostic only. Frequencies must agree
with the selected QEMU counter, not an invented boot-complete marker.
"""
import struct
import secrets
from analyze_firmware import device_tree


def prepare(data, counter_frequency, *, random_seed=None, dram_base=0x40000000, dram_size=2 * 1024 * 1024 * 1024, research_bridge_handoff=False, research_internal_storage=False, research_fastsim=False, research_no_sep=False, research_keybag_diagnostics=False):
    if not 1_000_000 <= counter_frequency <= 1_000_000_000:
        raise ValueError("invalid counter frequency")
    if research_no_sep and not research_fastsim:
        raise ValueError('no-SEP diagnostic requires explicit FastSim identity')
    if research_keybag_diagnostics and not research_no_sep:
        raise ValueError('keybag diagnostic requires explicit no-SEP experiment')
    original_nodes = device_tree(data)  # Validate bounds/depth before rewriting.
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
        if research_fastsim and path == '/device-tree/product':
            arm_io = next((n for n in original_nodes if n['path'] == '/device-tree/arm-io'), None)
            if arm_io is None or arm_io['properties'].get('compatible') != b'arm-io,t8010\0'.hex():
                raise ValueError('FastSim diagnostic requires original T8010 tree')
            key = b'product-name'
            properties = [(raw, value) for raw, value in properties if raw.split(b'\0')[0] != key]
            properties.append((key.ljust(32, b'\0'), b'FastSim\0'))
            changes.append({'path': path, 'property': 'product-name', 'value': 'FastSim',
                            'source': 'explicit no-SEP FastSim research diagnostic',
                            'sep_data_protection_confirmed': False, 'authentic_iboot_handoff': False})
            if research_keybag_diagnostics:
                key = b'boot-ios-diagnostics'
                if key in names and names[key] not in (bytes(4), struct.pack('<I', 1)):
                    raise ValueError('unexpected original diagnostic handoff value')
                properties = [(raw, value) for raw, value in properties if raw.split(b'\0')[0] != key]
                properties.append((key.ljust(32, b'\0'), struct.pack('<I', 1)))
                changes.append({'path': path, 'property': 'boot-ios-diagnostics', 'value': 1,
                                'source': 'explicit keybag diagnostic DeviceTree handoff experiment',
                                'sep_data_protection_confirmed': False, 'authentic_iboot_handoff': False})
        if research_internal_storage and path == '/device-tree/arm-io/apcie/pci-bridge0/s3e':
            arm_io = next((n for n in original_nodes if n['path'] == '/device-tree/arm-io'), None)
            if arm_io is None or arm_io['properties'].get('compatible') != b'arm-io,t8010\0'.hex():
                raise ValueError('internal research storage requires original T8010 endpoint')
            if b'built-in' not in names:
                properties.append((b'built-in'.ljust(32, b'\0'), b''))
            changes.append({'path': path, 'property': 'built-in',
                            'source': 'fixed internal research NVMe system disk',
                            'authentic_iboot_handoff': False})
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
            if research_keybag_diagnostics and not names.get(b'osenvironment', b'').rstrip(b'\0'):
                # Original 19H422 sysctl_load_devicetree_entries reads this
                # independently of product/boot-ios-diagnostics. Without it,
                # hw.osenvironment has no value. SpringBoard's original launch
                # plist consults that sysctl through LimitLoadFromHardware.
                key = b'osenvironment'
                properties = [(raw, value) for raw, value in properties if raw.split(b'\0')[0] != key]
                properties.append((key.ljust(32, b'\0'), b'normal\0'))
                changes.append({'path': path, 'property': 'osenvironment', 'value': 'normal',
                                'source': 'explicit normal userspace handoff in no-SEP diagnostic',
                                'authentic_iboot_handoff': False,
                                'springboard_confirmed': False})
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
            # SEPROMPanicBuffer requires a nonzero SoC type, not an ECID.
            # Populate only the exact iBoot placeholder on a verified T8010.
            if names.get(b"chip-id") == bytes(4):
                arm_io = next((n for n in original_nodes if
                               n["path"] == "/device-tree/arm-io"), None)
                if arm_io is None or arm_io["properties"].get("compatible") != b"arm-io,t8010\0".hex():
                    raise ValueError("zero chip-id handoff requires original T8010 arm-io")
                position = next(i for i, (raw, _) in enumerate(properties)
                                if raw.split(b"\0")[0] == b"chip-id")
                properties[position] = (properties[position][0], struct.pack("<I", 0x8010))
                changes.append({"path": path, "property": "chip-id", "value": "0x8010",
                                "source": "SoC type from original arm-io,t8010 compatibility",
                                "authentic_iboot_handoff": False})
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
        if research_bridge_handoff and path == "/device-tree/arm-io/apcie":
            if names.get(b"compatible", b"").rstrip(b"\0") != b"apcie,t8010":
                raise ValueError("research PCIe handoff requires T8010 APCIE")
            # A virtual PHY has no analog tuning words. Declare an empty table
            # rather than silently dropping Apple's required OSData property.
            # Preserve genuine iBoot tuning when it was supplied.
            if b"apcie-phy-tunables" not in names:
                properties.append((b"apcie-phy-tunables".ljust(32, b"\0"), b""))
                changes.append({"path": path, "property": "apcie-phy-tunables",
                                "source": "empty tuning list for research virtual PHY",
                                "bytes": 0, "authentic_iboot_handoff": False})
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
                # Keep the intermediate native VFC frequencies. The original
                # T8010 UVLO selector needs a P state above 756 and <=1355 MHz;
                # endpoints alone leave its search at nonexistent state 14.
                frequencies = efficiency + performance
                if (len(efficiency) != 3 or len(performance) != 4 or
                        any(a >= b for group in (efficiency, performance) for a, b in zip(group, group[1:])) or
                        efficiency[0] <= 0 or performance[0] <= 0 or
                        performance[0] >= efficiency[-1] or performance[-1] != frequency_mhz):
                    raise ValueError("virtual CPU groups must expose the XNU E/P frequency drop")
                if not any(756 < frequency <= 1355 for frequency in performance):
                    raise ValueError('virtual CPU domain lacks a valid UVLO intermediate P state')
                periods = [(1000 << 16) // frequency for frequency in frequencies]
                if any((1000 << 16) // encoded != frequency for encoded, frequency in zip(periods, frequencies)):
                    raise ValueError("CPU frequency is not exactly representable")
                # Generic PMGR detects the first decreasing frequency as P-core
                # boundary, at 0x0066e0018. Nominal voltage is virtual metadata,
                # not a physical rail: nonzero permits its V^2 power calculation.
                value = b"".join(struct.pack("<II", encoded, 900) for encoded in periods)
                value += bytes(128 - len(value))
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
        if research_no_sep and path == '/device-tree/arm-io/sep':
            if names.get(b'compatible') != b'iop,t8010\0iop,s8000\0':
                raise ValueError('no-SEP diagnostic requires original T8010 SEP node')
            changes.append({'path': path, 'property': 'node', 'action': 'omit',
                            'source': 'explicit research platform without implemented SEP',
                            'sep_data_protection_confirmed': False})
            for _ in range(children):
                _, cursor = node(cursor, path)
            return b'', cursor
        encoded = [struct.pack("<II", len(properties), children)]
        for name, value in properties:
            encoded += [name, struct.pack("<I", len(value)), value, bytes((-len(value)) & 3)]
        for _ in range(children):
            child, cursor = node(cursor, path)
            if child:
                encoded.append(child)
            else:
                children -= 1
        encoded[0] = struct.pack("<II", len(properties), children)
        return b"".join(encoded), cursor
    prepared, end = node(0, "")
    if end != len(data) or not changes:
        raise ValueError("missing CPU nodes or trailing tree data")
    if research_bridge_handoff and not any(c.get("source") == "synthetic research bridge model" for c in changes):
        raise ValueError("missing T8010 PMGR node for research bridge handoff")
    device_tree(prepared)
    if research_internal_storage and not any(c.get('property') == 'built-in' for c in changes):
        raise ValueError('original internal storage endpoint missing')
    if research_fastsim and not any(c.get('value') == 'FastSim' for c in changes):
        raise ValueError('original product node missing for FastSim diagnostic')
    if research_no_sep and not any(c.get('action') == 'omit' for c in changes):
        raise ValueError('original SEP node missing for no-SEP diagnostic')
    return prepared, changes

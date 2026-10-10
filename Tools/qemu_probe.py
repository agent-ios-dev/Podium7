"""Bounded XNU bootstrap experiment on QEMU virt, NOT an iPod board.

Uses a synthetic physical RAM map; leaves the Apple kernel unpatched. Captures
unsupported system-register/device accesses instead of treating them as success.
boot_args layout: Apple's xnu-8019.80.24 pexpert/pexpert/arm64/boot.h.
"""
import argparse
import json
import pathlib
import re
import struct
import subprocess
import time
import tempfile
from qmp_diagnostics import capture as capture_cpu
from boot_milestones import inspect as inspect_boot_milestones
from analyze_firmware import macho, device_tree
from prepare_device_tree import prepare
from ramdisk_handoff import attach_ramdisk, attach_memory_file, validate_hfs
from guest_patches import skip_restore_secure_root
from trust_cache_handoff import serialize as serialize_trust_cache
COUNTER_FREQUENCY = 24_000_000
QEMU_RAM_BASE = 0x40000000
QEMU_RAM_SIZE = 2 * 1024 * 1024 * 1024

# Leave QEMU's own DTB/boot reservations intact at the start of virt RAM.
PHYSICAL_BASE = 0x44000000  # 64 MiB aligned synthetic harness map, not T8010.
RAM_SIZE = QEMU_RAM_SIZE - (PHYSICAL_BASE - QEMU_RAM_BASE)


def align(value):
    return (value + 0x3fff) & ~0x3fff


def virtual_base_for_kernel(minimum, maximum, physical_base=PHYSICAL_BASE):
    if not 0 <= minimum < maximum <= 0xffffffffffffffff or physical_base <= 0:
        raise ValueError("invalid kernel/RAM bounds")
    alignment = physical_base & -physical_base
    base = minimum & ~(alignment - 1)
    if maximum - base > alignment:
        raise ValueError("physical base alignment does not cover the kernel virtual span")
    return base


def boot_args(virtual_base, tree_address, tree_size, top, *, ramdisk=False):
    args = bytearray(736)
    struct.pack_into("<HH", args, 0, 2, 2)
    struct.pack_into("<4Q", args, 8, virtual_base, PHYSICAL_BASE, RAM_SIZE, top)
    struct.pack_into("<QI", args, 96, tree_address, tree_size)
    command = b"-v serial=3 debug=0x8 cpus=1" + (b" rd=md0" if ramdisk else b"")
    args[108:108 + len(command)] = command
    struct.pack_into("<Q", args, 728, RAM_SIZE)
    return bytes(args)


def elf_image(entry, segments):
    # Self-contained ELF64 ARM64 executable accepted by QEMU generic loader.
    cursor = 64 + len(segments) * 56
    headers, bodies = [], []
    for address, memory_size, data in segments:
        if len(data) > memory_size:
            raise ValueError("ELF payload exceeds segment")
        headers.append(struct.pack("<II6Q", 1, 7, cursor, address, address, len(data), memory_size, 1))
        bodies.append(data)
        cursor += len(data)
    identity = b"\x7fELF\x02\x01\x01" + bytes(9)
    header = identity + struct.pack("<HHI3QI6H", 2, 183, 1, entry, 64, 0, 0, 64, 56, len(segments), 0, 0, 0)
    return header + b"".join(headers) + b"".join(bodies)


def make_probe(directory, *, research_bridge_handoff=False, ramdisk=None, research_ramdisk_root=False, trust_cache=None, research_cfi_nvram=False, research_aes_root_fallback=False):
    if research_aes_root_fallback and not research_ramdisk_root:
        raise ValueError("AES fallback requires the explicit research restore root gate skip")
    if research_ramdisk_root and ramdisk is None:
        raise ValueError("research root gate skip is restricted to explicit restore ramdisk probes")
    kernel = (directory / "KernelCache.macho").read_bytes()
    original_tree = (directory / "DeviceTree.bin").read_bytes()
    tree, clocks = prepare(original_tree, COUNTER_FREQUENCY, dram_base=QEMU_RAM_BASE, dram_size=QEMU_RAM_SIZE,
                           research_bridge_handoff=research_bridge_handoff)
    if research_cfi_nvram:
        if not research_bridge_handoff:
            raise ValueError("CFI NVRAM requires synthetic research handoff")
        from cfi_nvram_handoff import attach, flash_image, select_bank, BASE, SIZE
        flash = directory / "nvram-flash.raw"
        if not flash.exists():
            flash.write_bytes(flash_image())
        elif flash.stat().st_size != SIZE:
            raise ValueError("invalid CFI NVRAM backing image size")
        backing = flash.read_bytes()
        bank_index, generation, _ = select_bank(backing)
        tree = attach(tree, backing)
        (directory / "nvram-handoff.json").write_text(json.dumps({
            "provider": "synthetic AMD CFI NOR", "physical_base": hex(BASE),
            "bytes": SIZE, "banks": 2, "bank_bytes": 8192,
            "selected_bank": bank_index, "selected_generation": generation,
            "original_nvme_hardware": False, "kernel_driver": "AppleARMCHRPNVRAM",
            "persistent_backing_file": str(flash)}, indent=2))
    info = macho(kernel)
    if research_ramdisk_root:
        kernel, patch_report = skip_restore_secure_root(kernel, info["segments"], aes_root_fallback=research_aes_root_fallback)
        (directory / "guest-patches.json").write_text(json.dumps([patch_report], indent=2))
    else:
        (directory / "guest-patches.json").write_text("[]")
    regions = [x for x in info["segments"] if x["length"]]
    minimum = min(int(x["address"], 16) for x in regions)
    maximum = max(int(x["address"], 16) + x["length"] for x in regions)
    virtual_base = virtual_base_for_kernel(minimum, maximum)
    if maximum - virtual_base > RAM_SIZE // 2:
        raise ValueError("kernel layout exceeds harness budget")
    entry = int(info["entry"], 16) - virtual_base + PHYSICAL_BASE
    stub_address = align(maximum - virtual_base + PHYSICAL_BASE)
    args_address = stub_address + 0x4000
    tree_address = args_address + 0x4000
    cache_region = None
    cache_address = None
    if trust_cache is not None:
        cache_region, cache_report = serialize_trust_cache(trust_cache.read_bytes())
        cache_address = align(minimum - virtual_base + PHYSICAL_BASE) - len(cache_region)
        if cache_address < PHYSICAL_BASE:
            raise ValueError("trust cache does not fit below kernel in harness RAM")
        tree = attach_memory_file(tree, cache_address, len(cache_region), "TrustCache")
        cache_report.update(physical_address=hex(cache_address),
                            placement="immediately below lowest kernel segment")
        (directory / "trust-cache-handoff.json").write_text(json.dumps(cache_report, indent=2))
        clocks.append({"path": "/device-tree/chosen/memory-map", "property": "TrustCache",
                       "physical_address": hex(cache_address), "bytes": len(cache_region),
                       "source": "official IPSW restore trust cache", "entries": cache_report["entries"]})
    disk = ramdisk.read_bytes() if ramdisk is not None else None
    if disk is not None:
        disk_info = validate_hfs(disk)
        disk += bytes((-len(disk)) & 4095)
        disk_info["reserved_bytes"] = len(disk)
        sized_tree = attach_ramdisk(tree, 0, len(disk))
        disk_address = align(tree_address + len(sized_tree))
        top = align(disk_address + len(disk))
        if top > PHYSICAL_BASE + RAM_SIZE:
            raise ValueError("ramdisk exceeds harness RAM")
        tree = attach_ramdisk(tree, disk_address, len(disk))
        disk_info.update(physical_address=hex(disk_address), reserved_top=hex(top),
                         root_device="md0", guest_mount_confirmed=False)
        (directory / "ramdisk-handoff.json").write_text(json.dumps(disk_info, indent=2))
        (directory / "PreparedDeviceTree.bin").write_bytes(tree)
    else:
        top = align(tree_address + len(tree))
    if disk is not None:
        clocks.append({"path": "/device-tree/chosen/memory-map", "property": "RAMDisk",
                       "physical_address": hex(disk_address), "bytes": len(disk),
                       "source": "official IPSW restore ramdisk, reserved in harness RAM"})
    (directory / "device-tree-preparation.json").write_text(json.dumps({
        "bootloader_placeholder_flags_cleared": True, "original_bytes": len(original_tree),
        "prepared_bytes": len(tree), "device_tree_changes": clocks}, indent=2))
    (directory / "PreparedDeviceTree.bin").write_bytes(tree)
    stub = [0xd2800000 | ((args_address & 0xffff) << 5),
            0xf2a00000 | (((args_address >> 16) & 0xffff) << 5),
            0xd2800001 | ((entry & 0xffff) << 5),
            0xf2a00001 | (((entry >> 16) & 0xffff) << 5),
            0xd61f0020]  # mov x0, boot_args; mov x1, entry; br x1
    segments = [(int(x["address"], 16) - virtual_base + PHYSICAL_BASE, x["length"],
                 kernel[x["offset"]:x["offset"] + x["file_size"]]) for x in regions]
    segments += [(stub_address, 0x4000, b"".join(struct.pack("<I", x) for x in stub)),
                 (args_address, 0x4000, boot_args(virtual_base, virtual_base + tree_address - PHYSICAL_BASE, len(tree), top, ramdisk=disk is not None)),
                 (tree_address, align(len(tree)), tree)]
    if disk is not None:
        segments.append((disk_address, align(len(disk)), disk))
    if cache_region is not None:
        segments.append((cache_address, len(cache_region), cache_region))
    destination = directory / "qemu-kernel-probe.elf"
    destination.write_bytes(elf_image(stub_address, segments))
    readonly_low = min(int(x["address"], 16) for x in regions if x["name"] == "__PRELINK_TEXT") - virtual_base + PHYSICAL_BASE
    if cache_address is not None:
        readonly_low = min(readonly_low, cache_address)
    last = next(x for x in regions if x["name"] == "__LAST")
    readonly_high = int(last["address"], 16) + last["length"] - virtual_base + PHYSICAL_BASE - 1
    return destination, entry, ((readonly_low - QEMU_RAM_BASE) >> 14, (readonly_high - QEMU_RAM_BASE) >> 14)


def panic_capture_complete(serial_bytes):
    """Wait for the first panic's saved PC/ESR/FAR, not just its header."""
    header = serial_bytes.find(b"panic(cpu ")
    if header < 0:
        return False
    line = serial_bytes[header:].split(b"\n", 1)
    # Driver REQUIRE/assertion panics end at @Source.cpp:line and do not emit
    # a primary saved state. Only data-abort panics need the PC/ESR/FAR line.
    if len(line) == 2 and re.search(rb"@[^\r\n]+:\d+\r?$", line[0]):
        return True
    return re.search(
        rb"pc:\s*0x[0-9a-fA-F]+\s+cpsr:\s*0x[0-9a-fA-F]+"
        rb"\s+esr:\s*0x[0-9a-fA-F]+\s+far:\s*0x[0-9a-fA-F]+[\r\n]",
        serial_bytes[header:]) is not None


def run_probe(directory, executable="qemu-system-aarch64", cpu="max", *, research_bridge_handoff=False, ramdisk=None, seconds=30, research_ramdisk_root=False, trust_cache=None, research_cfi_nvram=False, research_pmp_core=False, research_aes_root_fallback=False, research_nvme=False):
    if not 1 <= seconds <= 600:
        raise ValueError("execution budget must be between 1 and 600 seconds")
    if research_bridge_handoff and cpu != "podium7-research":
        raise ValueError("synthetic bridge handoff requires the research bridge model")
    if research_nvme and cpu != "podium7-research":
        raise ValueError("research NVMe requires the explicitly modeled PCIe backend")
    image, kernel_entry, rorgn = make_probe(directory, research_bridge_handoff=research_bridge_handoff, ramdisk=ramdisk, research_ramdisk_root=research_ramdisk_root, trust_cache=trust_cache, research_cfi_nvram=research_cfi_nvram, research_aes_root_fallback=research_aes_root_fallback)
    trace, serial = directory / "qemu-trace.txt", directory / "qemu-serial.txt"
    command = [executable, "-machine", "virt,secure=off,virtualization=off", "-cpu", f"{cpu},cntfrq={COUNTER_FREQUENCY}", "-accel", "tcg",
               "-m", "2048", "-smp", "1", "-display", "none", "-monitor", "none", "-serial", "stdio",
               "-device", f"loader,file={image},cpu-num=0", "-d", "in_asm,int,guest_errors,unimp", "-D", str(trace)]
    if research_pmp_core:
        if cpu != "podium7-research":
            raise ValueError("integrated PMP requires the research ARM64 backend")
        # Reserve a second TCG context for the non-AP coprocessor without
        # creating another ARM64 guest CPU or changing XNU's cpus=1 topology.
        command[command.index("-smp") + 1] = "1,maxcpus=2"
        from probe_pmp_core import extract
        marker = directory / "PMPFirmware.bin"
        marker.write_bytes(extract((directory / "KernelCache.macho").read_bytes()))
        command += ["-drive", f"if=none,id=podium7-pmp-integrated,format=raw,read-only=on,file={marker}"]
    if research_cfi_nvram:
        command += ["-drive", f"if=none,id=podium7-nvram,format=raw,cache=writeback,file={directory / 'nvram-flash.raw'}"]
    if research_nvme:
        disk_path = directory / "storage-16g.raw"
        if not disk_path.exists():
            with disk_path.open("xb") as storage:
                storage.truncate(16 << 30)
        if disk_path.stat().st_size != 16 << 30:
            raise ValueError("research storage must be exactly 16 GiB; existing disk preserved")
        command += ["-drive", f"if=none,id=podium7-storage,format=raw,file={disk_path}"]
        command += ["-trace", "enable=pci_nvme*"]
    if cpu == "podium7-research":
        command += ["-device", f"loader,addr=0x2000007e4,data={rorgn[0]},data-len=4",
                    "-device", f"loader,addr=0x2000007e8,data={rorgn[1]},data-len=4"]
    monitor_dir = tempfile.TemporaryDirectory(prefix="p7-qmp-")
    monitor_path = pathlib.Path(monitor_dir.name) / "monitor.sock"
    command += ["-qmp", f"unix:{monitor_path},server=on,wait=off"]
    snapshot = None
    version = subprocess.check_output([executable, "--version"], text=True).splitlines()[0]
    with serial.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        start = time.monotonic()
        stop = "QEMU exited"
        panic_started = None
        while process.poll() is None:
            deadline = time.monotonic() - start > seconds
            full_trace = trace.exists() and trace.stat().st_size > 16 * 1024 * 1024
            serial_bytes = serial.read_bytes()
            panic_seen = b"panic(cpu " in serial_bytes
            if panic_seen and panic_started is None:
                panic_started = time.monotonic()
            complete = panic_capture_complete(serial_bytes)
            panic_timeout = panic_started is not None and time.monotonic() - panic_started > 2
            if deadline or full_trace or complete or panic_timeout:
                stop = ("XNU panic captured" if complete else
                        "XNU panic capture incomplete" if panic_seen else
                        f"{seconds}-second execution deadline reached" if deadline else "16-MiB trace limit reached")
                try:
                    # Capture the actual panic FAR translation while the guest
                    # page tables still exist; register snapshots alone show VA.
                    panic_fars = re.findall(rb"\bfar:\s*(0x[0-9a-fA-F]+)", serial_bytes)
                    addresses = tuple(dict.fromkeys(int(value, 16) for value in panic_fars[-4:]))
                    # Only PMP control words: exclude FIFO data/pop and event-claim ports.
                    controls = ((0x20e300b84, 5), (0x20e300ba0, 2),
                                (0x20e304008, 1), (0x20e304020, 1)) if research_pmp_core else ()
                    snapshot = capture_cpu(monitor_path, addresses, physical_windows=controls)
                    (directory / "cpu-snapshot.txt").write_text(snapshot["registers"])
                    (directory / "cpu-stack.txt").write_text(snapshot["stack"])
                    (directory / "cpu-snapshot.json").write_text(json.dumps(snapshot, indent=2))
                except (OSError, ValueError) as error:
                    snapshot = {"capture_error": str(error)}
                    (directory / "cpu-snapshot.json").write_text(json.dumps(snapshot, indent=2))
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.1)
    monitor_dir.cleanup()
    trace_text = trace.read_text(errors="replace") if trace.exists() else ""
    entry_seen = any(int(address, 16) == kernel_entry for address in re.findall(r"^0x([0-9a-fA-F]+):", trace_text, re.MULTILINE))
    faults = [line for line in trace_text.splitlines() if "exception" in line.lower() or "unimplemented" in line.lower() or "unallocated" in line.lower() or "unsupported" in line.lower()]
    outside_harness_ram_mappings = [line for line in trace_text.splitlines()
                                    if "PODIUM7 KVA-OUTSIDE-HARNESS-RAM" in line]
    acc_arguments = [line for line in trace_text.splitlines() if "PODIUM7 ACC-ARG " in line or "PODIUM7 BOOT-ARG " in line]
    timer_fiq_transactions = [line for line in trace_text.splitlines() if "PODIUM7 TIMER-FIQ " in line]
    aic_transactions = [line for line in trace_text.splitlines() if "PODIUM7 AIC1 " in line]
    mcc_transactions = [line for line in trace_text.splitlines() if "PODIUM7 MCC " in line]
    wdt_transactions = [line for line in trace_text.splitlines() if "PODIUM7 WDT1 " in line]
    gpio_transactions = [line for line in trace_text.splitlines() if "PODIUM7 GPIO " in line]
    aes_transactions = [line for line in trace_text.splitlines() if "PODIUM7 AES " in line]
    thermal_transactions = [line for line in trace_text.splitlines() if "PODIUM7 THERMAL " in line]
    temperature_sensor_transactions = [line for line in trace_text.splitlines()
                                       if "PODIUM7 THERMAL base=000000020e0bc000 " in line]
    cpu_clpc_transactions = [line for line in trace_text.splitlines() if "PODIUM7 CPU-CLPC " in line]
    gfx_transactions = [line for line in trace_text.splitlines() if "PODIUM7 GFX " in line]
    mipi_transactions = [line for line in trace_text.splitlines() if "PODIUM7 MIPI-DSIM " in line]
    mca_transactions = [line for line in trace_text.splitlines() if "PODIUM7 MCA " in line]
    dwi_transactions = [line for line in trace_text.splitlines() if "PODIUM7 DWI " in line]
    usbphy_transactions = [line for line in trace_text.splitlines() if "PODIUM7 USBPHY " in line]
    i2s_switch_transactions = [line for line in trace_text.splitlines() if "PODIUM7 I2S-SWITCH " in line]
    pmgr_transactions = [line for line in trace_text.splitlines() if "PODIUM7 PMGR-BRIDGE " in line]
    pmgr_power_transactions = [line for line in trace_text.splitlines() if "PODIUM7 PMGR-POWER " in line]
    pmgr_raw_transactions = [line for line in trace_text.splitlines() if "PODIUM7 PMGR-RAW " in line]
    exception_tail = faults[-24:]
    from inspect_pmgr_handoff import inspect_tree
    handoff = inspect_tree((directory / "PreparedDeviceTree.bin").read_bytes())
    (directory / "pmgr-handoff.json").write_text(json.dumps(handoff, indent=2))
    summary = {"research_nvme": research_nvme, "research_storage_bytes": (16 << 30) if research_nvme else None, "research_aes_root_fallback": research_aes_root_fallback, "research_pmp_core": research_pmp_core, "research_cfi_nvram": research_cfi_nvram, "research_bridge_handoff": research_bridge_handoff,
               "authentic_iboot_handoff": False, "pmgr_handoff": handoff, "booted_ios": False, "kernel_entry_seen": entry_seen, "physical_kernel_entry": hex(kernel_entry),
               "boot_milestones": inspect_boot_milestones(serial.read_text(errors="replace"), trace_text),
               "last_translated_blocks": re.findall(r"^0x([0-9a-fA-F]+):", trace_text, re.MULTILINE)[-8:],
               "cpu_model": cpu, "aprr_permissions_enforced": False,
               "counter_frequency": COUNTER_FREQUENCY,
               "first_faults": faults[:12],
               "exception_tail": exception_tail,
               "interrupt_controller_diagnostics": [line for line in trace_text.splitlines() if "PODIUM7 IRQ-CONTROLLER " in line][:64],
               "outside_harness_ram_kernel_mappings": outside_harness_ram_mappings,
               "mcc_transactions": mcc_transactions[:128],
               "acc_argument_diagnostics": acc_arguments[:128],
               "timer_fiq_transactions": timer_fiq_transactions[:128],
               "aic_transactions": aic_transactions[:128],
               "watchdog_transactions": wdt_transactions[:128],
               "gpio_transactions": gpio_transactions[:128],
               "aes_transactions": aes_transactions[:128],
               "thermal_transactions": thermal_transactions[:128],
               "temperature_sensor_transactions": temperature_sensor_transactions[:128],
               "cpu_clpc_transactions": cpu_clpc_transactions[:128],
               "gfx_transactions": gfx_transactions[:128],
               "mipi_dsim_transactions": mipi_transactions[:128],
               "mca_transactions": mca_transactions[:128],
               "dwi_transactions": dwi_transactions[:128],
               "usbphy_transactions": usbphy_transactions[:128],
               "i2s_switch_transactions": i2s_switch_transactions[:128],
               "pmgr_bridge_transactions": pmgr_transactions[:128],
               "pmgr_power_transactions": pmgr_power_transactions[:128],
               "pmgr_raw_transactions": pmgr_raw_transactions[:128],
               "execution_budget_seconds": seconds, "cpu_snapshot": snapshot,
               "restore_trust_cache_supplied": trust_cache is not None,
               "research_ramdisk_root_gate_skip": research_ramdisk_root,
               "original_kernel_unpatched": not research_ramdisk_root,
               "restore_ramdisk_requested": ramdisk is not None,
               "backend": version, "board": "QEMU virt bootstrap experiment, not T8010",
               "physical_ram_base": hex(PHYSICAL_BASE), "command": command, "stop": stop,
               "returncode": process.returncode, "seconds": time.monotonic() - start,
               "console_tail": serial.read_text(errors="replace")[-4096:],
               "trace_bytes": trace.stat().st_size if trace.exists() else 0}
    if research_cfi_nvram:
        import hashlib
        import zlib
        flash_bytes = (directory / "nvram-flash.raw").read_bytes()
        banks = []
        for offset in (0, 8192):
            bank = flash_bytes[offset:offset + 8192]
            banks.append({"offset": offset, "generation": struct.unpack_from("<I", bank, 20)[0],
                          "adler_valid": struct.unpack_from("<I", bank, 16)[0] == zlib.adler32(bank[20:]),
                          "restore_outcome_variable_present": b"restore-outcome=" in bank})
        # No guest variable values or raw key material are exported.
        summary["nvram_backing_evidence"] = {"bytes": len(flash_bytes),
            "sha256": hashlib.sha256(flash_bytes).hexdigest(), "banks": banks}
    (directory / "qemu-probe.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if not trace.exists() or trace.stat().st_size == 0:
        raise RuntimeError("QEMU produced no guest execution trace")
    if not entry_seen:
        raise RuntimeError("trace does not show the genuine Apple kernel entry")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=pathlib.Path, default=pathlib.Path(".firmware"))
    parser.add_argument("--qemu", default="qemu-system-aarch64")
    parser.add_argument("--cpu", choices=["max", "podium7-research"], default="max")
    parser.add_argument("--research-bridge-handoff", action="store_true",
                        help="Synthetic empty tuning lists for modeled bridges; not authentic iBoot settings")
    parser.add_argument("--ramdisk", type=pathlib.Path, help="Raw HFS restore disk, reserved in harness RAM; root md0")
    parser.add_argument("--seconds", type=int, default=30, help="Bounded execution budget (1..600 seconds)")
    parser.add_argument("--research-ramdisk-root", action="store_true",
                        help="Opt-in exact-kernel SecureRootName gate skip; unauthenticated restore userland experiment")
    parser.add_argument("--trust-cache", type=pathlib.Path, help="Official RestoreTrustCache rtsc IM4P, loaded below kernel")
    parser.add_argument("--research-cfi-nvram", action="store_true", help="Synthetic AMD NOR provider; not original A10 NVMe hardware")
    parser.add_argument("--research-pmp-core", action="store_true", help="Opt-in generic ARM32 PMP core sharing original SRAM; not exact hardware")
    parser.add_argument("--research-aes-root-fallback", action="store_true", help="Exact-kernel diagnostic SecureRoot unsupported fallback; requires explicit restore root gate skip, no AES crypto bypass")
    parser.add_argument("--research-nvme", action="store_true", help="Separate real QEMU NVMe backend, fixed 16 GiB scratch disk; no Apple DART/MSI claim")
    args = parser.parse_args()
    run_probe(args.directory, executable=args.qemu, cpu=args.cpu,
              research_bridge_handoff=args.research_bridge_handoff, ramdisk=args.ramdisk, seconds=args.seconds, research_ramdisk_root=args.research_ramdisk_root, trust_cache=args.trust_cache, research_cfi_nvram=args.research_cfi_nvram, research_pmp_core=args.research_pmp_core, research_aes_root_fallback=args.research_aes_root_fallback, research_nvme=args.research_nvme)

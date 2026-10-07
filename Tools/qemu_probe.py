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
from analyze_firmware import macho, device_tree
from prepare_device_tree import prepare
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


def boot_args(virtual_base, tree_address, tree_size, top):
    args = bytearray(736)
    struct.pack_into("<HH", args, 0, 2, 2)
    struct.pack_into("<4Q", args, 8, virtual_base, PHYSICAL_BASE, RAM_SIZE, top)
    struct.pack_into("<QI", args, 96, tree_address, tree_size)
    command = b"-v serial=3 debug=0x8"
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


def make_probe(directory):
    kernel = (directory / "KernelCache.macho").read_bytes()
    original_tree = (directory / "DeviceTree.bin").read_bytes()
    tree, clocks = prepare(original_tree, COUNTER_FREQUENCY, dram_base=QEMU_RAM_BASE, dram_size=QEMU_RAM_SIZE)
    (directory / "device-tree-preparation.json").write_text(json.dumps({
        "bootloader_placeholder_flags_cleared": True, "original_bytes": len(original_tree),
        "prepared_bytes": len(tree), "cpu_clocks": clocks}, indent=2))
    info = macho(kernel)
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
    top = align(tree_address + len(tree))
    stub = [0xd2800000 | ((args_address & 0xffff) << 5),
            0xf2a00000 | (((args_address >> 16) & 0xffff) << 5),
            0xd2800001 | ((entry & 0xffff) << 5),
            0xf2a00001 | (((entry >> 16) & 0xffff) << 5),
            0xd61f0020]  # mov x0, boot_args; mov x1, entry; br x1
    segments = [(int(x["address"], 16) - virtual_base + PHYSICAL_BASE, x["length"],
                 kernel[x["offset"]:x["offset"] + x["file_size"]]) for x in regions]
    segments += [(stub_address, 0x4000, b"".join(struct.pack("<I", x) for x in stub)),
                 (args_address, 0x4000, boot_args(virtual_base, virtual_base + tree_address - PHYSICAL_BASE, len(tree), top)),
                 (tree_address, align(len(tree)), tree)]
    destination = directory / "qemu-kernel-probe.elf"
    destination.write_bytes(elf_image(stub_address, segments))
    readonly_low = min(int(x["address"], 16) for x in regions if x["name"] == "__PRELINK_TEXT") - virtual_base + PHYSICAL_BASE
    last = next(x for x in regions if x["name"] == "__LAST")
    readonly_high = int(last["address"], 16) + last["length"] - virtual_base + PHYSICAL_BASE - 1
    return destination, entry, ((readonly_low - QEMU_RAM_BASE) >> 14, (readonly_high - QEMU_RAM_BASE) >> 14)


def run_probe(directory, executable="qemu-system-aarch64", cpu="max"):
    image, kernel_entry, rorgn = make_probe(directory)
    trace, serial = directory / "qemu-trace.txt", directory / "qemu-serial.txt"
    command = [executable, "-machine", "virt,secure=off,virtualization=off", "-cpu", f"{cpu},cntfrq={COUNTER_FREQUENCY}", "-accel", "tcg",
               "-m", "2048", "-smp", "1", "-display", "none", "-monitor", "none", "-serial", "stdio",
               "-device", f"loader,file={image},cpu-num=0", "-d", "in_asm,int,guest_errors,unimp", "-D", str(trace)]
    if cpu == "podium7-research":
        command += ["-device", f"loader,addr=0x2000007e4,data={rorgn[0]},data-len=4",
                    "-device", f"loader,addr=0x2000007e8,data={rorgn[1]},data-len=4"]
    version = subprocess.check_output([executable, "--version"], text=True).splitlines()[0]
    with serial.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        start = time.monotonic()
        stop = "QEMU exited"
        while process.poll() is None:
            deadline = time.monotonic() - start > 30
            full_trace = trace.exists() and trace.stat().st_size > 16 * 1024 * 1024
            if deadline or full_trace:
                stop = "30-second execution deadline reached" if deadline else "16-MiB trace limit reached"
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.1)
    trace_text = trace.read_text(errors="replace") if trace.exists() else ""
    entry_seen = any(int(address, 16) == kernel_entry for address in re.findall(r"^0x([0-9a-fA-F]+):", trace_text, re.MULTILINE))
    faults = [line for line in trace_text.splitlines() if "exception" in line.lower() or "unimplemented" in line.lower() or "unallocated" in line.lower() or "unsupported" in line.lower()]
    exception_tail = faults[-24:]
    summary = {"booted_ios": False, "kernel_entry_seen": entry_seen, "physical_kernel_entry": hex(kernel_entry),
               "last_translated_blocks": re.findall(r"^0x([0-9a-fA-F]+):", trace_text, re.MULTILINE)[-8:],
               "cpu_model": cpu, "aprr_permissions_enforced": False,
               "counter_frequency": COUNTER_FREQUENCY,
               "first_faults": faults[:12],
               "exception_tail": exception_tail, "backend": version, "board": "QEMU virt bootstrap experiment, not T8010",
               "physical_ram_base": hex(PHYSICAL_BASE), "command": command, "stop": stop,
               "returncode": process.returncode, "seconds": time.monotonic() - start,
               "console_tail": serial.read_text(errors="replace")[-4096:],
               "trace_bytes": trace.stat().st_size if trace.exists() else 0}
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
    args = parser.parse_args()
    run_probe(args.directory, executable=args.qemu, cpu=args.cpu)

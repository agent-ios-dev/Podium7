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
from analyze_firmware import macho

PHYSICAL_BASE = 0x40000000  # QEMU virt RAM, deliberately not claimed as T8010.
RAM_SIZE = 2 * 1024 * 1024 * 1024


def align(value):
    return (value + 0x3fff) & ~0x3fff


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
    tree = (directory / "DeviceTree.bin").read_bytes()
    info = macho(kernel)
    regions = [x for x in info["segments"] if x["length"]]
    minimum = min(int(x["address"], 16) for x in regions)
    maximum = max(int(x["address"], 16) + x["length"] for x in regions)
    if maximum - minimum > RAM_SIZE // 2:
        raise ValueError("kernel layout exceeds harness budget")
    entry = int(info["entry"], 16) - minimum + PHYSICAL_BASE
    stub_address = align(maximum - minimum + PHYSICAL_BASE)
    args_address = stub_address + 0x4000
    tree_address = args_address + 0x4000
    top = align(tree_address + len(tree))
    stub = [0xd2800000 | ((args_address & 0xffff) << 5),
            0xf2a00000 | (((args_address >> 16) & 0xffff) << 5),
            0xd2800001 | ((entry & 0xffff) << 5),
            0xf2a00001 | (((entry >> 16) & 0xffff) << 5),
            0xd61f0020]  # mov x0, boot_args; mov x1, entry; br x1
    segments = [(int(x["address"], 16) - minimum + PHYSICAL_BASE, x["length"],
                 kernel[x["offset"]:x["offset"] + x["file_size"]]) for x in regions]
    segments += [(stub_address, 0x4000, b"".join(struct.pack("<I", x) for x in stub)),
                 (args_address, 0x4000, boot_args(minimum, minimum + tree_address - PHYSICAL_BASE, len(tree), top)),
                 (tree_address, align(len(tree)), tree)]
    destination = directory / "qemu-kernel-probe.elf"
    destination.write_bytes(elf_image(stub_address, segments))
    return destination, entry


def run_probe(directory, executable="qemu-system-aarch64"):
    image, kernel_entry = make_probe(directory)
    trace, serial = directory / "qemu-trace.txt", directory / "qemu-serial.txt"
    command = [executable, "-machine", "virt,secure=off,virtualization=off", "-cpu", "max", "-accel", "tcg",
               "-m", "2048", "-smp", "1", "-display", "none", "-monitor", "none", "-serial", "stdio",
               "-device", f"loader,file={image},cpu-num=0", "-d", "in_asm,int,guest_errors,unimp", "-D", str(trace)]
    version = subprocess.check_output([executable, "--version"], text=True).splitlines()[0]
    with serial.open("wb") as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)
        start = time.monotonic()
        stop = "QEMU exited"
        while process.poll() is None:
            if time.monotonic() - start > 10 or trace.exists() and trace.stat().st_size > 16 * 1024 * 1024:
                stop = "bounded trace limit reached"
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
    exception_tail = [line for line in trace_text.splitlines() if "exception" in line.lower() or "unimplemented" in line.lower() or "unallocated" in line.lower()][-24:]
    summary = {"booted_ios": False, "kernel_entry_seen": entry_seen, "physical_kernel_entry": hex(kernel_entry),
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
    args = parser.parse_args()
    run_probe(args.directory)

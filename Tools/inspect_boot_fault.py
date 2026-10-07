"""Disassemble the first actual exception PC from the captured QEMU trace."""
import pathlib
import re
import subprocess
import sys
import json
from analyze_firmware import macho

root = pathlib.Path(".firmware")
if not (root / "qemu-trace.txt").exists():
    print("No execution trace: backend did not start; inspect the earlier build step")
    sys.exit(0)
trace = (root / "qemu-trace.txt").read_text(errors="replace")
serial_path = root / "qemu-serial.txt"
serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""

# QEMU can report many recoverable exceptions before XNU prints a panic. Keep
# the first-exception report above, but also disassemble the actual panic PC and
# record the saved FAR/ESR/registers so later runs identify the fatal access.
panic = re.search(r"panic\(cpu\s+(\d+).*?\):\s*(.*?)\s+at pc\s+(0x[0-9a-fA-F]+),\s*lr\s+(0x[0-9a-fA-F]+).*?\n(?P<state>(?:.*\n)*?\s*pc:\s*0x[0-9a-fA-F]+\s+cpsr:\s*0x[0-9a-fA-F]+\s+esr:\s*0x[0-9a-fA-F]+\s+far:\s*0x[0-9a-fA-F]+)", serial)
if panic:
    fault_pc = int(panic.group(3), 16)
    state = panic.group("state")
    values = {name.lower(): "0x" + value.lower() for name, value in
              re.findall(r"\b(x\d+|fp|lr|sp|pc|cpsr|esr|far):\s*(0x[0-9a-fA-F]+)", state)}
    kernel_path = root / "KernelCache.macho"
    report = {"cpu": int(panic.group(1)), "reason": panic.group(2),
              "panic_pc": hex(fault_pc), "panic_lr": panic.group(4).lower(),
              "registers": values}
    if kernel_path.exists():
        segments = macho(kernel_path.read_bytes())["segments"]
        for segment in segments:
            base = int(segment["address"], 16)
            if base <= fault_pc < base + segment["length"]:
                report["segment"] = segment["name"]
                report["segment_offset"] = hex(fault_pc - base)
                report["file_backed"] = fault_pc < base + segment["file_size"]
                break
    (root / "panic-context.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if fault_pc >= 0xfffffff000000000:
        result = subprocess.run(["xcrun", "llvm-objdump", "--disassemble",
            f"--start-address={hex(fault_pc - 32)}", f"--stop-address={hex(fault_pc + 96)}",
            str(kernel_path)], capture_output=True, text=True)
        (root / "panic-disassembly.txt").write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr)
        result.check_returncode()

first = re.search(r"Taking exception.*?with ELR (0x[0-9a-f]+)", trace, re.DOTALL)
if first:
    before = trace[:first.start()]
    register_blocks = list(re.finditer(r" PC=([0-9a-f]+) X00=([0-9a-f]+).*?PSTATE=[^\n]+", before, re.DOTALL))
    if register_blocks:
        registers = dict(re.findall(r"X(\d\d)=([0-9a-f]+)", register_blocks[-1].group(0)))
        kernel = (root / "KernelCache.macho").read_bytes()
        segments = macho(kernel)["segments"]
        strings = []
        for name in ["00", "01", "02", "03", "05", "06", "10", "11", "23"]:
            address = int(registers.get(name, "0"), 16)
            for segment in segments:
                base = int(segment["address"], 16)
                if base <= address < base + segment["file_size"]:
                    offset = segment["offset"] + address - base
                    value = kernel[offset:offset + 256].split(b"\0")[0]
                    if value and all(byte in (9, 10, 13) or 32 <= byte < 127 for byte in value):
                        strings.append(f"X{name} {hex(address)}: {value.decode('ascii')}")
        (root / "first-fault-strings.txt").write_text("\n".join(strings) + "\n")
        print("\n".join(strings))
    address = int(first.group(1), 16)
    if address >= 0xfffffff000000000:
        command = ["xcrun", "llvm-objdump", "--disassemble", f"--start-address={hex(address - 64)}",
                   f"--stop-address={hex(address + 256)}", str(root / "KernelCache.macho")]
        result = subprocess.run(command, capture_output=True, text=True)
        (root / "first-fault-disassembly.txt").write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr)
        result.check_returncode()
else:
    print("No CPU exception captured; inspect the serial output and instruction trace")
    blocks = re.findall(r"^0x([0-9a-fA-F]+):", trace, re.MULTILINE)
    if blocks and int(blocks[-1], 16) >= 0xfffffff000000000:
        address = int(blocks[-1], 16)
        result = subprocess.run(["xcrun", "llvm-objdump", "--disassemble",
            f"--start-address={hex(address - 64)}", f"--stop-address={hex(address + 192)}",
            str(root / "KernelCache.macho")], capture_output=True, text=True)
        (root / "last-block-disassembly.txt").write_text(result.stdout + result.stderr)
        result.check_returncode()

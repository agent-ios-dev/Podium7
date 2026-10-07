"""Disassemble the first actual exception PC from the captured QEMU trace."""
import pathlib
import re
import subprocess
import sys
import json
from analyze_firmware import macho


def run_diagnostic(command, **kwargs):
    """Run optional disassembly tools without hiding the primary boot result."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, **kwargs)
        output = result.stdout + result.stderr
        if result.returncode:
            output += f"\n(disassembler exited with status {result.returncode})\n"
        return output
    except OSError as error:
        return f"Disassembler unavailable: {error}\n"


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
    values = {name.lower(): value.lower() for name, value in
              re.findall(r"\b(x\d+|fp|lr|sp|pc|cpsr|esr|far):\s*(0x[0-9a-fA-F]+)", state)}
    kernel_path = root / "KernelCache.macho"
    report = {"cpu": int(panic.group(1)), "reason": panic.group(2),
              "panic_pc": hex(fault_pc), "panic_lr": panic.group(4).lower(),
              "registers": values}
    if kernel_path.exists():
        kernel = kernel_path.read_bytes()
        segments = macho(kernel)["segments"]
        for segment in segments:
            base = int(segment["address"], 16)
            if base <= fault_pc < base + segment["length"]:
                report["segment"] = segment["name"]
                report["segment_offset"] = hex(fault_pc - base)
                report["file_backed"] = fault_pc < base + segment["file_size"]
                if fault_pc < base + segment["file_size"]:
                    file_offset = segment["offset"] + fault_pc - base
                    word = int.from_bytes(kernel[file_offset:file_offset + 4], "little")
                    report["instruction_word"] = hex(word)
                    if word & 0xffe00c00 == 0xb8600800:
                        rt, rn, rm = word & 31, (word >> 5) & 31, (word >> 16) & 31
                        option, scaled = (word >> 13) & 7, (word >> 12) & 1
                        extension = {2: "uxtw", 3: "uxtx", 6: "sxtw", 7: "sxtx"}
                        modifier = f", #{(word >> 30) & 3}" if scaled else ""
                        report["decoded_instruction"] = (
                            f"ldr w{rt}, [x{rn}, {('w' if option in (2, 6) else 'x')}{rm}, "
                            f"{extension.get(option, 'option-' + str(option))}{modifier}]"
                        )
                break
    (root / "panic-context.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if fault_pc >= 0xfffffff000000000 and kernel_path.exists() and "segment" in report:
        segment = next(item for item in segments if item["name"] == report["segment"] and
                       int(item["address"], 16) <= fault_pc < int(item["address"], 16) + item["length"])
        base = int(segment["address"], 16)
        window_start = max(base, fault_pc - 32) & ~3
        window_end = min(base + segment["file_size"], fault_pc + 96) & ~3
        source_offset = segment["offset"] + window_start - base
        code = kernel[source_offset:source_offset + window_end - window_start]
        encoded = "\n".join(" ".join(f"0x{byte:02x}" for byte in code[index:index + 4])
                            for index in range(0, len(code) - 3, 4)) + "\n"
        disassembly = run_diagnostic(["xcrun", "llvm-mc", "--disassemble",
            "--triple=arm64-apple-ios"], input=encoded)
        text = (f"Code window starts at {hex(window_start)}; panic instruction at {hex(fault_pc)}\n" +
                disassembly)
        (root / "panic-disassembly.txt").write_text(text)
        print(text)

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
        disassembly = run_diagnostic(command)
        (root / "first-fault-disassembly.txt").write_text(disassembly)
        print(disassembly)
else:
    print("No CPU exception captured; inspect the serial output and instruction trace")
    blocks = re.findall(r"^0x([0-9a-fA-F]+):", trace, re.MULTILINE)
    if blocks and int(blocks[-1], 16) >= 0xfffffff000000000:
        address = int(blocks[-1], 16)
        disassembly = run_diagnostic(["xcrun", "llvm-objdump", "--disassemble",
            f"--start-address={hex(address - 64)}", f"--stop-address={hex(address + 192)}",
            str(root / "KernelCache.macho")])
        (root / "last-block-disassembly.txt").write_text(disassembly)

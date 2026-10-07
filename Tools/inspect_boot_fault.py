"""Disassemble the first actual exception PC from the captured QEMU trace."""
import pathlib
import re
import subprocess
from analyze_firmware import macho

root = pathlib.Path(".firmware")
trace = (root / "qemu-trace.txt").read_text(errors="replace")
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

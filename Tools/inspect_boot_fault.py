"""Disassemble the first actual exception PC from the captured QEMU trace."""
import pathlib
import re
import subprocess

root = pathlib.Path(".firmware")
trace = (root / "qemu-trace.txt").read_text(errors="replace")
first = re.search(r"Taking exception.*?with ELR (0x[0-9a-f]+)", trace, re.DOTALL)
if first:
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

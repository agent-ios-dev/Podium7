"""Exercise T8010 SoCHot and iPod9,1 temperature sensor windows."""
import argparse
import json
import pathlib
import subprocess
import tempfile

from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    # Generate addresses and boundary accesses explicitly: ARM64's immediate
    # range differs for 32- and 64-bit accesses, so use computed addresses.
    banks = [
        (0x202f30000, 0x8000, 0x470, "x"),
        (0x20e0bc000, 0x8000, 0x12c, "w"),
        (0x20e0c4000, 0x1000, 0x20, "w"),
        (0x20e0c0000, 0x1000, 0x20, "w"),
        (0x2102bc000, 0x4000, 0x20, "w"),
    ]
    instructions = [".text"]
    checks = []
    for base, size, fault_offset, width in banks:
        instructions += [f"movz x3, #{base & 0xffff}",
                         f"movk x3, #{(base >> 16) & 0xffff}, lsl #16",
                         f"movk x3, #{base >> 32}, lsl #32"]
        for offset in (fault_offset, size - (8 if width == "x" else 4)):
            instructions += [f"movz x6, #{offset}", "add x6, x3, x6",
                             f"ldr {width}4, [x6]", f"cmp {width}4, #0",
                             "b.ne failure", f"mov {width}5, #0x5678",
                             f"str {width}5, [x6]", f"ldr {width}4, [x6]",
                             f"cmp {width}4, {width}5", "b.ne failure"]
            checks.append(f"{width}-register read/write at {hex(base + offset)}")
    # sochot0 range 2 must share the tempsensor3-5 backing bank, not shadow it.
    instructions += ["movz x3, #0", "movk x3, #0x02f3, lsl #16",
                     "movk x3, #2, lsl #32", "movz x6, #0x4020",
                     "add x6, x3, x6", "mov w5, #0x1234", "str w5, [x6]",
                     "movz x3, #0x4000", "movk x3, #0x02f3, lsl #16",
                     "movk x3, #2, lsl #32", "ldr w4, [x3, #0x20]",
                     "cmp w4, w5", "b.ne failure"]
    checks.append("sochot0 range 2 aliases the tempsensor3-5 bank")
    assembly = "\n".join(instructions) + '''
mov x0, #0x20
adr x1, success_exit
hlt #0xf000
b .
failure:
mov x0, #0x20
adr x1, failure_exit
hlt #0xf000
b .
.p2align 3
success_exit:
.quad 0x20026, 0
failure_exit:
.quad 0x20026, 1
'''
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        (root / "test.s").write_text(assembly)
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"),
                        "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native", "-device",
            f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        passed = result.returncode == 0
        report.write_text(json.dumps({"passed": passed,
            "model": "T8010 SoCHot and shared temperature-sensor register banks",
            "checks": checks,
            "returncode": result.returncode, "stdout": result.stdout,
            "stderr": result.stderr}, indent=2))
        if not passed:
            raise RuntimeError("T8010 thermal sensor guest MMIO checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path,
                        default=pathlib.Path(".firmware/thermal-sensor-checks.json"))
    arguments = parser.parse_args()
    check(arguments.qemu, arguments.report)

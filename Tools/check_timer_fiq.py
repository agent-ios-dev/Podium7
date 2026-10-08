"""A real EL1 guest must receive physical and virtual timer FIQs."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = """.text
msr daifset, #15
msr spsel, #1
movz x0, #0
movk x0, #0x4501, lsl #16
mov sp, x0
adr x0, vectors
msr vbar_el1, x0
isb
mov x20, #0
mov x0, #24000
msr cntp_tval_el0, x0
mov x0, #1
msr cntp_ctl_el0, x0
isb
msr daifclr, #1
physical_wait:
cmp x20, #1
b.ne physical_wait
msr daifset, #1
mov x0, #24000
msr cntv_tval_el0, x0
mov x0, #1
msr cntv_ctl_el0, x0
isb
msr daifclr, #1
virtual_wait:
cmp x20, #2
b.ne virtual_wait
mov x0, #0x20
adr x1, success_exit
hlt #0xf000
b .
failure:
mov x0, #0x20
adr x1, failure_exit
hlt #0xf000
b .
fiq_handler:
cbnz x20, virtual_handler
mrs x0, cntp_ctl_el0
tbz x0, #2, failure
msr cntp_ctl_el0, xzr
b completed
virtual_handler:
mrs x0, cntv_ctl_el0
tbz x0, #2, failure
msr cntv_ctl_el0, xzr
completed:
isb
add x20, x20, #1
eret
.p2align 3
success_exit:
.quad 0x20026, 0
failure_exit:
.quad 0x20026, 1
.p2align 11
vectors:
"""
    for slot in range(16):
        assembly += ("b fiq_handler" if slot in (2, 6, 10, 14) else "b failure") + "\n.space 124\n"
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        source = root / "timer.s"
        obj = root / "timer.o"
        source.write_text(assembly)
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(source), "-o", str(obj)], check=True)
        code = text_section(obj.read_bytes())
        image = root / "timer.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research,cntfrq=24000000", "-m", "128", "-display", "none",
            "-monitor", "none", "-serial", "none", "-semihosting-config", "enable=on,target=native",
            "-device", f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=10)
        report.write_text(json.dumps({"passed": result.returncode == 0,
            "checks": ["physical timer enters EL1 FIQ vector", "virtual timer enters EL1 FIQ vector",
                       "ISTATUS is set in handler", "timer deasserts on disable and ERET resumes guest"],
            "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}, indent=2))
        if result.returncode: raise RuntimeError("real timer FIQ delivery failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/timer-fiq-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.report)

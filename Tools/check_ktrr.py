"""Verify sticky KTRR registers and real EL1 instruction fetch restriction."""
import argparse
import json
import pathlib
import subprocess
import tempfile
from check_qemu_registers import text_section
from qemu_probe import elf_image


def check(executable, report):
    assembly = '''.text
mov x0, #0x45000000
msr VBAR_EL1, x0
msr S3_4_C15_C2_3, x0
msr S3_4_C15_C2_4, x0
mov x1, #1
msr S3_4_C15_C2_2, x1
msr S3_4_C15_C2_3, xzr
mrs x2, S3_4_C15_C2_3
cmp x2, x0
b.ne failure
msr S3_4_C15_C2_2, xzr
mrs x2, S3_4_C15_C2_2
cmp x2, #1
b.ne failure
// Build one 1-GiB identity block in TTBR0, 4-KiB translation granule.
mov x4, #0x46000000
mov x1, #0x40000000
orr x1, x1, #0x400
orr x1, x1, #1
str x1, [x4, #8]
dsb sy
msr TTBR0_EL1, x4
mov x0, #0x20
movk x0, #0x80, lsl #16
msr TCR_EL1, x0
mov x0, #0xff
msr MAIR_EL1, x0
isb
mov x0, #0x0839
movk x0, #0x00c5, lsl #16
msr SCTLR_EL1, x0
isb
// Allowed current code remains executable; jump outside locked KTRR range.
mov x16, #0x45000000
add x16, x16, #8, lsl #12
br x16
b failure
failure:
mov x0, #0x20
adr x1, failure_exit
hlt #0xf000
b .
.org 0x200
// EL1h synchronous vector must be reached by a real instruction permission fault.
mrs x0, ESR_EL1
lsr x0, x0, #26
cmp x0, #0x21
b.ne failure
mrs x0, FAR_EL1
mov x1, #0x45000000
add x1, x1, #8, lsl #12
cmp x0, x1
b.ne failure
mov x0, #0x20
adr x1, success_exit
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
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"), "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code), (0x45008000, 4, bytes.fromhex("000020d4"))]))
        trace = report.with_name("ktrr-check-trace.txt")
        command = [executable, "-machine", "virt,secure=off,virtualization=off", "-cpu", "podium7-research",
            "-m", "128", "-display", "none", "-monitor", "none", "-serial", "none",
            "-semihosting-config", "enable=on,target=native", "-device", f"loader,file={image},cpu-num=0",
            "-d", "in_asm,int,guest_errors,unimp", "-D", str(trace)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        report.write_text(json.dumps({"passed": result.returncode == 0,
            "checks": ["sticky range/lock", "EL1 allowed fetch with MMU", "EL1 forbidden fetch gives Instruction Abort"],
            "returncode": result.returncode, "stderr": result.stderr}, indent=2))
        if result.returncode != 0:
            raise RuntimeError("KTRR guest enforcement checks failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/ktrr-checks.json"))
    args = parser.parse_args()
    check(args.qemu, args.report)

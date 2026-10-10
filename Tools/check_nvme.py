"""Real PCI enumeration, NVMe queue DMA and persistent 16 GiB disk I/O.

Polling completion test; deliberately does not claim Apple DART/MSI support.
The scratch disk is fresh and isolated from any user's virtual iPod.
"""
import argparse
import json
import pathlib
import subprocess
import tempfile
import os
import re

from check_qemu_registers import text_section
from qemu_probe import elf_image

DISK_BYTES = 16 << 30


def assembly(dart=False, msi=False):
    source = '''.text
mov x20, #1
// Apple port0 link bit reflects the real root port, only while enabled.
movz x3, #0
movk x3, #0x100, lsl #16
movk x3, #6, lsl #32
ldr w0, [x3, #0x208]
tbnz w0, #6, failure
tbnz w0, #0, failure
mov w0, #1
str w0, [x3, #0x80]
mov w0, #0x80000000
str w0, [x3, #0x140]
ldr w0, [x3, #0x208]
tbz w0, #6, failure
tbz w0, #0, failure
str wzr, [x3, #0x80]
ldr w0, [x3, #0x208]
tbnz w0, #6, failure
tbnz w0, #0, failure
movz x21, #0
movk x21, #0x1000, lsl #16
movk x21, #6, lsl #32
ldr w0, [x21]
movz w1, #0x1b36
movk w1, #0xc, lsl #16
cmp w0, w1
b.ne failure
// Traverse the real PCI capability lists on all four DeviceTree root ports.
mov x4, x21
mov x5, #4
root_caps:
ldr w0, [x4]
cmp w0, w1
b.ne failure
ldrb w6, [x4, #0x34]
mov x7, #48
cap_next:
cbz w6, failure
add x8, x4, x6
ldrb w9, [x8]
cmp w9, #0x10
b.eq cap_found
ldrb w6, [x8, #1]
subs x7, x7, #1
b.ne cap_next
b failure
cap_found:
cmp x5, #4
b.eq root_next
ldrh w9, [x8, #0x12]
tbnz w9, #13, failure
root_next:
add x4, x4, #8, lsl #12
subs x5, x5, #1
b.ne root_caps
mov w0, #6
strh w0, [x21, #4]
movz w0, #0x100
movk w0, #1, lsl #16
str w0, [x21, #0x18]
movz w0, #0x2001
movk w0, #0x2001, lsl #16
str w0, [x21, #0x24]
mov w0, #6
str w0, [x21, #0x28]
str w0, [x21, #0x2c]
mov x20, #2
mov x0, #0x100000
add x21, x21, x0
ldr w0, [x21, #8]
lsr w0, w0, #8
movz w1, #0x802
movk w1, #1, lsl #16
cmp w0, w1
b.ne failure
movz w0, #4
movk w0, #0x2000, lsl #16
str w0, [x21, #0x10]
mov w0, #6
str w0, [x21, #0x14]
strh w0, [x21, #4]
movz x22, #0
movk x22, #0x2000, lsl #16
movk x22, #6, lsl #32
mov x20, #3
ldr w0, [x22, #8]
cbz w0, failure
// Clear queues and buffers (fresh memory only).
movz x0, #0
movk x0, #0x4501, lsl #16
mov x1, #0x20000
zero:
str xzr, [x0], #8
subs x1, x1, #8
b.ne zero
movz w0, #0xf
movk w0, #0xf, lsl #16
str w0, [x22, #0x24]
movz x0, #0
movk x0, #0x4501, lsl #16
str x0, [x22, #0x28]
movz x0, #0x4000
movk x0, #0x4501, lsl #16
str x0, [x22, #0x30]
movz w0, #1
movk w0, #0x46, lsl #16
str w0, [x22, #0x14]
mov x1, #0x100000
ready:
ldr w0, [x22, #0x1c]
tbnz w0, #1, failure
tbnz w0, #0, initialized
subs x1, x1, #1
b.ne ready
b failure
initialized:
mov x27, #0
// Each command has a distinct CID and completion entry.
movz x23, #0
movk x23, #0x4501, lsl #16
movz x24, #0x4000
movk x24, #0x4501, lsl #16
mov x25, #0
mov x20, #4
mov w0, #6
str w0, [x23]
movz x0, #0x8000
movk x0, #0x4501, lsl #16
str x0, [x23, #24]
mov w0, #1
str w0, [x23, #40]
bl submit_admin
// NN is the controller namespace limit, not the active namespace count.
movz x0, #0x8000
movk x0, #0x4501, lsl #16
ldr w1, [x0, #516]
cbz w1, failure
mov x20, #5
movz w0, #6
movk w0, #1, lsl #16
str w0, [x23]
mov w0, #1
str w0, [x23, #4]
movz x0, #0xc000
movk x0, #0x4501, lsl #16
str x0, [x23, #24]
bl submit_admin
movz x0, #0xc000
movk x0, #0x4501, lsl #16
ldr x1, [x0]
movz x2, #0
movk x2, #0x200, lsl #16
cmp x1, x2
b.ne failure
ldrb w1, [x0, #130]
cmp w1, #9
b.ne failure
mov x20, #6
movz w0, #5
movk w0, #2, lsl #16
str w0, [x23]
movz x0, #0
movk x0, #0x4502, lsl #16
str x0, [x23, #24]
movz w0, #1
movk w0, #0xf, lsl #16
str w0, [x23, #40]
mov w0, #1
str w0, [x23, #44]
bl submit_admin
mov x20, #7
movz w0, #1
movk w0, #3, lsl #16
str w0, [x23]
movz x0, #0x4000
movk x0, #0x4502, lsl #16
str x0, [x23, #24]
movz w0, #1
movk w0, #0xf, lsl #16
str w0, [x23, #40]
movz w0, #1
movk w0, #1, lsl #16
str w0, [x23, #44]
bl submit_admin
movz x0, #0x8000
movk x0, #0x4502, lsl #16
mov x1, #0
pattern:
strb w1, [x0, x1]
add x1, x1, #1
cmp x1, #512
b.ne pattern
movz x23, #0x4000
movk x23, #0x4502, lsl #16
movz x24, #0
movk x24, #0x4502, lsl #16
mov x25, #0
mov x20, #8
movz w0, #1
movk w0, #4, lsl #16
str w0, [x23]
mov w0, #1
str w0, [x23, #4]
movz x0, #0x8000
movk x0, #0x4502, lsl #16
str x0, [x23, #24]
mov x0, #8
str x0, [x23, #40]
bl submit_io
mov x20, #9
movz w0, #2
movk w0, #5, lsl #16
str w0, [x23]
mov w0, #1
str w0, [x23, #4]
movz x0, #0xc000
movk x0, #0x4502, lsl #16
str x0, [x23, #24]
mov x0, #8
str x0, [x23, #40]
bl submit_io
movz x0, #0xc000
movk x0, #0x4502, lsl #16
mov x1, #0
compare:
ldrb w2, [x0, x1]
and w3, w1, #255
cmp w2, w3
b.ne failure
add x1, x1, #1
cmp x1, #512
b.ne compare
mov x20, #0
b finish
submit_admin:
mov x26, #0x1000
b submit
submit_io:
mov x26, #0x1008
submit:
add x25, x25, #1
dsb sy
str w25, [x22, x26]
mov x1, #0x1000000
completion:
ldrh w0, [x24, #14]
tbnz w0, #0, completed
subs x1, x1, #1
b.ne completion
b failure
completed:
lsr w0, w0, #1
cbnz x27, completion_id
cbnz w0, failure
b completion_id
completion_id:
// Verify this completion belongs to the submitted command.
ldrh w0, [x24, #12]
ldrh w1, [x23, #2]
cmp w0, w1
b.ne failure
add x26, x26, #4
str w25, [x22, x26]
add x23, x23, #64
add x24, x24, #16
ret
failure:
finish:
adr x1, exit_block
str x20, [x1, #8]
mov x0, #0x20
hlt #0xf000
b .
.p2align 3
exit_block:
.quad 0x20026, 0
'''
    if dart:
        setup = '''// Real DMA uses distinct IOVAs and the original port0 register bank.
movz x0, #0
movk x0, #0x4503, lsl #16
mov x1, #0x2000
dart_zero:
str xzr, [x0], #8
subs x1, x1, #8
b.ne dart_zero
movz x0, #0
movk x0, #0x4503, lsl #16
movz x1, #0x1003
movk x1, #0x4503, lsl #16
str x1, [x0]
add x0, x0, #1, lsl #12
add x0, x0, #0x80
movz x1, #3
movk x1, #0x4501, lsl #16
mov x2, #32
dart_leaf:
str x1, [x0], #8
add x1, x1, #1, lsl #12
subs x2, x2, #1
b.ne dart_leaf
movz x3, #0x8000
movk x3, #0x100, lsl #16
movk x3, #6, lsl #32
movz w0, #0x5030
movk w0, #0x8004, lsl #16
str w0, [x3, #0x40]
mov w0, #0x100
str w0, [x3, #0x20]
dsb sy
'''
        # CPU queue accesses stay physical. Only controller DMA pointers change.
        source, changed = re.subn(r'(movk x0, #)0x450([12])(, lsl #16\nstr x0, \[x(?:22, #0x(?:28|30)|23, #24)\])',
            lambda m: m[1] + '0x800' + m[2] + m[3], source)
        if changed != 8:
            raise ValueError(f"NVMe DMA pointer anchors changed: {changed}")
        source = source.replace("movz w0, #0xf\nmovk w0, #0xf, lsl #16", setup + "movz w0, #0xf\nmovk w0, #0xf, lsl #16")
        negative = '''// Posted DMA writes may complete at NVMe despite a host IOMMU fault.
// Require unchanged physical destination pages; verify mapper rejection in trace.
mov x20, #10
mov x27, #1
movz x0, #0x1170
movk x0, #0x4503, lsl #16
movz x1, #0xe083
movk x1, #0x4502, lsl #16
str x1, [x0]
movz w0, #2
movk w0, #6, lsl #16
str w0, [x23]
mov w0, #1
str w0, [x23, #4]
movz x0, #0xe000
movk x0, #0x8002, lsl #16
str x0, [x23, #24]
mov x0, #8
str x0, [x23, #40]
dsb sy
bl submit_io
mov x20, #11
movz x0, #0x1178
movk x0, #0x4503, lsl #16
str xzr, [x0]
movz w0, #2
movk w0, #7, lsl #16
str w0, [x23]
mov w0, #1
str w0, [x23, #4]
movz x0, #0xf000
movk x0, #0x8002, lsl #16
str x0, [x23, #24]
mov x0, #8
str x0, [x23, #40]
dsb sy
bl submit_io
movz x0, #0xe000
movk x0, #0x4502, lsl #16
mov x1, #0x2000
unchanged:
ldr x2, [x0], #8
cbnz x2, failure
subs x1, x1, #8
b.ne unchanged
'''
        source = source.replace("mov x20, #0\nb finish", negative + "mov x20, #0\nb finish")
    if msi:
        if not dart:
            raise ValueError("MSI research requires the verified DART DMA path")
        setup = '''// Locate MSI-X table through its genuine capability BIR.
ldrb w0, [x21, #0x34]
mov x1, #48
msix_next:
cbz w0, failure
add x2, x21, x0
ldrb w3, [x2]
cmp w3, #0x11
b.eq msix_found
ldrb w0, [x2, #1]
subs x1, x1, #1
b.ne msix_next
b failure
msix_found:
ldr w0, [x2, #4]
and w1, w0, #7
cbz w1, msix_bar0
cmp w1, #4
b.ne failure
movz w1, #4
movk w1, #0x2008, lsl #16
str w1, [x21, #0x20]
mov w1, #6
str w1, [x21, #0x24]
movz x1, #0
movk x1, #0x2008, lsl #16
b msix_base
msix_bar0:
movz x1, #0
movk x1, #0x2000, lsl #16
msix_base:
and w0, w0, #0xfffffff8
movk x1, #6, lsl #32
add x1, x1, x0
movz x0, #0xf000
movk x0, #0xbfff, lsl #16
str x0, [x1]
str wzr, [x1, #8]
str wzr, [x1, #12]
ldrh w0, [x2, #2]
and w0, w0, #0xbfff
orr w0, w0, #0x8000
strh w0, [x2, #2]
dsb sy
'''
        source = source.replace('movz x22, #0', setup + 'movz x22, #0', 1)
        # Enable interrupts for the I/O CQ as well as the admin CQ.
        source = source.replace('mov w0, #1\nstr w0, [x23, #44]\nbl submit_admin',
                                'mov w0, #3\nstr w0, [x23, #44]\nbl submit_admin', 1)
        prefix = '''msr daifset, #15
msr spsel, #1
movz x0, #0
movk x0, #0x4504, lsl #16
mov sp, x0
adr x0, msi_vectors
msr vbar_el1, x0
isb
mov x28, #0
mov x29, #0
movz x16, #0
movk x16, #0xe10, lsl #16
movk x16, #2, lsl #32
mov w17, #1
str w17, [x16, #0x3480]
add x16, x16, #4, lsl #12
str w17, [x16, #0x1a4]
msr daifclr, #2
'''
        source = source.replace('.text\n', '.text\n' + prefix, 1)
        source = source.replace('submit:\nadd x25', 'submit:\nadd x29, x29, #1\nadd x25', 1)
        wait = '''// A CQ entry alone does not pass: a real EL1 IRQ is required.
mov x1, #0x1000000
msi_wait:
cmp x28, x29
b.eq msi_received
subs x1, x1, #1
b.ne msi_wait
b failure
msi_received:
'''
        source = source.replace('completed:\n', 'completed:\n' + wait, 1)
        unmask = '''movz x16, #0
movk x16, #0xe10, lsl #16
movk x16, #2, lsl #32
add x16, x16, #4, lsl #12
mov w17, #1
str w17, [x16, #0x1a4]
'''
        source = source.replace('str w25, [x22, x26]\nadd x23',
                                'str w25, [x22, x26]\ndsb sy\n' + unmask + 'add x23', 1)
        source += '''msi_handler:
movz x16, #0
movk x16, #0xe10, lsl #16
movk x16, #2, lsl #32
ldr w17, [x16, #0x2004]
movz w16, #0x120
movk w16, #1, lsl #16
cmp w17, w16
b.ne failure
add x28, x28, #1
eret
.p2align 11
msi_vectors:
'''
        for slot in range(16):
            source += ('b msi_handler' if slot in (1, 5, 9, 13) else 'b failure') + '\n.space 124\n'
    return source


def check(executable, report, dart=False, msi=False):
    report.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        disk = root / "scratch-16g.raw"
        with disk.open("xb") as stream:
            stream.truncate(DISK_BYTES)
        (root / "test.s").write_text(assembly(dart, msi))
        subprocess.run(["xcrun", "clang", "-arch", "arm64", "-c", str(root / "test.s"),
                        "-o", str(root / "test.o")], check=True)
        code = text_section((root / "test.o").read_bytes())
        image = root / "test.elf"
        image.write_bytes(elf_image(0x45000000, [(0x45000000, len(code), code)]))
        result = subprocess.run([executable, "-machine", "virt,secure=off,virtualization=off",
            "-cpu", "podium7-research", "-m", "128", "-display", "none", "-monitor", "none",
            "-serial", "none", "-semihosting-config", "enable=on,target=native",
            "-drive", f"if=none,id=podium7-storage,format=raw,file={disk}",
            "-trace", "enable=pci_nvme*", "-D", str(root / "nvme-trace.txt"),
            "-device", f"loader,file={image},cpu-num=0"], capture_output=True, text=True, timeout=25,
            env={**os.environ, "PODIUM7_RESEARCH_NVME_DART": "1" if dart else "0",
                 "PODIUM7_RESEARCH_NVME_MSI": "1" if msi else "0"})
        with disk.open("rb") as stream:
            stream.seek(8 * 512)
            persisted = stream.read(512) == bytes(range(256)) * 2
        trace_text = (root / "nvme-trace.txt").read_text(errors="replace") if (root / "nvme-trace.txt").exists() else ""
        fault_evidence = ("NVME-DART rejected permission iova=000000008002e" in trace_text and
                          "NVME-DART rejected unmapped iova=000000008002f" in trace_text)
        passed = result.returncode == 0 and persisted and disk.stat().st_size == DISK_BYTES and (not dart or fault_evidence)
        report.write_text(json.dumps({"passed": passed, "disk_bytes": disk.stat().st_size,
            "allocated_disk_bytes": disk.stat().st_blocks * 512 if hasattr(disk.stat(), "st_blocks") else None,
            "persistent_write_verified": persisted, "returncode": result.returncode,
            "checks": ["real root port and class 010802 NVMe endpoint enumeration",
                       "four original host-port capability lists; empty ports have no active link",
                       "admin queue DMA: identify controller and 16 GiB namespace",
                       "I/O queue creation, 512-byte write and independent read comparison",
                       "host-side exact persisted sector verification"],
            "interrupt_delivery_tested": msi, "research_port0_dart_tested": dart,
            "dma_permission_and_invalid_leaf_checked": dart,
            "mapper_fault_evidence_confirmed": fault_evidence if dart else None,
            "dart_hardware_fault_irq_tested": False,
            "stdout": result.stdout, "stderr": result.stderr,
            "nvme_trace_tail": trace_text[-8192:]}, indent=2))
        if not passed:
            raise RuntimeError(f"Real NVMe DMA checks failed at stage {result.returncode}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--report", type=pathlib.Path, default=pathlib.Path(".firmware/nvme-checks.json"))
    parser.add_argument("--dart", action="store_true", help="Verify nonidentity IOVA DMA, read-only and invalid-page errors")
    parser.add_argument("--msi", action="store_true", help="Require real NVMe MSI-X delivery into EL1 IRQ vectors")
    args = parser.parse_args()
    check(args.qemu, args.report, args.dart, args.msi)

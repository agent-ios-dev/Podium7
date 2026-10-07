"""Install an opt-in research CPU on the pinned QEMU 10.0.0 sources.

The four observed APRR controls are read/write latches only. Permission
overlay/MMU enforcement is NOT implemented by this experiment. Unknown
registers still trap. No Apple kernel instruction is patched out.
Changes to QEMU sources are GPL-2.0-or-later, matching the surrounding files.
"""
import argparse
import pathlib
import subprocess

PIN = "7c949c53e936aa3a658d84ab53bae5cadaa5d59c"


def replace_once(path, needle, replacement):
    text = path.read_text()
    if text.count(needle) != 1:
        raise ValueError(f"QEMU source anchor changed: {path}")
    path.write_text(text.replace(needle, replacement))


def patch(directory):
    actual = subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()
    if actual != PIN:
        raise ValueError(f"QEMU commit mismatch: {actual} != {PIN}")
    if subprocess.check_output(["git", "-C", str(directory), "status", "--porcelain"], text=True).strip():
        raise ValueError("refusing to patch a dirty QEMU checkout")
    # QEMU reserves fieldoffset=0 to mean no backing storage.
    replace_once(directory / "target/arm/cpu.h", "    uint32_t regs[16];",
                 "    uint32_t regs[16];\n    uint64_t podium7_aprr[4]; /* research latch state; not full APRR */")
    definitions = '''
/* Podium7 research CPU. GPL-2.0-or-later.
 * APRR register latches permit bootstrap diagnosis only; no APRR page
 * permission enforcement yet. Do not describe this as a complete A10 CPU.
 */
static const ARMCPRegInfo podium7_aprr_regs[] = {
'''
    for index, number in enumerate([0, 1, 6, 7]):
        definitions += f'''    {{ .name = "PODIUM7_APRR_LATCH_{number}", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 4, .crn = 15, .crm = 2, .opc2 = {number},
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[{index}]) }},
'''
    definitions += '''};
static void podium7_research_initfn(Object *obj)
{
    aarch64_max_initfn(obj);
    define_arm_cp_regs(ARM_CPU(obj), podium7_aprr_regs);
}

'''
    replace_once(directory / "target/arm/cpu64.c", "static const ARMCPUInfo aarch64_cpus[] = {",
                 definitions + 'static const ARMCPUInfo aarch64_cpus[] = {\n    { .name = "podium7-research", .initfn = podium7_research_initfn },')
    replace_once(directory / "hw/arm/virt.c", '        ARM_CPU_TYPE_NAME("max"),',
                 '        ARM_CPU_TYPE_NAME("max"),\n        ARM_CPU_TYPE_NAME("podium7-research"),')
    # Apple's implementation-defined encodings permit EL1 despite opc1=4.
    # Narrow this exception to our explicitly named four research controls.
    replace_once(directory / "target/arm/helper.c", '        assert((r->access & ~mask) == 0);',
                 '''        if (r->opc0 == 3 && r->opc1 == 4 && r->crn == 15 &&
            r->crm == 2 && (r->opc2 == 0 || r->opc2 == 1 ||
                           r->opc2 == 6 || r->opc2 == 7) &&
            g_str_has_prefix(r->name, "PODIUM7_APRR_LATCH_")) {
            mask = PL1_RW;
        }
        assert((r->access & ~mask) == 0);''')
    subprocess.run(["git", "-C", str(directory), "diff", "--check"], check=True)
    print("Registered podium7-research on pinned QEMU; APRR enforcement remains unsupported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    patch(parser.parse_args().directory)

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
    # Runtime-only diagnostic for the unpatched 19H422 ACC decoder. No register
    # values, instruction bytes or branch decisions are modified by this helper.
    with (directory / "target/arm/helper.h").open("a") as output:
        output.write("\n#ifdef TARGET_AARCH64\nDEF_HELPER_2(podium7_acc_trace, void, env, i64)\n#endif\n")
    with (directory / "target/arm/tcg/helper-a64.c").open("a") as output:
        output.write(r'''
#include "exec/cpu-common.h"
#include "qemu/bswap.h"
void HELPER(podium7_acc_trace)(CPUARMState *env, uint64_t pc)
{
    static unsigned logged;
    static unsigned irq_logged;
    if ((pc == 0xfffffff00777f958ULL || pc == 0xfffffff00777f8ecULL) &&
        irq_logged++ < 64) {
        uint8_t raw[8];
        char name[49] = { 0 };
        CPUState *cpu = env_cpu(env);
        if (cpu_memory_rw_debug(cpu, env->xregs[1] + 0x10, raw, 8, 0) == 0) {
            uint64_t pointer = ldq_le_p(raw);
            if (pointer >= 0xffffffe000000000ULL &&
                cpu_memory_rw_debug(cpu, pointer, (uint8_t *)name, 48, 0) == 0) {
                for (unsigned i = 0; i < 48 && name[i]; i++) {
                    if ((unsigned char)name[i] < 32 || (unsigned char)name[i] > 126) {
                        name[i] = '.';
                    }
                }
            }
        }
        qemu_log("PODIUM7 IRQ-CONTROLLER pc=%016" PRIx64 " name=%s object=%016" PRIx64 "\n",
                 pc, name, env->xregs[2]);
    }
    if (logged++ < 256 || pc == 0xfffffff0069445c4ULL ||
        pc == 0xfffffff005b898e4ULL || pc == 0xfffffff0068fcb94ULL ||
        pc == 0xfffffff0068fcb98ULL ||
        (pc >= 0xfffffff0077b9084ULL && pc <= 0xfffffff0077b910cULL)) {
        qemu_log("PODIUM7 BOOT-ARG pc=%016" PRIx64 " x0=%016" PRIx64
                 " x1=%016" PRIx64 " x2=%016" PRIx64 " x3=%016" PRIx64
                 " x8=%016" PRIx64 " x9=%016" PRIx64 " x19=%016" PRIx64 " x20=%016" PRIx64
                 " fp=%016" PRIx64 " lr=%016" PRIx64 "\n",
                 pc, env->xregs[0], env->xregs[1], env->xregs[2], env->xregs[3],
                 env->xregs[8], env->xregs[9], env->xregs[19], env->xregs[20],
                 env->xregs[29], env->xregs[30]);
    }
}
''')
    replace_once(directory / "target/arm/tcg/translate-a64.c",
                 "    s->insn = insn;\n    s->base.pc_next = pc + 4;",
                 '''    s->insn = insn;
    s->base.pc_next = pc + 4;
    if (pc == 0xfffffff0069459f4ULL || pc == 0xfffffff006945b6cULL || pc == 0xfffffff0069445c4ULL ||
        pc == 0xfffffff0077b9084ULL || pc == 0xfffffff0077b9108ULL ||
        pc == 0xfffffff0077b910cULL || pc == 0xfffffff005b898e4ULL ||
        pc == 0xfffffff00777f958ULL || pc == 0xfffffff00777f8ecULL ||
        pc == 0xfffffff0068fcb94ULL || pc == 0xfffffff0068fcb98ULL) {
        gen_helper_podium7_acc_trace(tcg_env, tcg_constant_i64(pc));
    }''')
    # QEMU reserves fieldoffset=0 to mean no backing storage.
    replace_once(directory / "target/arm/cpu.h", "    uint32_t regs[16];",
                 "    uint32_t regs[16];\n    uint64_t podium7_aprr[32]; /* fixed research register bank; not full Apple semantics */")
    definitions = '''
#include "exec/exec-all.h"
#include "exec/cputlb.h"
/* KTRR lower/upper are inclusive 16-KiB page bases; lock is sticky until reset. */
static void podium7_ktrr_write(CPUARMState *env, const ARMCPRegInfo *ri,
                              uint64_t value)
{
    if (env->podium7_aprr[18] & 1) { return; }
    if (ri->opc2 == 2) { env->podium7_aprr[18] = value & 1; }
    else if (ri->opc2 == 3) { env->podium7_aprr[16] = value & ~0x3fffULL; }
    else if (ri->opc2 == 4) { env->podium7_aprr[17] = value & ~0x3fffULL; }
    tlb_flush(env_cpu(env));
}
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
    definitions += '''    { .name = "PODIUM7_HID5_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 0, .crn = 15, .crm = 5, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[4]) },
    { .name = "PODIUM7_HID4_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 0, .crn = 15, .crm = 4, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[5]) },
    { .name = "PODIUM7_HID0_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 0, .crn = 15, .crm = 0, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[6]) },
    { .name = "PODIUM7_LSU_ERR_CTL", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 3, .crn = 15, .crm = 1, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[7]) },
    { .name = "PODIUM7_HID1_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 0, .crn = 15, .crm = 1, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[8]) },
    { .name = "PODIUM7_PMC0_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 2, .crn = 15, .crm = 0, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[9]) },
    { .name = "PODIUM7_PMC1_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 2, .crn = 15, .crm = 1, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[10]) },
    { .name = "PODIUM7_PMCR0_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 1, .crn = 15, .crm = 0, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[11]) },
    { .name = "PODIUM7_IPI_STATUS_SINGLE_CPU", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 5, .crn = 15, .crm = 10, .opc2 = 1,
      .access = PL1_RW, .type = ARM_CP_CONST | ARM_CP_OVERRIDE, .resetvalue = 0 },
'''
    # PMCR1 controls counting modes; PMCR2..4 are the companion controls
    # documented by XNU's PMU setup and existing Apple CPU models.
    for number in range(1, 5):
        definitions += f'''    {{ .name = "PODIUM7_PMCR{number}_LATCH", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 1, .crn = 15, .crm = {number}, .opc2 = 0,
      .access = PL1_RW, .resetvalue = 0,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[{11 + number}]) }},
'''
    for number, name, slot in [(3, "LOWER", 16), (4, "UPPER", 17), (2, "LOCK", 18)]:
        definitions += f'''    {{ .name = "PODIUM7_KTRR_{name}", .state = ARM_CP_STATE_AA64,
      .opc0 = 3, .opc1 = 4, .crn = 15, .crm = 2, .opc2 = {number},
      .access = PL1_RW, .type = ARM_CP_IO | ARM_CP_OVERRIDE, .resetvalue = 0,
      .writefn = podium7_ktrr_write,
      .fieldoffset = offsetof(CPUARMState, podium7_aprr[{slot}]) }},
'''
    definitions += '''};
static void podium7_research_initfn(Object *obj)
{
    aarch64_max_initfn(obj);
    /* Apple PMCR3 shares the encoding of Cortex CBAR_EL1. Apple has no
     * inherited Cortex CBAR; do not reinstall it at ARM CPU realization. */
    unset_feature(&ARM_CPU(obj)->env, ARM_FEATURE_CBAR_RO);
    unset_feature(&ARM_CPU(obj)->env, ARM_FEATURE_CBAR);
    define_arm_cp_regs(ARM_CPU(obj), podium7_aprr_regs);
}

'''
    # This derived CPU uses Apple encodings that overlap implementation-defined
    # Cortex controls inherited from max/A57. Override only our named entries.
    definitions = definitions.replace('.access = PL1_RW, .resetvalue = 0,',
                                      '.access = PL1_RW, .type = ARM_CP_OVERRIDE, .resetvalue = 0,')
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
        if (r->opc0 == 3 && r->opc1 == 5 && r->crn == 15 &&
            r->crm == 10 && r->opc2 == 1 &&
            !strcmp(r->name, "PODIUM7_IPI_STATUS_SINGLE_CPU")) {
            mask = PL1_RW;
        }
        if (r->opc0 == 3 && r->opc1 == 4 && r->crn == 15 &&
            r->crm == 2 && r->opc2 >= 2 && r->opc2 <= 4 &&
            g_str_has_prefix(r->name, "PODIUM7_KTRR_")) {
            mask = PL1_RW;
        }
        assert((r->access & ~mask) == 0);''')
    replace_once(directory / "target/arm/ptw.c",
        '    if (!(result->f.prot & (1 << access_type))) {\n        fi->type = ARMFault_Permission;\n        goto do_fault;\n    }\n\n    /* If FEAT_HAFDBS',
        '''    if (aarch64 && el == 1 && !regime_is_user(env, mmu_idx) &&
        (env->podium7_aprr[18] & 1)) {
        uint64_t lower = env->podium7_aprr[16];
        uint64_t upper = env->podium7_aprr[17];
        uint64_t physical = descaddr; /* computed output; result is assigned below */
        if (physical < lower || upper < lower ||
            physical > (upper | 0x3fffULL)) {
            result->f.prot &= ~PAGE_EXEC;
        }
    }
    if (!(result->f.prot & (1 << access_type))) {
        fi->type = ARMFault_Permission;
        goto do_fault;
    }

    /* If FEAT_HAFDBS''')
    replace_once(directory / "target/arm/ptw.c",
        '    result->f.lg_page_size = ctz64(page_size);\n    return false;',
        '''    result->f.lg_page_size = ctz64(page_size);
    /* Record kernel-heap virtual mappings outside the harness RAM. These can
     * be legitimate MMIO mappings; an out-of-RAM address alone is not a fault. */
    static unsigned podium7_out_of_ram_mappings;
    if ((env->podium7_aprr[18] & 1) &&
        address >= 0xffffffe000000000ULL &&
        (descaddr < 0x40000000ULL || descaddr >= 0xc0000000ULL) &&
        podium7_out_of_ram_mappings < 512) {
        qemu_log(
            "PODIUM7 KVA-OUTSIDE-HARNESS-RAM va=%016" PRIx64 " pa=%016" PRIx64
            " page-size=%" PRIu64 "\\n",
            (uint64_t)address, (uint64_t)descaddr, (uint64_t)page_size);
        podium7_out_of_ram_mappings++;
    }
    if (aarch64 && el == 1 && !regime_is_user(env, mmu_idx) &&
        (env->podium7_aprr[18] & 1)) {
        result->f.lg_page_size = MIN(result->f.lg_page_size, 14);
    }
    return false;''')
    uart = '''
/* Podium7 polling TX-only Samsung UART research device. GPL-2.0-or-later.
 * Address 0x20a0c0000 and 0x4000 span come from n112ap DeviceTree reg/ranges.
 * No RX, FIFO timing, interrupts or complete platform model yet.
 */
typedef struct Podium7UART {
    MemoryRegion region;
    uint32_t registers[64];
    bool console;
} Podium7UART;
static uint64_t podium7_uart_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7UART *uart = opaque;
    if (address == 0x10) { return 6; } /* TX buffer/shift register empty; RX empty */
    if (address == 0x18 || address == 0x14 || address == 0x24) { return 0; }
    return address < sizeof(uart->registers) ? uart->registers[address / 4] : 0;
}
static void podium7_uart_write(void *opaque, hwaddr address, uint64_t value,
                              unsigned size)
{
    Podium7UART *uart = opaque;
    if (address == 0x20) { if (uart->console) { putchar(value & 0xff); fflush(stdout); } return; }
    if (address < sizeof(uart->registers)) { uart->registers[address / 4] = value; }
}
static const MemoryRegionOps podium7_uart_ops = {
    .read = podium7_uart_read, .write = podium7_uart_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 4 },
};
static void podium7_uart_create(MachineState *machine, MemoryRegion *memory)
{
    static const hwaddr banks[] = {
        0x20a0c0000ULL, 0x20a0c4000ULL, 0x20a0d0000ULL,
        0x20a0d4000ULL, 0x20a0d8000ULL,
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        Podium7UART *uart = g_new0(Podium7UART, 1);
        uart->console = i == 0;
        memory_region_init_io(&uart->region, OBJECT(machine), &podium7_uart_ops,
                             uart, "podium7-uart-tx-only", 0x4000);
        memory_region_add_subregion(memory, banks[i], &uart->region);
    }
}

/* Minimal one-plane A10 MCC RoRgn research model. GPL-2.0-or-later.
 * Offsets: published A10 RoRgn base/end/lock. Aperture: n112ap mcc DT.
 * No cache timing, multiple planes or CPU KTRR execute enforcement yet.
 */
typedef struct Podium7MCC {
    MemoryRegion io, protected_alias;
    MachineState *machine;
    MemoryRegion *memory;
    uint32_t lower, upper;
    unsigned logged_accesses;
    bool locked;
} Podium7MCC;
static uint64_t podium7_mcc_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7MCC *mcc = opaque;
    uint64_t value = 0;
    switch (address) {
    case 0: value = 0; break; /* cache disabled in this minimal controller */
    case 0x7e4: value = mcc->lower; break;
    case 0x7e8: value = mcc->upper; break;
    case 0x7ec: value = mcc->locked; break;
    default: break;
    }
    if (mcc->logged_accesses < 256) {
        qemu_log("PODIUM7 MCC read offset=%05" PRIx64 " size=%u value=%016" PRIx64 "\\n",
                 (uint64_t)address, size, value);
        mcc->logged_accesses++;
    }
    return value;
}
static void podium7_mcc_write(void *opaque, hwaddr address, uint64_t value,
                             unsigned size)
{
    Podium7MCC *mcc = opaque;
    if (mcc->locked) { return; }
    if (address == 0x7e4) { mcc->lower = value; }
    else if (address == 0x7e8) { mcc->upper = value; }
    else if (address == 0x7ec && (value & 1)) {
        uint64_t offset = (uint64_t)mcc->lower << 14;
        uint64_t end = ((uint64_t)mcc->upper + 1) << 14;
        if (end <= offset || end > mcc->machine->ram_size) {
            error_report("Podium7 MCC: invalid protected range; refusing lock");
            return;
        }
        memory_region_init_alias(&mcc->protected_alias, OBJECT(mcc->machine),
            "podium7-mcc-readonly", mcc->machine->ram, offset, end - offset);
        memory_region_set_readonly(&mcc->protected_alias, true);
        memory_region_add_subregion_overlap(mcc->memory, 0x40000000ULL + offset,
            &mcc->protected_alias, 1);
        mcc->locked = true;
    }
}
static const MemoryRegionOps podium7_mcc_ops = {
    .read = podium7_mcc_read, .write = podium7_mcc_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};
static void podium7_mcc_create(MachineState *machine, MemoryRegion *memory)
{
    Podium7MCC *mcc = g_new0(Podium7MCC, 1);
    mcc->machine = machine; mcc->memory = memory;
    memory_region_init_io(&mcc->io, OBJECT(machine), &podium7_mcc_ops, mcc,
        "podium7-mcc-one-plane", 0x300000);
    memory_region_add_subregion(memory, 0x200000000ULL, &mcc->io);
}

'''
    aic = '''
/* Minimal Apple AIC v1 research model for the T8010 bootstrap.
 * The n112 firmware's ipid-mask is 40 bytes, so model 320 implemented IRQs;
 * the Linux driver documents the broader AIC family's 896-IRQ capability.
 * Level device inputs and software events drive CPU0 IRQ; timers use FIQ.
 */
#define PODIUM7_AIC_IRQ_COUNT 320
typedef struct Podium7AIC {
    MemoryRegion io;
    uint32_t config;
    uint32_t target_cpu[1024];
    uint32_t irq_mask[32];
    uint32_t irq_state[32];
    uint32_t ipi_pending;
    uint32_t ipi_mask;
    unsigned logged_accesses;
} Podium7AIC;

static uint32_t podium7_aic_event(Podium7AIC *aic)
{
    unsigned irq;
    for (irq = 0; irq < PODIUM7_AIC_IRQ_COUNT; irq++) {
        uint32_t bit = 1U << (irq & 31);
        if ((aic->target_cpu[irq] & 1) &&
            (aic->irq_state[irq >> 5] & bit) &&
            !(aic->irq_mask[irq >> 5] & bit)) {
            aic->irq_mask[irq >> 5] |= bit; /* AIC auto-masks on event read */
            return 0x10000U | irq;          /* type=IRQ, die=0 */
        }
    }
    if ((aic->ipi_pending & 0x80000000U) && !(aic->ipi_mask & 0x80000000U)) {
        aic->ipi_mask |= 0x80000000U;
        return 0x40002U; /* self IPI */
    }
    if ((aic->ipi_pending & 1) && !(aic->ipi_mask & 1)) {
        aic->ipi_mask |= 1;
        return 0x40001U; /* other IPI */
    }
    return 0; /* spurious / no pending event */
}

static uint64_t podium7_aic_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7AIC *aic = opaque;
    uint32_t value = 0;
    if (address >= 0x5000 && address < 0x5080) {
        address = address - 0x5000 + 0x2000; /* explicit CPU 0 register view */
    }
    switch (address) {
    case 0x0004: value = PODIUM7_AIC_IRQ_COUNT; break; /* AIC_INFO */
    case 0x0010: value = aic->config; break;
    case 0x2000: value = 0; break; /* AIC_WHOAMI: CPU 0 */
    case 0x2004: value = podium7_aic_event(aic); break; /* AIC_EVENT */
    case 0x200c: value = aic->ipi_pending; break; /* AIC_IPI_ACK */
    default:
        if (address >= 0x3000 && address < 0x4000) {
            value = aic->target_cpu[(address - 0x3000) >> 2];
        } else if (address >= 0x4000 && address < 0x4080) {
            value = aic->irq_state[(address - 0x4000) >> 2];
        } else if (address >= 0x4100 && address < 0x4180) {
            value = aic->irq_mask[(address - 0x4100) >> 2];
        } else if (address >= 0x4180 && address < 0x4200) {
            value = aic->irq_mask[(address - 0x4180) >> 2];
        } else if (address >= 0x4200 && address < 0x4280) {
            value = aic->irq_state[(address - 0x4200) >> 2];
        }
        break;
    }
    if (aic->logged_accesses < 512) {
        qemu_log("PODIUM7 AIC1 read offset=%05" PRIx64 " value=%08" PRIx32 "\\n",
                 (uint64_t)address, value);
        aic->logged_accesses++;
    }
    return value;
}

static void podium7_aic_write(void *opaque, hwaddr address, uint64_t data,
                              unsigned size)
{
    Podium7AIC *aic = opaque;
    uint32_t value = (uint32_t)data;
    if (address >= 0x5000 && address < 0x5080) {
        address = address - 0x5000 + 0x2000;
    }
    switch (address) {
    case 0x0010: aic->config = value; break;
    case 0x2008: aic->ipi_pending |= value & 0x80000001U; break;
    case 0x200c: aic->ipi_pending &= ~(value & 0x80000001U); break;
    case 0x2024: aic->ipi_mask |= value & 0x80000001U; break;
    case 0x2028: aic->ipi_mask &= ~(value & 0x80000001U); break;
    default:
        if (address >= 0x3000 && address < 0x4000) {
            aic->target_cpu[(address - 0x3000) >> 2] = value;
        } else if (address >= 0x4000 && address < 0x4080) {
            aic->irq_state[(address - 0x4000) >> 2] |= value;
        } else if (address >= 0x4080 && address < 0x4100) {
            aic->irq_state[(address - 0x4080) >> 2] &= ~value;
        } else if (address >= 0x4100 && address < 0x4180) {
            aic->irq_mask[(address - 0x4100) >> 2] |= value;
        } else if (address >= 0x4180 && address < 0x4200) {
            aic->irq_mask[(address - 0x4180) >> 2] &= ~value;
        }
        break;
    }
    if (aic->logged_accesses < 512) {
        qemu_log("PODIUM7 AIC1 write offset=%05" PRIx64 " value=%08" PRIx32 "\\n",
                 (uint64_t)address, value);
        aic->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_aic_ops = {
    .read = podium7_aic_read, .write = podium7_aic_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_aic_create(MachineState *machine, MemoryRegion *memory)
{
    Podium7AIC *aic = g_new0(Podium7AIC, 1);
    memset(aic->irq_mask, 0xff, sizeof(aic->irq_mask));
    aic->ipi_mask = 0x80000001U;
    memory_region_init_io(&aic->io, OBJECT(machine), &podium7_aic_ops, aic,
                          "podium7-aic-v1-research", 0x100000);
    memory_region_add_subregion(memory, 0x20e100000ULL, &aic->io);
}

'''
    aic = aic.replace("    MemoryRegion io;", "    MemoryRegion io;\n    qemu_irq output;\n    uint32_t external_state[32];")
    start = aic.index("static uint32_t podium7_aic_event(")
    aic = aic[:start] + '''static Podium7AIC *podium7_aic_device;

static void podium7_aic_update(Podium7AIC *aic)
{
    bool pending = (aic->ipi_pending & ~aic->ipi_mask) != 0;
    for (unsigned irq = 0; irq < PODIUM7_AIC_IRQ_COUNT && !pending; irq++) {
        uint32_t bit = 1U << (irq & 31);
        pending = (aic->target_cpu[irq] & 1) &&
            ((aic->irq_state[irq >> 5] | aic->external_state[irq >> 5]) & bit) &&
            !(aic->irq_mask[irq >> 5] & bit);
    }
    qemu_set_irq(aic->output, pending);
}

static void podium7_aic_set_external(unsigned irq, bool level)
{
    Podium7AIC *aic = podium7_aic_device;
    if (!aic || irq >= PODIUM7_AIC_IRQ_COUNT) { return; }
    uint32_t bit = 1U << (irq & 31);
    if (level) { aic->external_state[irq >> 5] |= bit; }
    else { aic->external_state[irq >> 5] &= ~bit; }
    podium7_aic_update(aic);
}

''' + aic[start:]
    aic_view = "    if (address >= 0x5000 && address < 0x5080) {"
    if aic.count(aic_view) != 2:
        raise ValueError("AIC CPU-view source anchors changed")
    aic = aic.replace(aic_view,
        "    if (address >= 0x1000 && address < 0x1080) {\n"
        "        address = address - 0x1000 + 0x2000; /* Observed PMP CPU view. */\n"
        "    }\n" + aic_view)
    aic = aic.replace("(aic->irq_state[irq >> 5] & bit)",
                      "((aic->irq_state[irq >> 5] | aic->external_state[irq >> 5]) & bit)")
    aic = aic.replace("    if (aic->logged_accesses < 512) {",
                      "    podium7_aic_update(aic);\n    if (aic->logged_accesses < 512) {")
    aic = aic.replace("    memset(aic->irq_mask, 0xff, sizeof(aic->irq_mask));",
                      "    aic->output = podium7_aic_cpu_irq;\n"
                      "    podium7_aic_device = aic;\n"
                      "    memset(aic->irq_mask, 0xff, sizeof(aic->irq_mask));")
    wdt = '''
/* Minimal Apple SoC watchdog register bank for the T8010 bootstrap.
 * The Apple watchdog has WD0/WD1/WD2 counter, bite-time, and control registers.
 * Counters are intentionally inert in this bring-up model, so an incompletely
 * emulated watchdog cannot reset the guest while the rest of the SoC is absent.
 */
typedef struct Podium7WDT {
    MemoryRegion io;
    uint32_t regs[12];
    unsigned logged_accesses;
} Podium7WDT;

static uint64_t podium7_wdt_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7WDT *wdt = opaque;
    uint32_t value = 0;
    if (address <= 0x2c && !(address & 3) && address != 0x18 && address != 0x28) {
        value = wdt->regs[address >> 2];
    }
    if (wdt->logged_accesses < 256) {
        qemu_log("PODIUM7 WDT1 read offset=%02" PRIx64 " value=%08" PRIx32 "\\n",
                 (uint64_t)address, value);
        wdt->logged_accesses++;
    }
    return value;
}

static void podium7_wdt_write(void *opaque, hwaddr address, uint64_t data,
                              unsigned size)
{
    Podium7WDT *wdt = opaque;
    uint32_t value = (uint32_t)data;
    if (address <= 0x2c && !(address & 3) && address != 0x18 && address != 0x28) {
        if (address == 0x0c || address == 0x1c || address == 0x2c) {
            /* IRQ_STATUS is write-one-to-clear; only IRQ_EN and RESET_EN persist. */
            wdt->regs[address >> 2] = value & 0x5;
        } else {
            wdt->regs[address >> 2] = value;
        }
    }
    if (wdt->logged_accesses < 256) {
        qemu_log("PODIUM7 WDT1 write offset=%02" PRIx64 " value=%08" PRIx32 "\\n",
                 (uint64_t)address, value);
        wdt->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_wdt_ops = {
    .read = podium7_wdt_read, .write = podium7_wdt_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_wdt_create(MachineState *machine, MemoryRegion *memory)
{
    Podium7WDT *wdt = g_new0(Podium7WDT, 1);
    memory_region_init_io(&wdt->io, OBJECT(machine), &podium7_wdt_ops, wdt,
                          "podium7-apple-wdt-register-bank", 0x4000);
    memory_region_add_subregion(memory, 0x2102b0000ULL, &wdt->io);
}

'''
    gpio = '''
/* Minimal T8010 GPIO/pinmux/interrupt register banks.
 * Main GPIO has 208 pins at 0x20f100000; AOP GPIO has 42 pins at
 * 0x2100f0000. Pin registers are four-byte read/write values; interrupt
 * status registers are W1C. External pins and AIC delivery are not modeled.
 */
typedef struct Podium7GPIO {
    MemoryRegion io;
    uint64_t base;
    unsigned pin_count;
    unsigned bank_count;
    uint32_t pin_config[208];
    uint32_t irq_status[7][7];
    unsigned logged_accesses;
} Podium7GPIO;

static bool podium7_gpio_irq_index(Podium7GPIO *gpio, hwaddr address,
                                   unsigned *group, unsigned *bank)
{
    hwaddr offset;
    if (address < 0x800 || address > 0x998 || (address & 3)) {
        return false;
    }
    offset = address - 0x800;
    *group = offset / 0x40;
    *bank = (offset % 0x40) / 4;
    return *group < 7 && *bank < gpio->bank_count && (offset % 0x40) <= 0x18;
}

static uint64_t podium7_gpio_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7GPIO *gpio = opaque;
    uint32_t value = 0;
    unsigned group, bank;
    if (address < gpio->pin_count * 4 && !(address & 3)) {
        value = gpio->pin_config[address >> 2];
    } else if (podium7_gpio_irq_index(gpio, address, &group, &bank)) {
        value = gpio->irq_status[group][bank];
    }
    if (gpio->logged_accesses < 256) {
        qemu_log("PODIUM7 GPIO base=%016" PRIx64 " read offset=%03" PRIx64
                 " value=%08" PRIx32 "\\n", gpio->base, (uint64_t)address, value);
        gpio->logged_accesses++;
    }
    return value;
}

static void podium7_gpio_write(void *opaque, hwaddr address, uint64_t data,
                               unsigned size)
{
    Podium7GPIO *gpio = opaque;
    uint32_t value = (uint32_t)data;
    unsigned group, bank;
    if (address < gpio->pin_count * 4 && !(address & 3)) {
        gpio->pin_config[address >> 2] = value;
    } else if (podium7_gpio_irq_index(gpio, address, &group, &bank)) {
        gpio->irq_status[group][bank] &= ~value; /* write-one-to-clear */
    }
    if (gpio->logged_accesses < 256) {
        qemu_log("PODIUM7 GPIO base=%016" PRIx64 " write offset=%03" PRIx64
                 " value=%08" PRIx32 "\\n", gpio->base, (uint64_t)address, value);
        gpio->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_gpio_ops = {
    .read = podium7_gpio_read, .write = podium7_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_gpio_create(MachineState *machine, MemoryRegion *memory,
                                hwaddr base, unsigned pin_count, const char *name)
{
    Podium7GPIO *gpio = g_new0(Podium7GPIO, 1);
    gpio->base = base;
    gpio->pin_count = pin_count;
    gpio->bank_count = (pin_count + 31) / 32;
    memory_region_init_io(&gpio->io, OBJECT(machine), &podium7_gpio_ops, gpio,
                          name, 0x100000);
    memory_region_add_subregion(memory, base, &gpio->io);
}

'''
    # Original gpio-iic_scl/sda tuples identify these six main-bank pins.
    # Idle I2C lines have board pull-ups; GPIO output-low still overrides them.
    before = gpio.index("static uint64_t podium7_gpio_read(")
    gpio = gpio[:before] + '''static bool podium7_gpio_i2c_pin(Podium7GPIO *gpio, hwaddr address)
{
    unsigned pin = address >> 2;
    return gpio->base == 0x20f100000ULL && !(address & 3) &&
           (pin == 39 || pin == 40 || pin == 132 || pin == 133 ||
            pin == 196 || pin == 197);
}

''' + gpio[before:]
    gpio = gpio.replace("        value = gpio->pin_config[address >> 2];",
        "        value = gpio->pin_config[address >> 2];\n"
        "        if (podium7_gpio_i2c_pin(gpio, address) && ((value >> 1) & 7) != 1) {\n"
        "            value |= 1; /* Released/input line samples its external pull-up. */\n"
        "        }")
    gpio = gpio.replace("    unsigned logged_accesses;", "    unsigned logged_accesses;\n    unsigned bus_logged;")
    gpio = gpio.replace("if (gpio->logged_accesses < 256)",
        "if (gpio->logged_accesses < 256 || (podium7_gpio_i2c_pin(gpio, address) && gpio->bus_logged++ < 512))")
    aes = '''
/* Minimal T8010 AES register windows for kernel bootstrap.
 * AppleS8000AES maps both ranges as 0x4000-byte windows. This backing store
 * only prevents unimplemented-MMIO aborts; it does not perform AES operations,
 * model DMA, key slots, interrupts, or secure-enclave behavior.
 */
typedef struct Podium7AES {
    MemoryRegion io;
    uint64_t base;
    uint32_t registers[0x1000];
    unsigned logged_accesses;
} Podium7AES;

static uint64_t podium7_aes_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7AES *aes = opaque;
    uint32_t value = aes->registers[address >> 2];
    if (aes->logged_accesses < 256) {
        qemu_log("PODIUM7 AES base=%016" PRIx64 " read offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n",
                 aes->base, (uint64_t)address, value);
        aes->logged_accesses++;
    }
    return value;
}

static void podium7_aes_write(void *opaque, hwaddr address, uint64_t data,
                              unsigned size)
{
    Podium7AES *aes = opaque;
    uint32_t value = (uint32_t)data;
    aes->registers[address >> 2] = value;
    if (aes->logged_accesses < 256) {
        qemu_log("PODIUM7 AES base=%016" PRIx64 " write offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n",
                 aes->base, (uint64_t)address, value);
        aes->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_aes_ops = {
    .read = podium7_aes_read, .write = podium7_aes_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_aes_create(MachineState *machine, MemoryRegion *memory,
                               hwaddr base, const char *name)
{
    Podium7AES *aes = g_new0(Podium7AES, 1);
    aes->base = base;
    memory_region_init_io(&aes->io, OBJECT(machine), &podium7_aes_ops, aes,
                          name, 0x4000);
    memory_region_add_subregion(memory, base, &aes->io);
}

'''
    thermal = '''
/* Minimal T8010 thermal register windows for XNU bring-up.
 * sochot1 and tempsensor3-5 share 0x202f30000; tempsensor0-2 share 0x20e0bc000.
 * Zeroed, stateful banks allow register discovery only; they do not model
 * temperatures, sensor conversion, interrupts, or thermal policy.
 */
typedef struct Podium7Thermal {
    MemoryRegion io;
    uint64_t base;
    uint32_t registers[0x2000];
    unsigned logged_accesses;
} Podium7Thermal;

static uint64_t podium7_thermal_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7Thermal *thermal = opaque;
    uint32_t value = thermal->registers[address >> 2];
    if (thermal->logged_accesses < 256) {
        qemu_log("PODIUM7 THERMAL base=%016" PRIx64 " read offset=%04" PRIx64
                 " size=%u value=%08" PRIx32 "\\n",
                 thermal->base, (uint64_t)address, size, value);
        thermal->logged_accesses++;
    }
    return value;
}

static void podium7_thermal_write(void *opaque, hwaddr address, uint64_t data,
                                  unsigned size)
{
    Podium7Thermal *thermal = opaque;
    uint32_t value = (uint32_t)data;
    thermal->registers[address >> 2] = value;
    if (thermal->logged_accesses < 256) {
        qemu_log("PODIUM7 THERMAL base=%016" PRIx64 " write offset=%04" PRIx64
                 " size=%u value=%08" PRIx32 "\\n",
                 thermal->base, (uint64_t)address, size, value);
        thermal->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_thermal_ops = {
    .read = podium7_thermal_read, .write = podium7_thermal_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_thermal_bank_create(MachineState *machine, MemoryRegion *memory,
                                        hwaddr base, hwaddr size, const char *name)
{
    Podium7Thermal *thermal = g_new0(Podium7Thermal, 1);
    thermal->base = base;
    memory_region_init_io(&thermal->io, OBJECT(machine), &podium7_thermal_ops,
                          thermal, name, size);
    memory_region_add_subregion(memory, base, &thermal->io);
}

static void podium7_thermal_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_thermal_bank_create(machine, memory, 0x202f30000ULL, 0x8000,
                                "podium7-t8010-sochot-thermal");
    /* tempsensor0-2 share this 0x8000-byte window in the iPod9,1 DeviceTree. */
    podium7_thermal_bank_create(machine, memory, 0x20e0bc000ULL, 0x8000,
                                "podium7-t8010-temperature-sensors");
    /* sochot0's third range aliases 0x202f34000 within the first bank. */
    podium7_thermal_bank_create(machine, memory, 0x20e0c4000ULL, 0x1000,
                                "podium7-t8010-sochot0-control");
    podium7_thermal_bank_create(machine, memory, 0x20e0c0000ULL, 0x1000,
                                "podium7-t8010-sochot0-sensor");
    podium7_thermal_bank_create(machine, memory, 0x2102bc000ULL, 0x4000,
                                "podium7-t8010-sochot0-aop");
}

'''
    usbphy = '''
/* Minimal T8010 OTG PHY register windows for XNU bootstrap.
 * DeviceTree maps a 0x20-byte control range at 0x20c000030 and a 0x1000-byte
 * PHY range at 0x20e0d8000. Registers are zeroed and stateful only; clocks,
 * reset sequencing, USB signaling, DMA, and interrupts are not modeled.
 */
typedef struct Podium7USBPHYBank {
    MemoryRegion io;
    uint64_t base;
    uint32_t registers[0x400];
    unsigned logged_accesses;
} Podium7USBPHYBank;

static uint64_t podium7_usbphy_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7USBPHYBank *bank = opaque;
    uint32_t value = bank->registers[address >> 2];
    if (bank->logged_accesses < 256) {
        qemu_log("PODIUM7 USBPHY base=%016" PRIx64 " read offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n",
                 bank->base, (uint64_t)address, value);
        bank->logged_accesses++;
    }
    return value;
}

static void podium7_usbphy_write(void *opaque, hwaddr address, uint64_t data,
                                 unsigned size)
{
    Podium7USBPHYBank *bank = opaque;
    uint32_t value = (uint32_t)data;
    bank->registers[address >> 2] = value;
    if (bank->logged_accesses < 256) {
        qemu_log("PODIUM7 USBPHY base=%016" PRIx64 " write offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n",
                 bank->base, (uint64_t)address, value);
        bank->logged_accesses++;
    }
}

static const MemoryRegionOps podium7_usbphy_ops = {
    .read = podium7_usbphy_read, .write = podium7_usbphy_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_usbphy_bank_create(MachineState *machine, MemoryRegion *memory,
                                       hwaddr base, hwaddr size, const char *name)
{
    Podium7USBPHYBank *bank = g_new0(Podium7USBPHYBank, 1);
    bank->base = base;
    memory_region_init_io(&bank->io, OBJECT(machine), &podium7_usbphy_ops, bank,
                          name, size);
    memory_region_add_subregion(memory, base, &bank->io);
}

static void podium7_usbphy_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_usbphy_bank_create(machine, memory, 0x20c000030ULL, 0x20,
                               "podium7-t8010-otgphy-control");
    podium7_usbphy_bank_create(machine, memory, 0x20e0d8000ULL, 0x1000,
                               "podium7-t8010-otgphy-registers");
    /* Original n112ap usb-complex parent range, independently of OTG PHY. */
    podium7_usbphy_bank_create(machine, memory, 0x20c900000ULL, 0xa0,
                               "podium7-t8010-usb-complex-control");
}

'''
    # DWI shares simple 32-bit backing-store machinery but has a separate
    # aperture and diagnostic identity; bus transactions/IRQ delivery absent.
    dwi = usbphy.replace("USBPHY", "DWI").replace("usbphy", "dwi")
    dwi = dwi.replace("uint32_t registers[0x400]", "uint32_t registers[0x1000]")
    dwi = dwi.replace("Minimal T8010 OTG PHY register windows", "Minimal T8010 DWI register window")
    start = dwi.index("static void podium7_dwi_create(")
    dwi = dwi[:start] + '''static void podium7_dwi_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_dwi_bank_create(machine, memory, 0x20e200000ULL, 0x4000,
                            "podium7-t8010-dwi-control");
}
'''
    dwi = dwi.replace("DeviceTree maps a 0x20-byte control range at 0x20c000030 and a 0x1000-byte",
                      "DeviceTree maps a 0x4000-byte control range at 0x20e200000; the")
    dwi = dwi.replace("PHY range at 0x20e0d8000. Registers are zeroed and stateful only; clocks,",
                      "registers are zeroed and stateful only; clocks,")
    mca = dwi.replace("DWI", "MCA").replace("dwi", "mca")
    start = mca.index("static void podium7_mca_create(")
    mca = mca[:start] + '''static void podium7_mca_create(MachineState *machine, MemoryRegion *memory)
{
    static const hwaddr banks[] = { 0x20a0a0000ULL, 0x20a0a8000ULL, 0x20a0ac000ULL };
    static const hwaddr reset[] = { 0x20a002000ULL, 0x20a002008ULL, 0x20a00200cULL };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_mca_bank_create(machine, memory, banks[i], 0x4000,
                                "podium7-t8010-mca-control");
        podium7_mca_bank_create(machine, memory, reset[i], 4,
                                "podium7-t8010-mca-reset");
    }
}
'''
    # Original MCA reset routine writes bits 0/1 at +0xc, then polls each
    # until it clears. These are completion commands, not persistent flags.
    mca = mca.replace("    uint32_t value = (uint32_t)data;",
                      "    uint32_t value = (uint32_t)data;\n    if (address == 0xc) { value &= ~3U; }")
    mca = mca.replace("0x4000-byte control range at 0x20e200000",
                      "three 0x4000-byte MCA control ranges and three reset registers")
    mipi = dwi.replace("DWI", "MIPI-DSIM").replace("dwi", "mipi_dsim")
    # C identifiers cannot contain '-' from the diagnostic display name.
    mipi = mipi.replace("Podium7MIPI-DSIMBank", "Podium7MIPIDSIMBank")
    mipi = mipi.replace("uint32_t registers[0x1000]", "uint32_t *registers")
    mipi = mipi.replace("    bank->base = base;", "    bank->base = base;\n    bank->registers = g_new0(uint32_t, size / 4);")
    start = mipi.index("static void podium7_mipi_dsim_create(")
    mipi = mipi[:start] + '''static void podium7_mipi_dsim_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_mipi_dsim_bank_create(machine, memory, 0x206600000ULL, 0x100000,
                                 "podium7-t8010-mipi-dsim-control");
}
'''
    mipi = mipi.replace("0x4000-byte control range at 0x20e200000",
                        "0x100000-byte MIPI-DSIM range at 0x206600000")
    gfx = mipi.replace("MIPI-DSIM", "GFX").replace("mipi_dsim", "gfx")
    gfx = gfx.replace("Podium7MIPIDSIMBank", "Podium7GFXBank")
    start = gfx.index("static void podium7_gfx_create(")
    gfx = gfx[:start] + '''static void podium7_gfx_create(MachineState *machine, MemoryRegion *memory)
{
    /* sgx and gfx-kf share the second physical bank. Create it only once. */
    podium7_gfx_bank_create(machine, memory, 0x201000000ULL, 0x100000,
                            "podium7-t8010-sgx-control");
    podium7_gfx_bank_create(machine, memory, 0x201d00000ULL, 0x20000,
                            "podium7-t8010-sgx-gfx-shared-control");
    podium7_gfx_bank_create(machine, memory, 0x201d20000ULL, 0x10000,
                            "podium7-t8010-gfx-kf-control");
}
'''
    # The original startup writes 0x11 at shared +0x1000 and waits for bit 4
    # to clear. Complete this command, retaining bit 0 and other controls.
    gfx = gfx.replace("    uint32_t value = (uint32_t)data;",
                      "    uint32_t value = (uint32_t)data;\n    if (bank->base == 0x201d00000ULL && address == 0x1000) { value &= ~(1U << 4); }")
    gfx = gfx.replace("0x100000-byte GFX range at 0x206600000",
                      "original SGX/GFX control ranges; the shared bank is created once")
    clpc = mipi.replace("MIPI-DSIM", "CPU-CLPC").replace("mipi_dsim", "cpu_clpc")
    clpc = clpc.replace("Podium7MIPIDSIMBank", "Podium7CPUCLPCBank")
    start = clpc.index("static void podium7_cpu_clpc_create(")
    clpc = clpc[:start] + '''static void podium7_cpu_clpc_create(MachineState *machine, MemoryRegion *memory)
{
    static const hwaddr banks[] = {
        0x202010000ULL, 0x202030000ULL, 0x202110000ULL, 0x202130000ULL,
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_cpu_clpc_bank_create(machine, memory, banks[i], 0x10000,
                                     "podium7-t8010-cpu-clpc-control");
    }
}
'''
    clpc = clpc.replace("0x100000-byte CPU-CLPC range at 0x206600000",
                        "original four CPU-debug/CLPC register ranges")
    # Missing error-status apertures discovered after the CPU topology fix.
    error_handler = mipi.replace("MIPI-DSIM", "ERROR-HANDLER").replace("mipi_dsim", "error_handler")
    error_handler = error_handler.replace("Podium7MIPIDSIMBank", "Podium7ErrorHandlerBank")
    start = error_handler.index("static void podium7_error_handler_create(")
    error_handler = error_handler[:start] + '''static void podium7_error_handler_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x200d00000ULL, 0x13000 }, { 0x200d20000ULL, 0x1000 },
        { 0x200d90000ULL, 0x1000 }, { 0x200e20000ULL, 0x1000 },
        { 0x200e90000ULL, 0x1000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_error_handler_bank_create(machine, memory, banks[i].base,
            banks[i].size, "podium7-t8010-error-handler");
    }
}
'''
    # Observed original startup clears status with an all-one write at 0x10008.
    # No synthetic errors are raised; other control words remain latches.
    status_store = "bank->registers[address >> 2] = value;"
    if error_handler.count(status_store) != 1:
        raise ValueError("error-handler status-write source anchor changed")
    error_handler = error_handler.replace(status_store,
        "if (address == 0x10008) {\n"
        "        bank->registers[address >> 2] &= ~value;\n"
        "    } else {\n        bank->registers[address >> 2] = value;\n    }")
    # Original AppleA7IOP writes IRQ-mask controls at +0x4000/+0xc00.
    # Its mailbox helpers inspect empty/full bits 17/16 and exchange 64-bit
    # words at +0x4010/+0x4038. No SEP firmware or replies are synthesized.
    sep = mipi.replace("MIPI-DSIM", "SEP-MAILBOX").replace("mipi_dsim", "sep_mailbox")
    sep = sep.replace("Podium7MIPIDSIMBank", "Podium7SEPMailboxBank")
    sep = sep.replace("    unsigned logged_accesses;", "    unsigned logged_accesses;\n    bool inbox_pending;")
    sep = sep.replace("    uint32_t value = bank->registers[address >> 2];",
        "    uint32_t value = bank->registers[address >> 2];\n"
        "    if (address == 0x4008) {\n"
        "        value = bank->inbox_pending ? (1U << 16) : (1U << 17);\n"
        "    } else if (address == 0x4020) {\n"
        "        value = (value & 1U) | (1U << 17);\n"
        "    } else if (address == 0xb88) {\n"
        "        value |= 1U << 17; /* Observed ARM32 receive-control offset +8. */\n"
        "    }")
    sep_store = "bank->registers[address >> 2] = value;"
    if sep.count(sep_store) != 1:
        raise ValueError("SEP mailbox control-write source anchor changed")
    sep = sep.replace(sep_store,
        "if (address == 0x4008) {\n"
        "        /* Queue status is read-only. */\n"
        "    } else if (address == 0x4020) {\n"
        "        bank->registers[address >> 2] = value & 1U;\n"
        "    } else if (address == 0x4038 || address == 0x403c) {\n"
        "        /* No SEP peer: AP cannot manufacture an incoming reply. */\n"
        "    } else if (address == 0x4010 || address == 0x4014) {\n"
        "        if (!bank->inbox_pending) {\n"
        "            bank->registers[address >> 2] = value;\n"
        "            if (address == 0x4014) { bank->inbox_pending = true; }\n"
        "        }\n"
        "    } else {\n        bank->registers[address >> 2] = value;\n    }")
    sep = sep.replace(".valid = { .min_access_size = 4, .max_access_size = 4 },",
        ".valid = { .min_access_size = 4, .max_access_size = 8 },\n"
        "    .impl = { .min_access_size = 4, .max_access_size = 4 },")
    sep = "\n/* T8010 IOP mailbox apertures; PMP has audited bidirectional peer views. No synthetic replies. */\n" + sep[sep.index("typedef struct "):]
    # Audited PMP firmware object at VA 0x010144b0 uses MMIO base +0xb80:
    # rx-status +8 and rx-data +0x18. A distinct transmit object polls
    # +0xba0 and writes the real boot hello at +0xbb0/+0xbb4 (run 37988746111).
    # Keep all other IOPs passive; only PMP has these verified peer views.
    sep = sep.replace("    bool inbox_pending;",
        "    bool inbox_pending;\n    bool outbox_pending;\n"
        "    uint32_t outbox_low, outbox_high;")
    sep = sep.replace("        value = (value & 1U) | (1U << 17);",
        "        value = (value & 1U) | (bank->outbox_pending ? (1U << 16) : (1U << 17));")
    sep = sep.replace("        value |= 1U << 17; /* Observed ARM32 receive-control offset +8. */",
        "        value = (value & 0xffffU) | ((bank->base == 0x20e300000ULL && bank->inbox_pending) ? (1U << 16) : (1U << 17));")
    read_end = "    if (bank->logged_accesses < 256) {"
    read_peer = """    if (bank->base == 0x20e300000ULL) {
        if (address == 0x81c) {
            /* Original private IOP interrupt dispatch consumes type 4/source 0. */
            value = bank->inbox_pending && (bank->registers[0xb88 >> 2] & 1) ? 0x40000 : 0;
        }
        if (address == 0xba0) {
            value = (value & 0xffffU) | (bank->outbox_pending ? (1U << 16) : (1U << 17));
        } else if (address == 0xb98 || address == 0xb9c) {
            uint64_t message = bank->inbox_count ? bank->inbox_fifo[bank->inbox_head] : 0;
            value = address == 0xb98 ? (uint32_t)message : (uint32_t)(message >> 32);
            if (address == 0xb9c && bank->inbox_count) {
                bank->inbox_head = (bank->inbox_head + 1) % 16;
                bank->inbox_count--;
                bank->inbox_pending = bank->inbox_count != 0;
            }
        } else if (address == 0x4038 || address == 0x403c) {
            value = bank->outbox_pending ? (address == 0x4038 ? bank->outbox_low : bank->outbox_high) : 0;
            if (address == 0x403c) { bank->outbox_pending = false; }
        }
    }
"""
    # First occurrence belongs to read; the second is the write diagnostic.
    if sep.count(read_end) != 2:
        raise ValueError("PMP read diagnostic anchor changed")
    sep = sep.replace(read_end, read_peer + read_end, 1)
    sep = sep.replace("if (address == 0x4008) {\n        /* Queue status is read-only. */",
        "if (bank->base == 0x20e300000ULL && (address == 0xbb0 || address == 0xbb4)) {\n"
        "        if (!bank->outbox_pending) {\n"
        "            if (address == 0xbb0) { bank->outbox_low = value; }\n"
        "            else { bank->outbox_high = value; bank->outbox_pending = true; }\n"
        "        }\n"
        "    } else if (address == 0x4008) {\n        /* Queue status is read-only. */")
    sep = sep.replace("    bool inbox_pending;", "    qemu_irq pmp_receive_irq;\n    bool inbox_pending;")
    sep = sep.replace("    bool inbox_pending;",
        "    bool inbox_pending;\n    uint64_t inbox_fifo[16];\n    unsigned inbox_head, inbox_count;")
    sep = sep.replace("value = bank->inbox_pending ? (1U << 16) : (1U << 17);",
        "value = bank->base == 0x20e300000ULL ? (bank->inbox_count == 16 ? (1U << 16) : (bank->inbox_count == 0 ? (1U << 17) : 0)) : (bank->inbox_pending ? (1U << 16) : (1U << 17));")
    sep = sep.replace("((bank->base == 0x20e300000ULL && bank->inbox_pending) ? (1U << 16) : (1U << 17))",
        "(bank->base == 0x20e300000ULL ? (bank->inbox_count == 0 ? (1U << 17) : (bank->inbox_count == 16 ? (1U << 16) : 0)) : (1U << 17))")
    sep = sep.replace("typedef struct Podium7SEPMailboxBank {",
        "static ARMCPU *podium7_pmp_cpu;\n"
        "static void podium7_pmp_start(void);\n"
        "typedef struct Podium7SEPMailboxBank {")
    sep = sep.replace("    uint32_t value = bank->registers[address >> 2];",
        "    uint32_t value = bank->registers[address >> 2];\n"
        "    /* Private ARM32 SRAM alias is a research boot handoff. AP descriptor stays original. */\n"
        "    if (podium7_pmp_cpu && current_cpu == CPU(podium7_pmp_cpu) && bank->base == 0x20e300000ULL) {\n"
        "        if (address == 8) { value = 0x41000000; }\n"
        "        else if (address == 0x10) { value = 0; }\n"
        "    }")
    # Preserve the real driver's release trigger; do not start before SRAM copy.
    write_log = "    if (bank->logged_accesses < 256) {"
    last = sep.rindex(write_log)
    sep = sep[:last] + """    if (bank->base == 0x20e300000ULL && address == 0x38 && (value & 1)) {
        podium7_pmp_start();
    }
""" + sep[last:]
    sep = sep.replace("    return value;", """    if (bank->base == 0x20e300000ULL) {
        podium7_aic_set_external(170, bank->outbox_pending && (bank->registers[0x4020 >> 2] & 1));
        if (bank->pmp_receive_irq) {
            qemu_set_irq(bank->pmp_receive_irq, bank->inbox_pending && (bank->registers[0xb88 >> 2] & 1));
        }
    }
    return value;""")
    last = sep.rindex("    if (bank->logged_accesses < 256) {")
    sep = sep[:last] + """    if (bank->base == 0x20e300000ULL) {
        podium7_aic_set_external(170, bank->outbox_pending && (bank->registers[0x4020 >> 2] & 1));
        if (bank->pmp_receive_irq) {
            qemu_set_irq(bank->pmp_receive_irq, bank->inbox_pending && (bank->registers[0xb88 >> 2] & 1));
        }
    }
""" + sep[last:]
    sep = sep.replace("    } else if (address == 0x4010 || address == 0x4014) {",
        """    } else if (bank->base == 0x20e300000ULL && (address == 0x4010 || address == 0x4014)) {
        /* Bounded research FIFO: original AP sends endpoint-start bursts.
         * Stage the low word independently; publish only on the high word.
         * Exact hardware depth is not yet established, so capacity 16 is explicit. */
        if (address == 0x4010) {
            /* Staging must survive a consumer freeing space between low/high writes. */
            bank->registers[address >> 2] = value;
        } else if (bank->inbox_count < 16) {
            bank->registers[address >> 2] = value;
            unsigned tail = (bank->inbox_head + bank->inbox_count) % 16;
            bank->inbox_fifo[tail] = ((uint64_t)value << 32) | bank->registers[0x4010 >> 2];
            bank->inbox_count++;
            bank->inbox_pending = true;
        }
    } else if (address == 0x4010 || address == 0x4014) {""")
    sep = sep.replace("static void podium7_sep_mailbox_bank_create(",
                      "static Podium7SEPMailboxBank *podium7_sep_mailbox_bank_create(")
    bank_end = "    memory_region_add_subregion(memory, base, &bank->io);\n}"
    if sep.count(bank_end) != 1:
        raise ValueError("PMP mailbox factory source anchor changed")
    sep = sep.replace(bank_end, "    memory_region_add_subregion(memory, base, &bank->io);\n    return bank;\n}")
    start = sep.index("static void podium7_sep_mailbox_create(")
    sep = sep[:start] + '''static void podium7_sep_mailbox_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_sep_mailbox_bank_create(machine, memory, 0x20da00000ULL, 0x10000,
                                    "podium7-t8010-sep-mailbox");
    /* Same original AppleA7IOP helper, distinct SIO register aperture. */
    podium7_sep_mailbox_bank_create(machine, memory, 0x20ae00000ULL, 0x10000,
                                    "podium7-t8010-sio-mailbox");
    Podium7SEPMailboxBank *pmp_bank = podium7_sep_mailbox_bank_create(
        machine, memory, 0x20e300000ULL, 0x20000, "podium7-t8010-pmp-mailbox");
    podium7_sep_mailbox_bank_create(machine, memory, 0x210800000ULL, 0x1c000,
                                    "podium7-t8010-aop-mailbox");
    /* Original AOP reg[1] is a separate 640-KiB firmware SRAM window. */
    MemoryRegion *aop_sram = g_new0(MemoryRegion, 1);
    memory_region_init_ram(aop_sram, NULL, "podium7-t8010-aop-sram", 0xa0000, &error_fatal);
    memory_region_add_subregion(memory, 0x210e00000ULL, aop_sram);
    /* Original PMP reg[1] is firmware SRAM, not mailbox control registers.
     * RTBuddy copies real t8010pmp words here before +0x38 release. */
    MemoryRegion *pmp_sram = g_new0(MemoryRegion, 1);
    memory_region_init_ram(pmp_sram, NULL, "podium7-t8010-pmp-sram",
                           0x20000, &error_fatal);
    memory_region_add_subregion(memory, 0x20e500000ULL, pmp_sram);
    if (blk_by_name("podium7-pmp-integrated")) {
        /* Explicit research core, not an AP/SMP CPU and not the exact PMP ISA model.
         * Share the original firmware SRAM, with a low physical alias private to
         * ARM32. Its MMU subsequently translates peripheral access above 4 GiB. */
        MemoryRegion *private_memory = g_new0(MemoryRegion, 1);
        MemoryRegion *sram_alias = g_new0(MemoryRegion, 1);
        MemoryRegion *fallback = g_new0(MemoryRegion, 1);
        memory_region_init(private_memory, OBJECT(machine), "podium7-pmp-private-memory", UINT64_MAX);
        memory_region_init_alias(fallback, OBJECT(machine), "podium7-pmp-system-view",
                                 memory, 0, UINT64_MAX);
        memory_region_add_subregion_overlap(private_memory, 0, fallback, -1);
        memory_region_init_alias(sram_alias, OBJECT(machine), "podium7-pmp-low-sram",
                                 pmp_sram, 0, 0x20000);
        memory_region_add_subregion(private_memory, 0x41000000, sram_alias);
        Object *core = object_new("cortex-a7-arm-cpu");
        object_property_set_int(core, "mp-affinity", 0xff00, &error_fatal);
        object_property_set_bool(core, "has_el3", false, &error_fatal);
        object_property_set_bool(core, "has_el2", false, &error_fatal);
        object_property_set_bool(core, "start-powered-off", true, &error_fatal);
        object_property_set_int(core, "cntfrq", 24000000, &error_fatal);
        object_property_set_link(core, "memory", OBJECT(private_memory), &error_fatal);
        qdev_realize(DEVICE(core), NULL, &error_fatal);
        podium7_pmp_cpu = ARM_CPU(core);
        /* Local interrupt-controller state must not overwrite AP IRQ masks. */
        Podium7AIC *local_aic = g_new0(Podium7AIC, 1);
        Podium7IRQOr *route = g_new0(Podium7IRQOr, 1);
        route->output = qdev_get_gpio_in(DEVICE(core), ARM_CPU_IRQ);
        local_aic->output = qemu_allocate_irq(podium7_irq_or_set, route, 0);
        pmp_bank->pmp_receive_irq = qemu_allocate_irq(podium7_irq_or_set, route, 1);
        memset(local_aic->irq_mask, 0xff, sizeof(local_aic->irq_mask));
        local_aic->ipi_mask = 0x80000001U;
        memory_region_init_io(&local_aic->io, OBJECT(machine), &podium7_aic_ops,
                              local_aic, "podium7-pmp-private-aic", 0x100000);
        memory_region_add_subregion(private_memory, 0x20e100000ULL, &local_aic->io);
        qemu_log("PODIUM7 PMP integrated ARM32 core realized; no fabricated handshake\\n");
    }
    (void)pmp_bank;
}
static void podium7_pmp_start(void)
{
    if (!podium7_pmp_cpu) { return; }
    int result = arm_set_cpu_on(0xff00, 0x41000000, 0, 1, false);
    qemu_log("PODIUM7 PMP firmware release result=%d\\n", result);
}
'''
    # Polling must not exhaust evidence for actual message delivery. Keep a
    # separate bounded budget for data-port accesses (not status loops).
    sep = sep.replace("    unsigned logged_accesses;", "    unsigned logged_accesses;\n    unsigned logged_messages;")
    sep = sep.replace("if (bank->logged_accesses < 256) {",
        "if (bank->logged_accesses < 256 || (bank->base == 0x20e300000ULL && bank->logged_messages < 4096 && (address == 0xb98 || address == 0xb9c || address == 0xbb0 || address == 0xbb4 || address == 0x4010 || address == 0x4014 || address == 0x4038 || address == 0x403c))) {")
    sep = sep.replace("bank->logged_accesses++;",
        "bank->logged_accesses++;\n        if (address == 0xb98 || address == 0xb9c || address == 0xbb0 || address == 0xbb4 || address == 0x4010 || address == 0x4014 || address == 0x4038 || address == 0x403c) { bank->logged_messages++; }")
    # Next original-XNU data abort is AppleJPEGDriver's reset write at +8.
    # The n112ap DT has two 16-KiB JPEG engines adjacent to their DARTs.
    # Discovery/reset controls only: no encode/decode DMA or completion IRQ.
    jpeg = mipi.replace("MIPI-DSIM", "JPEG").replace("mipi_dsim", "jpeg")
    jpeg = jpeg.replace("Podium7MIPIDSIMBank", "Podium7JPEGBank")
    start = jpeg.index("static void podium7_jpeg_create(")
    jpeg = jpeg[:start] + '''static void podium7_jpeg_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_jpeg_bank_create(machine, memory, 0x207b00000ULL, 0x4000,
                             "podium7-t8010-jpeg0-control");
    podium7_jpeg_bank_create(machine, memory, 0x207b08000ULL, 0x4000,
                             "podium7-t8010-jpeg1-control");
}
'''
    jpeg = "\n/* Original JPEG reset/discovery apertures; codec/DMA absent. */\n" + jpeg[jpeg.index("typedef struct "):]
    # Original scaler0 reset writes 1 then 0 at 0x207900000 (run 38029948174).
    # Only discovery/control storage: no pixels, DMA or completion interrupts.
    scaler = mipi.replace("MIPI-DSIM", "SCALER").replace("mipi_dsim", "scaler")
    scaler = scaler.replace("Podium7MIPIDSIMBank", "Podium7ScalerBank")
    scaler = scaler.replace(".valid = { .min_access_size = 4, .max_access_size = 4 },",
        ".valid = { .min_access_size = 4, .max_access_size = 8 },\n"
        "    .impl = { .min_access_size = 4, .max_access_size = 4 },")
    start = scaler.index("static void podium7_scaler_create(")
    scaler = scaler[:start] + '''static void podium7_scaler_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_scaler_bank_create(machine, memory, 0x207900000ULL, 0x4000,
                               "podium7-t8010-scaler0-control");
    podium7_scaler_bank_create(machine, memory, 0x20790a000ULL, 0x200,
                               "podium7-t8010-scaler0-secondary-control");
}
'''
    scaler = "\n/* Original scaler0 control banks; pixel processing/DMA absent. */\n" + scaler[scaler.index("typedef struct "):]
    # Original VXD power/reset control read +4 faults in run 38030307496.
    # Exact n112ap DT windows; no video decode, DMA or synthetic IRQ.
    vxd = scaler.replace("SCALER", "VXD").replace("scaler", "vxd").replace("Podium7ScalerBank", "Podium7VXDBank")
    start = vxd.index("static void podium7_vxd_create(")
    vxd = vxd[:start] + '''static void podium7_vxd_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_vxd_bank_create(machine, memory, 0x208100000ULL, 0x30000,
                            "podium7-t8010-vxd-primary-control");
    podium7_vxd_bank_create(machine, memory, 0x208130000ULL, 0x1000,
                            "podium7-t8010-vxd-power-control");
}
'''
    # Original AppleD5500 SRAM-size formula at 0xfffffff006461738 derives
    # capacity from +0x500. Zero yields no firmware descriptor then a NULL
    # dereference. Explicit research geometry: one 64-KiB bank, large enough
    # for the original embedded 0xa1a0-byte image. Exact ASIC geometry unknown.
    vxd = vxd.replace("    uint32_t value = bank->registers[address >> 2];",
        "    uint32_t value = bank->registers[address >> 2];\n"
        "    if (bank->base == 0x208100000ULL && address == 0x500) { value = 0x0e000100; }")
    vxd = vxd.replace("bank->registers[address >> 2] = value;",
        "if (!(bank->base == 0x208100000ULL && address == 0x500)) { bank->registers[address >> 2] = value; }")
    # Original ISP reads revision at +0xa0000 (run 38030604802).
    # One exact 0x140000 n112ap register window; no camera firmware or frames.
    isp = scaler.replace("SCALER", "ISP").replace("scaler", "isp").replace("Podium7ScalerBank", "Podium7ISPBank")
    start = isp.index("static void podium7_isp_create(")
    isp = isp[:start] + '''static void podium7_isp_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_isp_bank_create(machine, memory, 0x205b00000ULL, 0x140000,
                            "podium7-t8010-isp-control");
}
'''
    # Original disp0 read +4 faults in run 38030933219. Exact DT control
    # windows only; no framebuffer scanout or fabricated display IRQ.
    display = scaler.replace("SCALER", "DISPLAY").replace("scaler", "display").replace("Podium7ScalerBank", "Podium7DisplayBank")
    start = display.index("static void podium7_display_create(")
    display = display[:start] + '''static void podium7_display_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x206200000ULL, 0x9000 },
        { 0x20620c000ULL, 0x4000 },
        { 0x206400000ULL, 0x4000 },
        { 0x206440000ULL, 0x4000 },
        { 0x206480000ULL, 0x8000 },
        { 0x2064c0000ULL, 0x8000 },
        { 0x206500000ULL, 0x4000 },
        { 0x206540000ULL, 0x4000 },
        { 0x2067c0000ULL, 0x4000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_display_bank_create(machine, memory, banks[i].base, banks[i].size,
                                    "podium7-t8010-disp0-control");
    }
}
'''
    # Original Samsung SPI starts by disabling +0/+0xc and setting +8.
    # Discovery/control storage only; no codec/touch traffic or fake IRQs.
    spi = mipi.replace("MIPI-DSIM", "SPI").replace("mipi_dsim", "spi")
    spi = spi.replace("Podium7MIPIDSIMBank", "Podium7SPIBank")
    spi = "\n/* T8010 SPI discovery controls; transfers and slave devices absent. */\n" + spi[spi.index("typedef struct "):]
    start = spi.index("static void podium7_spi_create(")
    spi = spi[:start] + '''static void podium7_spi_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_spi_bank_create(machine, memory, 0x20a084000ULL, 0x4000,
                            "podium7-t8010-spi1-control");
    podium7_spi_bank_create(machine, memory, 0x20a088000ULL, 0x4000,
                            "podium7-t8010-spi2-control");
}
'''
    # Original I2C startup configures divider/timing/control at these banks.
    # Bus packets, slave acknowledgments, FIFO completions and IRQs absent.
    i2c = mipi.replace("MIPI-DSIM", "I2C").replace("mipi_dsim", "i2c")
    i2c = i2c.replace("Podium7MIPIDSIMBank", "Podium7I2CBank")
    i2c = "\n/* T8010 I2C empty-bus packet engine with W1C status; no slave ACKs. */\n" + i2c[i2c.index("typedef struct "):]
    i2c = i2c.replace("    unsigned logged_accesses;", "    unsigned logged_accesses;\n    bool transfer_active;")
    i2c = i2c.replace("    uint32_t value = bank->registers[address >> 2];",
        "    uint32_t value = bank->registers[address >> 2];\n"
        "    if (address == 0x14) {\n"
        "        value |= 1U << 16; /* TX FIFO drained. */\n"
        "        if (bank->transfer_active) { value |= 1U << 28; }\n"
        "    } else if (address == 4) { value = 1U << 8; /* RX empty. */ }")
    i2c_store = "bank->registers[address >> 2] = value;"
    if i2c.count(i2c_store) != 1:
        raise ValueError("I2C control-write source anchor changed")
    i2c = i2c.replace(i2c_store,
        "if (address == 0x14) {\n"
        "        /* W1C events; TX-empty and transfer-active are derived. */\n"
        "        bank->registers[address >> 2] &= ~(value & 0x0ae00040U);\n"
        "    } else if (address == 0) {\n"
        "        if (value & (1U << 8)) {\n"
        "            bank->transfer_active = true;\n"
        "            bank->registers[0x14 >> 2] |= 1U << 21; /* No slave: NACK. */\n"
        "        }\n"
        "        if (value & (1U << 9)) {\n"
        "            bank->transfer_active = false;\n"
        "            bank->registers[0x14 >> 2] |= 1U << 27; /* STOP completed. */\n"
        "        }\n"
        "    } else if (address == 4 || address == 8 || address == 0xc) {\n"
        "        /* RX/counts are hardware state, not writable contents. */\n"
        "    } else if (address == 0x1c) {\n"
        "        if (value & 0x700U) { bank->transfer_active = false; }\n"
        "        bank->registers[address >> 2] = value & ~0x700U;\n"
        "    } else {\n        bank->registers[address >> 2] = value;\n    }")
    write_end = "    if (bank->logged_accesses < 256) {"
    write_start = i2c.index("static void podium7_i2c_write(")
    notify = i2c.index(write_end, write_start)
    i2c = i2c[:notify] + '''    bool irq_enabled = (bank->registers[0x10 >> 2] & 0x80000000U) != 0;
    bool pending = (bank->registers[0x14 >> 2] & bank->registers[0x18 >> 2]) != 0;
    podium7_aic_set_external(232 + (bank->base - 0x20a110000ULL) / 0x1000,
                            irq_enabled && pending);
''' + i2c[notify:]
    start = i2c.index("static void podium7_i2c_create(")
    i2c = i2c[:start] + '''static void podium7_i2c_create(MachineState *machine, MemoryRegion *memory)
{
    for (unsigned i = 0; i < 3; i++) {
        podium7_i2c_bank_create(machine, memory, 0x20a110000ULL + i * 0x1000,
                                0x1000, "podium7-t8010-i2c-control");
    }
}
'''
    pmp_system = mipi.replace("MIPI-DSIM", "PMP-SYSTEM").replace("mipi_dsim", "pmp_system")
    pmp_system = pmp_system.replace("Podium7MIPIDSIMBank", "Podium7PMPSystemBank")
    pmp_system = "\n/* PMP reg[2] system controls. No coprocessor execution or ready state. */\n" + pmp_system[pmp_system.index("typedef struct "):]
    start = pmp_system.index("static void podium7_pmp_system_create(")
    pmp_system = pmp_system[:start] + '''static void podium7_pmp_system_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_pmp_system_bank_create(machine, memory, 0x20e400000ULL, 0x10000,
                                   "podium7-t8010-pmp-system-control");
}
'''
    dart = mipi.replace("MIPI-DSIM", "DART").replace("mipi_dsim", "dart")
    dart = dart.replace("Podium7MIPIDSIMBank", "Podium7DARTBank")
    dart = "\n/* T8010 DART discovery/configuration banks. DMA translation is absent. */\n" + dart[dart.index("typedef struct "):]
    start = dart.index("static void podium7_dart_create(")
    dart = dart[:start] + '''static void podium7_dart_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x206304000ULL, 0x4000 }, { 0x206300000ULL, 0x4000 },
        { 0x207908000ULL, 0x2000 }, { 0x207904000ULL, 0x4000 },
        { 0x207b04000ULL, 0x4000 }, { 0x207b0c000ULL, 0x4000 },
        { 0x205b28000ULL, 0x4000 }, { 0x205b2c000ULL, 0x4000 },
        { 0x207c30000ULL, 0x4000 }, { 0x207c20000ULL, 0x4000 },
        { 0x601008000ULL, 0x4000 }, { 0x604008000ULL, 0x4000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_dart_bank_create(machine, memory, banks[i].base, banks[i].size,
                                 "podium7-t8010-dart-control");
    }
}
'''
    pcie = mipi.replace("MIPI-DSIM", "PCIE").replace("mipi_dsim", "pcie")
    pcie = pcie.replace("Podium7MIPIDSIMBank", "Podium7PCIeBank")
    pcie = "\n/* T8010 PCIe discovery controls; no endpoint, PHY-ready or link-up synthesis. */\n" + pcie[pcie.index("typedef struct "):]
    start = pcie.index("static void podium7_pcie_create(")
    pcie = pcie[:start] + '''static uint64_t podium7_pcie_config_read(void *opaque, hwaddr address, unsigned size)
{
    /* No endpoint is attached: PCI configuration reads return all ones. */
    return size == 4 ? 0xffffffffULL : ((1ULL << (size * 8)) - 1);
}

static void podium7_pcie_config_write(void *opaque, hwaddr address,
                                      uint64_t data, unsigned size)
{
    /* Writes to a nonexistent PCI function have no effect. */
}

static const MemoryRegionOps podium7_pcie_config_ops = {
    .read = podium7_pcie_config_read, .write = podium7_pcie_config_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 4 },
    .impl = { .min_access_size = 1, .max_access_size = 4 },
};

static void podium7_pcie_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x601000000ULL, 0x4000 }, { 0x601004000ULL, 0x4000 },
        { 0x602000000ULL, 0x4000 }, { 0x602004000ULL, 0x4000 },
        { 0x603000000ULL, 0x4000 }, { 0x603004000ULL, 0x4000 },
        { 0x604000000ULL, 0x4000 }, { 0x604004000ULL, 0x4000 },
        { 0x600000000ULL, 0x8000 }, { 0x600008000ULL, 0x4000 },
        { 0x6000a0000ULL, 0x4000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        podium7_pcie_bank_create(machine, memory, banks[i].base, banks[i].size,
                                 "podium7-t8010-pcie-control");
    }
    MemoryRegion *config = g_new0(MemoryRegion, 1);
    memory_region_init_io(config, OBJECT(machine), &podium7_pcie_config_ops,
        NULL, "podium7-t8010-pcie-empty-config", 0x1000000);
    memory_region_add_subregion(memory, 0x610000000ULL, config);
}
'''
    aop_system = mipi.replace("MIPI-DSIM", "AOP-SYSTEM").replace("mipi_dsim", "aop_system")
    aop_system = aop_system.replace("Podium7MIPIDSIMBank", "Podium7AOPSystemBank")
    aop_system = "\n/* Original AOP reg[2] system controls; no firmware execution. */\n" + aop_system[aop_system.index("typedef struct "):]
    start = aop_system.index("static void podium7_aop_system_create(")
    aop_system = aop_system[:start] + '''static uint64_t podium7_aop_counter_read(void *opaque, hwaddr address, unsigned size)
{
    uint64_t ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    uint64_t ticks = (ns / 1000000000ULL) * 32768ULL +
                     ((ns % 1000000000ULL) * 32768ULL) / 1000000000ULL;
    return address == 0 ? (uint32_t)ticks : (uint32_t)(ticks >> 32);
}
static void podium7_aop_counter_write(void *opaque, hwaddr address,
                                      uint64_t data, unsigned size)
{
    /* Free-running read-only AOP timebase. */
}
static const MemoryRegionOps podium7_aop_counter_ops = {
    .read = podium7_aop_counter_read, .write = podium7_aop_counter_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};
static void podium7_aop_system_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_aop_system_bank_create(machine, memory, 0x210000500ULL, 0x100,
                                   "podium7-t8010-aop-system-control");
    MemoryRegion *counter = g_new0(MemoryRegion, 1);
    memory_region_init_io(counter, OBJECT(machine), &podium7_aop_counter_ops,
        NULL, "podium7-t8010-aop-counter-32768hz", 8);
    memory_region_add_subregion(memory, 0x210000408ULL, counter);
}
'''
    i2s_switch = '''
/* n112ap exposes 4-KiB main/AOP I2S banks and a 32-bit routing register.
 * Retain guest routing writes for bootstrap. No PCM/DMA/audio output yet.
 */
typedef struct Podium7I2SSwitch {
    MemoryRegion io;
    uint64_t base;
    uint32_t registers[0x400];
    unsigned logged_accesses;
} Podium7I2SSwitch;

static uint64_t podium7_i2s_switch_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7I2SSwitch *s = opaque;
    uint32_t value = s->registers[address >> 2];
    if (s->logged_accesses++ < 64) {
        qemu_log("PODIUM7 I2S-SWITCH base=%016" PRIx64 " read offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n", s->base, (uint64_t)address, value);
    }
    return value;
}

static void podium7_i2s_switch_write(void *opaque, hwaddr address, uint64_t value,
                                     unsigned size)
{
    Podium7I2SSwitch *s = opaque;
    s->registers[address >> 2] = (uint32_t)value;
    if (s->logged_accesses++ < 64) {
        qemu_log("PODIUM7 I2S-SWITCH base=%016" PRIx64 " write offset=%04" PRIx64
                 " value=%08" PRIx32 "\\n", s->base, (uint64_t)address, (uint32_t)value);
    }
}

static const MemoryRegionOps podium7_i2s_switch_ops = {
    .read = podium7_i2s_switch_read, .write = podium7_i2s_switch_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_i2s_switch_bank_create(MachineState *machine,
                                          MemoryRegion *memory, hwaddr base,
                                          hwaddr size, const char *name)
{
    Podium7I2SSwitch *s = g_new0(Podium7I2SSwitch, 1);
    s->base = base;
    memory_region_init_io(&s->io, OBJECT(machine), &podium7_i2s_switch_ops,
                          s, name, size);
    memory_region_add_subregion(memory, base, &s->io);
}

static void podium7_i2s_switch_create(MachineState *machine, MemoryRegion *memory)
{
    podium7_i2s_switch_bank_create(machine, memory, 0x20a004000ULL, 0x1000,
                                   "podium7-t8010-main-i2s-bank");
    podium7_i2s_switch_bank_create(machine, memory, 0x210540000ULL, 0x1000,
                                   "podium7-t8010-aop-i2s-bank");
    podium7_i2s_switch_bank_create(machine, memory, 0x210000600ULL, 4,
                                   "podium7-t8010-aop-i2s-routing");
}

'''

    pmgr_bridges = r'''
/* n112ap PMGR reg[10..23], selected by bridge-reg-index=10, #bridges=14.
 * Register backing only. No fabricated iBoot settings or power transitions.
 */
typedef struct Podium7PMGRBridge {
    MemoryRegion io;
    uint32_t *registers;
    uint64_t base;
    unsigned index;
    unsigned logged_accesses;
} Podium7PMGRBridge;

static uint64_t podium7_pmgr_bridge_read(void *opaque, hwaddr address,
                                         unsigned size)
{
    Podium7PMGRBridge *s = opaque;
    uint32_t value = s->registers[address >> 2];
    if (s->logged_accesses++ < 32) {
        qemu_log("PODIUM7 PMGR-BRIDGE index=%u base=%016" PRIx64
                 " read offset=%04" PRIx64 " value=%08" PRIx32 "\n",
                 s->index, s->base, (uint64_t)address, value);
    }
    return value;
}

static void podium7_pmgr_bridge_write(void *opaque, hwaddr address,
                                       uint64_t value, unsigned size)
{
    Podium7PMGRBridge *s = opaque;
    s->registers[address >> 2] = (uint32_t)value;
    if (s->logged_accesses++ < 32) {
        qemu_log("PODIUM7 PMGR-BRIDGE index=%u base=%016" PRIx64
                 " write offset=%04" PRIx64 " value=%08" PRIx32 "\n",
                 s->index, s->base, (uint64_t)address, (uint32_t)value);
    }
}

static const MemoryRegionOps podium7_pmgr_bridge_ops = {
    .read = podium7_pmgr_bridge_read, .write = podium7_pmgr_bridge_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8, .unaligned = false },
    .impl = { .min_access_size = 4, .max_access_size = 4, .unaligned = false },
};

static void podium7_pmgr_bridges_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x207000000ULL, 0x1000 }, { 0x207800000ULL, 0x9000 },
        { 0x207a00000ULL, 0x9000 }, { 0x207c00000ULL, 0x9000 },
        { 0x208000000ULL, 0x5000 }, { 0x205b00000ULL, 0x11000 },
        { 0x206000000ULL, 0x1000 }, { 0x206100000ULL, 0x9000 },
        { 0x201f00000ULL, 0x9000 }, { 0x201f80000ULL, 0x1000 },
        { 0x20cb00000ULL, 0x1000 }, { 0x600010000ULL, 0x5000 },
        { 0x208080000ULL, 0x1000 }, { 0x20f000000ULL, 0x9000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        Podium7PMGRBridge *s = g_new0(Podium7PMGRBridge, 1);
        s->base = banks[i].base;
        s->index = i;
        s->registers = g_new0(uint32_t, banks[i].size / 4);
        memory_region_init_io(&s->io, OBJECT(machine), &podium7_pmgr_bridge_ops,
                              s, "podium7-t8010-pmgr-bridge", banks[i].size);
        memory_region_add_subregion(memory, s->base, &s->io);
    }
}

'''


    pmgr_power = r'''
/* n112ap ps-regs triples select power-register ranges. The third field is
 * not a validity bitmap: original XNU requests offset 0x30 in bank 0x200
 * even though the corresponding bit in that field is clear.
 * A deterministic virtual transition acknowledges DESIRED[3:0] in ACTUAL[7:4].
 * No analog voltages, parent dependency timing, or DVFS is simulated here.
 */
typedef struct Podium7PMGRPower {
    MemoryRegion io;
    uint32_t registers[64];
    uint64_t base;
    unsigned logged_accesses;
} Podium7PMGRPower;

static uint64_t podium7_pmgr_power_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7PMGRPower *s = opaque;
    uint32_t value = s->registers[address >> 2];
    if (s->logged_accesses++ < 64) {
        qemu_log("PODIUM7 PMGR-POWER base=%016" PRIx64 " read offset=%04" PRIx64
                 " value=%08" PRIx32 "\n", s->base, (uint64_t)address, value);
    }
    return value;
}

static void podium7_pmgr_power_write(void *opaque, hwaddr address,
                                      uint64_t value, unsigned size)
{
    Podium7PMGRPower *s = opaque;
    uint32_t state = value;
    if (!(address & 7)) {
        state = (state & ~0xf0U) | ((state & 0xfU) << 4);
    }
    s->registers[address >> 2] = state;
    if (s->logged_accesses++ < 64) {
        qemu_log("PODIUM7 PMGR-POWER base=%016" PRIx64 " write offset=%04" PRIx64
                 " value=%08" PRIx32 " state=%08" PRIx32 "\n",
                 s->base, (uint64_t)address, (uint32_t)value, state);
    }
}

static const MemoryRegionOps podium7_pmgr_power_ops = {
    .read = podium7_pmgr_power_read, .write = podium7_pmgr_power_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4, .unaligned = false },
    .impl = { .min_access_size = 4, .max_access_size = 4, .unaligned = false },
};


/* Backing store for DeviceTree PMGR control apertures reg[0..9]. Specific power,
 * thermal and AES models retain higher priority and their own semantics.
 * Other control registers are latches only, with accesses explicitly logged.
 */
typedef struct Podium7PMGRRaw {
    MemoryRegion io;
    uint32_t *registers;
    uint64_t base;
    unsigned logged_accesses;
} Podium7PMGRRaw;

static uint64_t podium7_pmgr_raw_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7PMGRRaw *s = opaque;
    uint32_t value = s->registers[address >> 2];
    if (s->logged_accesses++ < 128) {
        qemu_log("PODIUM7 PMGR-RAW base=%016" PRIx64 " read offset=%06" PRIx64
                 " value=%08" PRIx32 "\n", s->base, (uint64_t)address, value);
    }
    return value;
}

static void podium7_pmgr_raw_write(void *opaque, hwaddr address,
                                    uint64_t value, unsigned size)
{
    Podium7PMGRRaw *s = opaque;
    if (s->base == 0x202f20000ULL && address == 0x20) {
        /* Original XNU decodes low nibble as CPU state index + 2. Its
         * control initialization writes zero there before a request. Keep
         * the completed state unless UPDATE (bit 25) requests a new one.
         * Busy (bit 31) clears immediately in this fixed-clock TCG model. */
        uint32_t actual = s->registers[address >> 2] & 0xf;
        uint32_t desired = value & 0xf;
        if ((value & (1U << 25)) && desired >= 2) {
            actual = desired;
        }
        value = (value & ~0x8000000fULL) | actual;
    }
    s->registers[address >> 2] = value;
    if (s->logged_accesses++ < 128) {
        qemu_log("PODIUM7 PMGR-RAW base=%016" PRIx64 " write offset=%06" PRIx64
                 " value=%08" PRIx32 "\n", s->base, (uint64_t)address, (uint32_t)value);
    }
}

static const MemoryRegionOps podium7_pmgr_raw_ops = {
    .read = podium7_pmgr_raw_read, .write = podium7_pmgr_raw_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 8, .unaligned = false },
    .impl = { .min_access_size = 4, .max_access_size = 4, .unaligned = false },
};

static void podium7_pmgr_raw_create(MachineState *machine, MemoryRegion *memory)
{
    static const struct { hwaddr base; hwaddr size; } banks[] = {
        { 0x20e000000ULL, 0x100000 }, { 0x210200000ULL, 0x100000 },
        { 0x202f20000ULL, 0x11000 }, { 0x210004000ULL, 0x1000 },
        { 0x202f40000ULL, 0x10000 }, { 0x202f50000ULL, 0x1000 },
        { 0x202f80000ULL, 0x1000 }, { 0x202050000ULL, 0xa000 },
        { 0x202150000ULL, 0xa000 }, { 0x20e308000ULL, 0x1000 },
        /* Original 19H422 kernel maps [0x202f38000,0x202f39000) and writes
         * 64-bit control 0x8033 at +8. This window is not in PMGR's reg list.
         * Backing latches only; no unobserved PLL/timing semantics claimed. */
        { 0x202f38000ULL, 0x1000 },
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        Podium7PMGRRaw *s = g_new0(Podium7PMGRRaw, 1);
        s->base = banks[i].base;
        s->registers = g_new0(uint32_t, banks[i].size / 4);
        if (s->base == 0x202f20000ULL) {
            s->registers[0x20 / 4] = 2; /* first valid virtual CPU state */
        }
        if (s->base == 0x202f80000ULL) {
            /* XNU reads state records at encoded index * 0x20. Bit 23
             * distinguishes P-core records. States 0/1 are E, 2/3 are P. */
            s->registers[0x80 / 4] = 1U << 23;
            s->registers[0xa0 / 4] = 1U << 23;
        }
        memory_region_init_io(&s->io, OBJECT(machine), &podium7_pmgr_raw_ops,
                              s, "podium7-t8010-pmgr-raw", banks[i].size);
        memory_region_add_subregion_overlap(memory, s->base, &s->io, -1);
    }
}

static void podium7_pmgr_power_create(MachineState *machine, MemoryRegion *memory)
{
    static const hwaddr banks[] = {
        0x210280000ULL, 0x20e080000ULL, 0x20e080100ULL, 0x20e080200ULL,
        0x20e080300ULL, 0x20e080400ULL, 0x20e084000ULL, 0x20e088000ULL,
    };
    for (unsigned i = 0; i < ARRAY_SIZE(banks); i++) {
        Podium7PMGRPower *s = g_new0(Podium7PMGRPower, 1);
        s->base = banks[i];
        memory_region_init_io(&s->io, OBJECT(machine), &podium7_pmgr_power_ops,
                              s, "podium7-t8010-pmgr-power", 0x100);
        memory_region_add_subregion(memory, s->base, &s->io);
    }
}

'''

    # Match the original Apple CFI driver's query at unlock address 0x5555.
    # QEMU compares only low 11 address bits; preserve standard query at 0x55.
    cfi_path = directory / "hw/block/pflash_cfi02.c"
    cfi_source = cfi_path.read_text()
    cfi_source = cfi_source.replace("boff == 0x55 && cmd == 0x98",
        "(boff == 0x55 || boff == pfl->unlock_addr0) && cmd == 0x98")
    anchor = "        switch (cmd) {\n        case 0x20:"
    if cfi_source.count(anchor) != 1:
        raise ValueError("CFI unlock-state source anchor changed")
    cfi_source = cfi_source.replace(anchor,
        "        switch (cmd) {\n        case 0x98: /* Apple AMD unlock/query sequence */\n"
        "            pfl->wcycle = WCYCLE_CFI;\n"
        "            pfl->cmd = 0x98;\n"
        "            return;\n        case 0x20:")
    # ARM64 memcpy issues 64-bit reads immediately after leaving query mode,
    # before the lazy ROMD switch. Split them into supported 32-bit callbacks.
    wide_anchor = "    .valid.max_access_size = 4,"
    if cfi_source.count(wide_anchor) != 1:
        raise ValueError("CFI memory-operation source anchor changed")
    cfi_source = cfi_source.replace(wide_anchor,
        "    .valid.max_access_size = 8,\n    .impl.min_access_size = 1,\n    .impl.max_access_size = 4,")
    # This virtual NOR programs bytes immediately; don't advertise the generic
    # CFI device's slower byte-program timing to the original polling driver.
    timing_anchor = "    pfl->cfi_table[0x1F] = 0x07;"
    if cfi_source.count(timing_anchor) != 1:
        raise ValueError("CFI byte-program timing source anchor changed")
    cfi_source = cfi_source.replace(timing_anchor, timing_anchor +
        '\n    if (!strcmp(pfl->name, "podium7-nvram-cfi")) {\n'
        '        pfl->cfi_table[0x1F] = 0; /* 1-us virtual byte program */\n    }')
    cfi_path.write_text(cfi_source)
    kconfig = directory / "hw/arm/Kconfig"
    config = kconfig.read_text()
    start = config.index("config ARM_VIRT\n")
    end = config.index("\nconfig ", start + 1)
    block = config[start:end]
    if "select PFLASH_CFI02" not in block:
        block += "    select PFLASH_CFI02\n"
    kconfig.write_text(config[:start] + block + config[end:])
    replace_once(directory / "hw/arm/virt.c", '#include "hw/block/flash.h"',
                 '#include "hw/block/flash.h"\n#include "system/block-backend.h"')
    replace_once(directory / "hw/arm/virt.c", '#include "hw/arm/virt.h"',
                 '#include "hw/arm/virt.h"\n#include "target/arm/arm-powerctl.h"')
    replace_once(directory / "hw/arm/virt.c", '#include "qemu/error-report.h"',
                 '#include "qemu/error-report.h"\n#include "qemu/log.h"\n#include "qemu/timer.h"')
    replace_once(directory / "hw/arm/virt.c", "static void machvirt_init(MachineState *machine)",
                 uart + aic + wdt + gpio + aes + thermal + usbphy + dwi + mca + mipi + gfx + clpc + error_handler + sep + jpeg + scaler + vxd + isp + display + spi + i2c + pmp_system + dart + pcie + aop_system + i2s_switch + pmgr_bridges + pmgr_power + "static void machvirt_init(MachineState *machine)")
    timer_fiq = r'''
/* Research A10 EL1 timers arrive as FIQ, not GIC PPIs. External AIC device
 * interrupts use a separate CPU IRQ route; EL2 timer-enable controls are absent. */
typedef struct Podium7TimerFIQ {
    qemu_irq output;
    bool level[2];
    unsigned logged;
} Podium7TimerFIQ;

static void podium7_timer_fiq_set(void *opaque, int input, int level)
{
    Podium7TimerFIQ *s = opaque;
    s->level[input] = level;
    qemu_set_irq(s->output, s->level[0] || s->level[1]);
    if (s->logged++ < 128) {
        qemu_log("PODIUM7 TIMER-FIQ source=%d level=%d combined=%d\n",
                 input, level, s->level[0] || s->level[1]);
    }
}
'''
    irq_route = r'''
/* CPU0 sees the OR of the normal virt GIC output and Apple's AIC output. */
typedef struct Podium7IRQOr {
    qemu_irq output;
    bool level[2];
} Podium7IRQOr;
static qemu_irq podium7_aic_cpu_irq;
static void podium7_irq_or_set(void *opaque, int input, int level)
{
    Podium7IRQOr *s = opaque;
    s->level[input] = level;
    qemu_set_irq(s->output, s->level[0] || s->level[1]);
}
'''
    replace_once(directory / "hw/arm/virt.c", "static void create_gic(",
                 timer_fiq + irq_route + "static void create_gic(")
    replace_once(directory / "hw/arm/virt.c",
        "        sysbus_connect_irq(gicbusdev, i, qdev_get_gpio_in(cpudev, ARM_CPU_IRQ));",
        '''        if ((apple_timers || blk_by_name("podium7-pmp-core")) && i == 0) {
            Podium7IRQOr *route = g_new0(Podium7IRQOr, 1);
            route->output = qdev_get_gpio_in(cpudev, ARM_CPU_IRQ);
            sysbus_connect_irq(gicbusdev, i,
                qemu_allocate_irq(podium7_irq_or_set, route, 0));
            podium7_aic_cpu_irq = qemu_allocate_irq(podium7_irq_or_set, route, 1);
        } else {
            sysbus_connect_irq(gicbusdev, i, qdev_get_gpio_in(cpudev, ARM_CPU_IRQ));
        }''')
    replace_once(directory / "hw/arm/virt.c",
                 "        for (unsigned irq = 0; irq < ARRAY_SIZE(timer_irq); irq++) {",
                 '''        bool apple_timers = !strcmp(ms->cpu_type,
                                    ARM_CPU_TYPE_NAME("podium7-research"));
        Podium7TimerFIQ *fiq = NULL;
        if (apple_timers) {
            fiq = g_new0(Podium7TimerFIQ, 1);
            fiq->output = qdev_get_gpio_in(cpudev, ARM_CPU_FIQ);
        }
        for (unsigned irq = 0; irq < ARRAY_SIZE(timer_irq); irq++) {
            if (apple_timers && (irq == GTIMER_PHYS || irq == GTIMER_VIRT)) {
                qdev_connect_gpio_out(cpudev, irq,
                    qemu_allocate_irq(podium7_timer_fiq_set, fiq,
                                      irq == GTIMER_PHYS ? 0 : 1));
                continue;
            }''')
    replace_once(directory / "hw/arm/virt.c",
                 '''        sysbus_connect_irq(gicbusdev, i + smp_cpus,
                           qdev_get_gpio_in(cpudev, ARM_CPU_FIQ));''',
                 '''        if (!apple_timers) {
            sysbus_connect_irq(gicbusdev, i + smp_cpus,
                               qdev_get_gpio_in(cpudev, ARM_CPU_FIQ));
        }''')
    replace_once(directory / "hw/arm/virt.c",
                 "    create_uart(vms, VIRT_UART0, sysmem, serial_hd(0), false);",
                 '''    create_uart(vms, VIRT_UART0, sysmem, serial_hd(0), false);
    if (!strcmp(machine->cpu_type, ARM_CPU_TYPE_NAME("podium7-research"))) {
        podium7_uart_create(machine, sysmem);
        podium7_mcc_create(machine, sysmem);
        podium7_aic_create(machine, sysmem);
        podium7_wdt_create(machine, sysmem);
        podium7_gpio_create(machine, sysmem, 0x20f100000ULL, 208,
                            "podium7-t8010-main-gpio");
        podium7_gpio_create(machine, sysmem, 0x2100f0000ULL, 42,
                            "podium7-t8010-aop-gpio");
        podium7_aes_create(machine, sysmem, 0x20a108000ULL,
                           "podium7-t8010-aes-primary");
        podium7_aes_create(machine, sysmem, 0x2102d0000ULL,
                           "podium7-t8010-aes-secondary");
        podium7_thermal_create(machine, sysmem);
        podium7_usbphy_create(machine, sysmem);
        podium7_dwi_create(machine, sysmem);
        podium7_mca_create(machine, sysmem);
        podium7_mipi_dsim_create(machine, sysmem);
        podium7_gfx_create(machine, sysmem);
        podium7_cpu_clpc_create(machine, sysmem);
        podium7_error_handler_create(machine, sysmem);
        podium7_sep_mailbox_create(machine, sysmem);
        podium7_jpeg_create(machine, sysmem);
        podium7_scaler_create(machine, sysmem);
        podium7_vxd_create(machine, sysmem);
        podium7_isp_create(machine, sysmem);
        podium7_display_create(machine, sysmem);
        podium7_spi_create(machine, sysmem);
        podium7_i2c_create(machine, sysmem);
        podium7_pmp_system_create(machine, sysmem);
        podium7_dart_create(machine, sysmem);
        podium7_pcie_create(machine, sysmem);
        podium7_aop_system_create(machine, sysmem);
        podium7_i2s_switch_create(machine, sysmem);
        podium7_pmgr_bridges_create(machine, sysmem);
        podium7_pmgr_raw_create(machine, sysmem);
        podium7_pmgr_power_create(machine, sysmem);
        BlockBackend *nvram = blk_by_name("podium7-nvram");
        if (nvram) {
            pflash_cfi02_register(0x2f0000000ULL, "podium7-nvram-cfi",
                                 0x8000, nvram, 0x2000, 1, 1,
                                 0x01, 0x7e, 0, 0, 0x5555, 0x2aaa, 0);
        }
    }
    /* Standalone Cortex-A7 PMP firmware experiment only, explicitly opted in
     * by its guarded firmware backend. No ARM64 XNU integration or peer ACKs. */
    if (blk_by_name("podium7-pmp-core")) {
        podium7_aic_create(machine, sysmem);
        podium7_pmgr_raw_create(machine, sysmem);
        Podium7SEPMailboxBank *pmp = podium7_sep_mailbox_bank_create(
            machine, sysmem, 0x20e300000ULL, 0x20000, "podium7-pmp-core-mailbox");
        /* Mirror the original driver's boot descriptor, using this probe's
         * actual synthetic load address. No firmware-ready/response flags. */
        pmp->registers[0x08 >> 2] = 0x41000000U;
        pmp->registers[0x10 >> 2] = 0;
        pmp->registers[0x18 >> 2] = 0;
        pmp->registers[0x20 >> 2] = 0;
        pmp->registers[0x28 >> 2] = 0x20000;
        pmp->registers[0x30 >> 2] = 0;
        pmp->registers[0x38 >> 2] = 1;
        podium7_pmp_system_create(machine, sysmem);
    }''')
    subprocess.run(["git", "-C", str(directory), "diff", "--check"], check=True)
    print("Registered podium7-research on pinned QEMU; APRR enforcement remains unsupported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    patch(parser.parse_args().directory)

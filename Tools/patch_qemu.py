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
        address >= 0xffffffe000000000ULL && address < 0xfffffff000000000ULL &&
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
    if (address == 0x20) { putchar(value & 0xff); fflush(stdout); return; }
    if (address < sizeof(uart->registers)) { uart->registers[address / 4] = value; }
}
static const MemoryRegionOps podium7_uart_ops = {
    .read = podium7_uart_read, .write = podium7_uart_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 4 },
};
static void podium7_uart_create(MachineState *machine, MemoryRegion *memory)
{
    Podium7UART *uart = g_new0(Podium7UART, 1);
    memory_region_init_io(&uart->region, OBJECT(machine), &podium7_uart_ops,
                         uart, "podium7-uart-tx-only", 0x4000);
    memory_region_add_subregion(memory, 0x20a0c0000ULL, &uart->region);
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
    bool locked;
} Podium7MCC;
static uint64_t podium7_mcc_read(void *opaque, hwaddr address, unsigned size)
{
    Podium7MCC *mcc = opaque;
    switch (address) {
    case 0: return 0; /* cache disabled in this minimal controller */
    case 0x7e4: return mcc->lower;
    case 0x7e8: return mcc->upper;
    case 0x7ec: return mcc->locked;
    default: return 0;
    }
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
    .valid = { .min_access_size = 4, .max_access_size = 4 },
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
 * External device wiring and timer FIQ delivery are not modeled yet.
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
    replace_once(directory / "hw/arm/virt.c", '#include "qemu/error-report.h"',
                 '#include "qemu/error-report.h"\n#include "qemu/log.h"')
    replace_once(directory / "hw/arm/virt.c", "static void machvirt_init(MachineState *machine)",
                 uart + aic + "static void machvirt_init(MachineState *machine)")
    replace_once(directory / "hw/arm/virt.c",
                 "    create_uart(vms, VIRT_UART0, sysmem, serial_hd(0), false);",
                 '''    create_uart(vms, VIRT_UART0, sysmem, serial_hd(0), false);
    if (!strcmp(machine->cpu_type, ARM_CPU_TYPE_NAME("podium7-research"))) {
        podium7_uart_create(machine, sysmem);
        podium7_mcc_create(machine, sysmem);
        podium7_aic_create(machine, sysmem);
    }''')
    subprocess.run(["git", "-C", str(directory), "diff", "--check"], check=True)
    print("Registered podium7-research on pinned QEMU; APRR enforcement remains unsupported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    patch(parser.parse_args().directory)

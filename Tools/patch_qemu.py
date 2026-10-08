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
}

'''
    replace_once(directory / "hw/arm/virt.c", '#include "qemu/error-report.h"',
                 '#include "qemu/error-report.h"\n#include "qemu/log.h"')
    replace_once(directory / "hw/arm/virt.c", "static void machvirt_init(MachineState *machine)",
                 uart + aic + wdt + gpio + aes + thermal + usbphy + "static void machvirt_init(MachineState *machine)")
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
    }''')
    subprocess.run(["git", "-C", str(directory), "diff", "--check"], check=True)
    print("Registered podium7-research on pinned QEMU; APRR enforcement remains unsupported")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=pathlib.Path)
    patch(parser.parse_args().directory)

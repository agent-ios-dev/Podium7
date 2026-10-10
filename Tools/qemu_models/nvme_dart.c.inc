/* Opt-in port0 DART research mapper, derived from original queue snapshots.
 * 4K two-level tables; PCI inbound address bit31 is excluded from table index.
 * Other streams, fault IRQs, DAPF and MSI delivery are not implemented. */
static uint64_t podium7_storage_ram_end;
static unsigned podium7_storage_dma_logged;
static unsigned podium7_storage_dma_fault_seen;

static bool podium7_storage_read_pte(uint64_t address, uint64_t *value)
{
    uint64_t little;
    if (address < 0x40000000ULL || address > podium7_storage_ram_end - 8 ||
        address_space_read(&address_space_memory, address, MEMTXATTRS_UNSPECIFIED,
                           &little, sizeof(little)) != MEMTX_OK) { return false; }
    *value = le64_to_cpu(little);
    return (*value & 1) != 0;
}

static IOMMUTLBEntry podium7_storage_translate(IOMMUMemoryRegion *mr,
    hwaddr address, IOMMUAccessFlags flags, int index)
{
    IOMMUTLBEntry entry = {
        .target_as = &address_space_memory,
        .iova = address & ~0xfffULL,
        .translated_addr = address & ~0xfffULL,
        .addr_mask = 0xfff,
        .perm = IOMMU_RW,
    };
    if (!podium7_storage_dart ||
        !(podium7_storage_dart->registers[0x20 >> 2] & 0x100)) { return entry; }
    entry.perm = IOMMU_NONE;
    uint64_t iova = address & 0x7fffffffULL;
    uint32_t ttbr = podium7_storage_dart->registers[(0x40 >> 2) + (iova >> 30)];
    uint64_t first = 0, leaf = 0;
    if (address <= 0xffffffffULL && (ttbr & 0x80000000U) &&
        podium7_storage_read_pte(((uint64_t)(ttbr & 0xffffffU) << 12) +
                                 (((iova >> 21) & 0x1ff) << 3), &first) &&
        podium7_storage_read_pte((first & 0xfffffff000ULL) +
                                 (((iova >> 12) & 0x1ff) << 3), &leaf)) {
        uint64_t physical = leaf & 0xfffffff000ULL;
        if (physical >= 0x40000000ULL && physical <= podium7_storage_ram_end - 4096) {
            entry.translated_addr = physical;
            entry.perm = ((leaf & (1U << 8)) ? 0 : IOMMU_RO) |
                         ((leaf & (1U << 7)) ? 0 : IOMMU_WO);
        }
    }
    if (podium7_storage_dma_logged++ < 256) {
        qemu_log("PODIUM7 NVME-DART iova=%016" PRIx64 " physical=%016" PRIx64
                 " leaf=%016" PRIx64 " perm=%u access=%u\n",
                 (uint64_t)address, (uint64_t)entry.translated_addr,
                 leaf, (unsigned)entry.perm, (unsigned)flags);
    }
    if ((entry.perm & flags) != flags) {
        unsigned kind = 1U << ((entry.perm ? 1 : 0) + (flags == IOMMU_WO ? 0 : 2));
        if (!(podium7_storage_dma_fault_seen & kind)) {
            podium7_storage_dma_fault_seen |= kind;
            qemu_log("PODIUM7 NVME-DART rejected %s iova=%016" PRIx64 " access=%u\n",
                     entry.perm ? "permission" : "unmapped", (uint64_t)address, (unsigned)flags);
        }
    }
    return entry;
}

static void podium7_storage_iommu_class_init(ObjectClass *klass, void *data)
{
    IOMMU_MEMORY_REGION_CLASS(klass)->translate = podium7_storage_translate;
}

static const TypeInfo podium7_storage_iommu_info = {
    .name = "podium7-storage-dart-iommu",
    .parent = TYPE_IOMMU_MEMORY_REGION,
    .class_init = podium7_storage_iommu_class_init,
};

static void podium7_storage_iommu_register(void)
{
    type_register_static(&podium7_storage_iommu_info);
}
type_init(podium7_storage_iommu_register);

static AddressSpace *podium7_storage_dma_as(PCIBus *bus, void *opaque, int devfn)
{
    return opaque;
}

static const PCIIOMMUOps podium7_storage_iommu_ops = {
    .get_address_space = podium7_storage_dma_as,
};

static void podium7_storage_iommu_setup(VirtMachineState *vms, PCIHostState *pci)
{
    if (g_strcmp0(g_getenv("PODIUM7_RESEARCH_NVME_DART"), "1")) { return; }
    podium7_storage_ram_end = 0x40000000ULL + MACHINE(vms)->ram_size;
    IOMMUMemoryRegion *iommu = g_new0(IOMMUMemoryRegion, 1);
    memory_region_init_iommu(iommu, sizeof(*iommu), "podium7-storage-dart-iommu",
                             OBJECT(vms), "podium7-storage-dart", UINT64_MAX);
    AddressSpace *space = g_new0(AddressSpace, 1);
    address_space_init(space, MEMORY_REGION(iommu), "podium7-storage-dma");
    pci->bypass_iommu = false;
    pci_setup_iommu(pci->bus, &podium7_storage_iommu_ops, space);
}

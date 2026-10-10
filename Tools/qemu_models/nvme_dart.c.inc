/* Opt-in port0 DART research mapper, derived from original queue snapshots.
 * 4K two-level tables; PCI inbound address bit31 is excluded from table index.
 * Other streams, fault IRQs and DAPF are not implemented.
 * A separate opt-in MSI aperture below has its own EL1 delivery test. */
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
    uint64_t l1_address = ((uint64_t)(ttbr & 0xffffffU) << 12) +
                          (((iova >> 21) & 0x1ff) << 3);
    uint64_t first = 0, leaf = 0;
    bool subpage_fault = false;
    if (address <= 0xffffffffULL && (ttbr & 0x80000000U) &&
        podium7_storage_read_pte(((uint64_t)(ttbr & 0xffffffU) << 12) +
                                 (((iova >> 21) & 0x1ff) << 3), &first) &&
        podium7_storage_read_pte((first & 0xffffff000ULL) +
                                 (((iova >> 12) & 0x1ff) << 3), &leaf)) {
        /* Original T8010 descriptors use 36-bit physical addresses. Upper
         * fields encode inclusive byte start/end, not physical address bits.
         * bit1 bypasses subpage protection for whole-page queue mappings. */
        uint64_t physical = leaf & 0xffffff000ULL;
        if (physical >= 0x40000000ULL && physical <= podium7_storage_ram_end - 4096) {
            entry.translated_addr = physical;
            entry.perm = ((leaf & (1U << 8)) ? 0 : IOMMU_RO) |
                         ((leaf & (1U << 7)) ? 0 : IOMMU_WO);
            if (!(leaf & 2)) {
                unsigned start = (leaf >> 48) & 0xfff;
                unsigned end = (leaf >> 36) & 0xfff;
                unsigned offset = address & 0xfff;
                entry.addr_mask = (start % 4 == 0 && end % 4 == 3) ? 3 : 0;
                entry.iova = address & ~entry.addr_mask;
                entry.translated_addr = physical + (offset & ~entry.addr_mask);
                if (start > end || offset < start || offset > end) {
                    entry.perm = IOMMU_NONE;
                    subpage_fault = true;
                }
            }
        }
    }
    if (podium7_storage_dma_logged++ < 256) {
        qemu_log("PODIUM7 NVME-DART iova=%016" PRIx64 " physical=%016" PRIx64
                 " leaf=%016" PRIx64 " perm=%u access=%u\n",
                 (uint64_t)address, (uint64_t)entry.translated_addr,
                 leaf, (unsigned)entry.perm, (unsigned)flags);
    }
    if ((entry.perm & flags) != flags) {
        unsigned kind = 1U << (subpage_fault ? 4 : ((entry.perm ? 1 : 0) + (flags == IOMMU_WO ? 0 : 2)));
        if (!(podium7_storage_dma_fault_seen & kind)) {
            podium7_storage_dma_fault_seen |= kind;
            qemu_log("PODIUM7 NVME-DART rejected %s iova=%016" PRIx64 " access=%u\n",
                     subpage_fault ? "subpage" : entry.perm ? "permission" : "unmapped", (uint64_t)address, (unsigned)flags);
            qemu_log("PODIUM7 NVME-DART fault-pt ttbr=%08x l1_address=%016" PRIx64
                     " l1=%016" PRIx64 " l2_address=%016" PRIx64 " leaf=%016" PRIx64 "\n",
                     ttbr, l1_address, first, (first & 0xffffff000ULL) +
                     (((iova >> 12) & 0x1ff) << 3), leaf);
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

/* Separate research MSI aperture from the original n112ap DeviceTree:
 * msi-address=bffff000, msi-vector-offset=288, #msi-vectors=32.
 * No interrupt is generated without an actual valid endpoint MSI write.
 * Restricted to port0's eight vectors; other ports remain unsupported. */
static void podium7_storage_msi_write(void *opaque, hwaddr offset,
                                      uint64_t data, unsigned size)
{
    if (offset || size != 4 || data >= 8) {
        qemu_log("PODIUM7 NVME-MSI rejected offset=%" PRIx64 " data=%" PRIx64 "\n",
                 (uint64_t)offset, data);
        return;
    }
    qemu_log("PODIUM7 NVME-MSI delivered data=%" PRIu64 " aic=%" PRIu64 "\n", data, 288 + data);
    podium7_aic_raise_edge(288 + data);
}

static const MemoryRegionOps podium7_storage_msi_ops = {
    .write = podium7_storage_msi_write, .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static void podium7_storage_iommu_setup(VirtMachineState *vms, PCIHostState *pci)
{
    if (g_strcmp0(g_getenv("PODIUM7_RESEARCH_NVME_DART"), "1")) { return; }
    podium7_storage_ram_end = 0x40000000ULL + MACHINE(vms)->ram_size;
    IOMMUMemoryRegion *iommu = g_new0(IOMMUMemoryRegion, 1);
    memory_region_init_iommu(iommu, sizeof(*iommu), "podium7-storage-dart-iommu",
                             OBJECT(vms), "podium7-storage-dart", UINT64_MAX);
    AddressSpace *space = g_new0(AddressSpace, 1);
    MemoryRegion *dma_root = g_new0(MemoryRegion, 1);
    memory_region_init(dma_root, OBJECT(vms), "podium7-storage-dma-root", UINT64_MAX);
    memory_region_add_subregion(dma_root, 0, MEMORY_REGION(iommu));
    if (!g_strcmp0(g_getenv("PODIUM7_RESEARCH_NVME_MSI"), "1")) {
        MemoryRegion *msi = g_new0(MemoryRegion, 1);
        memory_region_init_io(msi, OBJECT(vms), &podium7_storage_msi_ops, NULL,
                             "podium7-storage-msi", 4096);
        memory_region_add_subregion_overlap(dma_root, 0xbffff000ULL, msi, 1);
    }
    address_space_init(space, dma_root, "podium7-storage-dma");
    pci->bypass_iommu = false;
    pci_setup_iommu(pci->bus, &podium7_storage_iommu_ops, space);
}

/* Separate opt-in research PCIe/NVMe backend, using stock QEMU devices.
 * No Apple NVMe firmware, DART or MSI routing is claimed by this experiment. */
static PCIDevice *podium7_storage_port;

static bool podium7_storage_link_active(void)
{
    if (!podium7_storage_port) { return false; }
    unsigned cap = podium7_storage_port->exp.exp_cap;
    return cap && (pci_get_word(podium7_storage_port->config + cap + PCI_EXP_LNKSTA)
                   & PCI_EXP_LNKSTA_DLLLA);
}

static void podium7_storage_attach(VirtMachineState *vms, DeviceState *host)
{
    BlockBackend *disk = blk_by_name("podium7-storage");
    if (!disk) { return; }
    PCIHostState *pci = PCI_HOST_BRIDGE(host);
    PCIDevice *port = NULL;
    /* Original DeviceTree exposes four host ports. Empty root ports still
     * have real PCI capabilities, but no endpoint or active link. */
    for (unsigned i = 0; i < 4; i++) {
        PCIDevice *root = pci_new(PCI_DEVFN(i, 0), "pcie-root-port");
        qdev_prop_set_uint8(DEVICE(root), "port", i + 1);
        qdev_prop_set_uint8(DEVICE(root), "chassis", 1);
        qdev_prop_set_uint16(DEVICE(root), "slot", i + 1);
        pci_realize_and_unref(root, pci->bus, &error_fatal);
        if (i == 0) { port = root; }
    }
    PCIDevice *nvme = pci_new(PCI_DEVFN(0, 0), "nvme");
    qdev_prop_set_string(DEVICE(nvme), "serial", "Podium7-Research");
    qdev_prop_set_drive(DEVICE(nvme), "drive", disk);
    pci_realize_and_unref(nvme, &PCI_BRIDGE(port)->sec_bus, &error_fatal);
    podium7_storage_port = port;
    MemoryRegion *ecam = g_new0(MemoryRegion, 1);
    memory_region_init_alias(ecam, OBJECT(host), "podium7-storage-ecam",
        sysbus_mmio_get_region(SYS_BUS_DEVICE(host), 0), 0, 0x1000000);
    memory_region_add_subregion(get_system_memory(), 0x610000000ULL, ecam);
    MemoryRegion *mmio64 = g_new0(MemoryRegion, 1);
    memory_region_init_alias(mmio64, OBJECT(host), "podium7-storage-mmio64",
        sysbus_mmio_get_region(SYS_BUS_DEVICE(host), 1), 0x620000000ULL, 0x1a0000000ULL);
    memory_region_add_subregion(get_system_memory(), 0x620000000ULL, mmio64);
    MemoryRegion *mmio32 = g_new0(MemoryRegion, 1);
    memory_region_init_alias(mmio32, OBJECT(host), "podium7-storage-mmio32",
        sysbus_mmio_get_region(SYS_BUS_DEVICE(host), 1), 0xc0000000ULL, 0x40000000);
    memory_region_add_subregion(get_system_memory(), 0x7c0000000ULL, mmio32);
    qemu_log("PODIUM7 genuine QEMU NVMe attached; direct DMA, MSI routing not implemented\n");
}

import Foundation

public enum BootBundleError: Error {
    case invalidManifest, invalidFile(String)
}

/// Private prepared boot fixture. Never accept arbitrary QEMU options.
public struct BootBundle: Codable {
    public let schema: Int
    public let profile: String
    public let diskBytes: UInt64
    public let rorgn: [UInt32]
    public static let filenames = ["boot.elf", "pmp.bin", "nvram.raw", "disk.raw"]
    public static let diagnosticProfile = "19H422-disabled-aks-root-unsupported-v1"

    public static func read(directory: URL) throws -> BootBundle {
        let url = directory.appendingPathComponent("boot.json")
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size > 0, size <= 4096 else { throw BootBundleError.invalidManifest }
        let bundle = try JSONDecoder().decode(Self.self, from: Data(contentsOf: url))
        guard bundle.schema == 1, bundle.profile == diagnosticProfile,
              bundle.diskBytes == VirtualDisk.capacity, bundle.rorgn.count == 2 else {
            throw BootBundleError.invalidManifest
        }
        for name in filenames {
            let values = try directory.appendingPathComponent(name).resourceValues(
                forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true,
                  let bytes = values.fileSize, bytes > 0,
                  (name != "disk.raw" || UInt64(bytes) == bundle.diskBytes) else {
                throw BootBundleError.invalidFile(name)
            }
        }
        let handle = try FileHandle(forReadingFrom: directory.appendingPathComponent("boot.elf"))
        defer { try? handle.close() }
        let header = try handle.read(upToCount: 20) ?? Data()
        guard header.count == 20, Array(header.prefix(7)) == [0x7f, 0x45, 0x4c, 0x46, 2, 1, 1],
              header[18] == 0xb7, header[19] == 0 else { throw BootBundleError.invalidFile("boot.elf") }
        return bundle
    }

    public func arguments(directory: URL, logs: URL, qmp: URL) throws -> [String] {
        for path in [directory.path, logs.path, qmp.path] {
            guard !path.contains(","), !path.contains("\n"), !path.contains("\0") else {
                throw BootBundleError.invalidManifest
            }
        }
        func file(_ name: String) -> String { directory.appendingPathComponent(name).path }
        return ["Podium7QEMU", "-machine", "virt,secure=off,virtualization=off",
                "-cpu", "podium7-research,cntfrq=24000000", "-accel", "tcg",
                "-m", "2048", "-smp", "1,maxcpus=2", "-display", "none", "-monitor", "none",
                "-serial", "file:\(logs.appendingPathComponent("serial.txt").path)",
                "-device", "loader,file=\(file("boot.elf")),cpu-num=0",
                "-drive", "if=none,id=podium7-pmp-integrated,format=raw,read-only=on,file=\(file("pmp.bin"))",
                "-drive", "if=none,id=podium7-nvram,format=raw,cache=writeback,file=\(file("nvram.raw"))",
                "-drive", "if=none,id=podium7-storage,format=raw,file=\(file("disk.raw"))",
                "-device", "loader,addr=0x2000007e4,data=\(rorgn[0]),data-len=4",
                "-device", "loader,addr=0x2000007e8,data=\(rorgn[1]),data-len=4",
                "-d", "guest_errors,unimp", "-D", logs.appendingPathComponent("qemu.txt").path,
                "-qmp", "unix:\(qmp.path),server=on,wait=off"]
    }
}

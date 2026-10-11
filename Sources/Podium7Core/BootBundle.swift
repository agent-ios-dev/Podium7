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
        let info = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey])
        let size = info.fileSize ?? 0
        guard info.isRegularFile == true, info.isSymbolicLink != true,
              size > 0, size <= 4096 else { throw BootBundleError.invalidManifest }
        let bundle = try JSONDecoder().decode(Self.self, from: Data(contentsOf: url))
        guard bundle.schema == 1, bundle.profile == diagnosticProfile,
              bundle.diskBytes == VirtualDisk.capacity, bundle.rorgn.count == 2,
              bundle.rorgn[0] <= bundle.rorgn[1], bundle.rorgn[1] < 131072 else {
            throw BootBundleError.invalidManifest
        }
        for name in filenames {
            let values = try directory.appendingPathComponent(name).resourceValues(
                forKeys: [.isRegularFileKey, .isSymbolicLinkKey, .fileSizeKey])
            guard values.isRegularFile == true, values.isSymbolicLink != true,
                  let bytes = values.fileSize, bytes > 0,
                  (name != "disk.raw" || UInt64(bytes) == bundle.diskBytes),
                  (name != "nvram.raw" || bytes == 0x8000),
                  (name != "pmp.bin" || bytes <= 16 * 1024 * 1024),
                  (name != "boot.elf" || bytes <= 512 * 1024 * 1024) else {
                throw BootBundleError.invalidFile(name)
            }
        }
        let handle = try FileHandle(forReadingFrom: directory.appendingPathComponent("boot.elf"))
        defer { try? handle.close() }
        let fileBytes = try handle.seekToEnd()
        try handle.seek(toOffset: 0)
        let header = try handle.read(upToCount: 64) ?? Data()
        guard header.count == 64, Array(header.prefix(7)) == [0x7f, 0x45, 0x4c, 0x46, 2, 1, 1],
              header[18] == 0xb7, header[19] == 0 else { throw BootBundleError.invalidFile("boot.elf") }
        func integer(_ data: Data, _ offset: Int, _ bytes: Int) -> UInt64 {
            (0..<bytes).reduce(UInt64(0)) { $0 | UInt64(data[offset + $1]) << (8 * $1) }
        }
        let entry = integer(header, 24, 8)
        let phoff = integer(header, 32, 8)
        let count = integer(header, 56, 2)
        let stride = integer(header, 54, 2)
        guard integer(header, 16, 2) == 2, integer(header, 20, 4) == 1,
              entry >= 0x40000000, entry < 0xc0000000,
              phoff >= 64, phoff <= fileBytes, stride == 56, count > 0, count <= 256,
              count * stride <= fileBytes - phoff else { throw BootBundleError.invalidFile("boot.elf") }
        try handle.seek(toOffset: phoff)
        let programs = try handle.read(upToCount: Int(count * stride)) ?? Data()
        guard programs.count == Int(count * stride) else { throw BootBundleError.invalidFile("boot.elf") }
        for index in 0..<Int(count) {
            let start = index * Int(stride)
            let offset = integer(programs, start + 8, 8)
            let physical = integer(programs, start + 24, 8)
            let fileSize = integer(programs, start + 32, 8)
            let memorySize = integer(programs, start + 40, 8)
            guard integer(programs, start, 4) == 1,
                  offset <= fileBytes, fileSize <= fileBytes - offset,
                  fileSize <= memorySize, physical >= 0x40000000, physical <= 0xc0000000,
                  memorySize <= 0xc0000000 - physical else { throw BootBundleError.invalidFile("boot.elf") }
        }
        return bundle
    }

    public func arguments(directory: URL, logs: URL, qmp: URL, nativeJIT: Bool = false) throws -> [String] {
        guard qmp.path.utf8.count < 104 else { throw BootBundleError.invalidFile("QMP socket path too long") }
        for path in [directory.path, logs.path, qmp.path] {
            guard !path.contains(","), !path.contains("\n"), !path.contains("\0") else {
                throw BootBundleError.invalidManifest
            }
        }
        func file(_ name: String) -> String { directory.appendingPathComponent(name).path }
        return ["Podium7QEMU", "-machine", "virt,secure=off,virtualization=off",
                "-cpu", "podium7-research,cntfrq=24000000", "-accel", nativeJIT ? "tcg,tb-size=64" : "tcg",
                "-m", "2048", "-smp", "1,maxcpus=2", "-display", "none", "-monitor", "none", "-nic", "none",
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

import XCTest
@testable import Podium7Core

final class BootBundleTests: XCTestCase {
    private func fixture(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let manifest = BootBundle(schema: 1, profile: BootBundle.diagnosticProfile,
                                  diskBytes: VirtualDisk.capacity, rorgn: [1, 2])
        try JSONEncoder().encode(manifest).write(to: root.appendingPathComponent("boot.json"))
        var header = Data([0x7f, 0x45, 0x4c, 0x46, 2, 1, 1] + Array(repeating: UInt8(0), count: 13))
        header[18] = 0xb7
        try header.write(to: root.appendingPathComponent("boot.elf"))
        try Data([1]).write(to: root.appendingPathComponent("pmp.bin"))
        try Data(repeating: 0, count: 128 * 1024).write(to: root.appendingPathComponent("nvram.raw"))
        _ = try VirtualDisk(url: root.appendingPathComponent("disk.raw"))
        try body(root)
    }

    func testPreparedDiskIsNotReplacedAndQEMUArgumentsAreHostControlled() throws {
        try fixture { root in
            let disk = try VirtualDisk(url: root.appendingPathComponent("disk.raw"))
            try disk.write(offset: VirtualDisk.capacity - 4, data: Data([9, 8, 7, 6]))
            let bundle = try BootBundle.read(directory: root)
            let args = try bundle.arguments(directory: root, logs: root, qmp: URL(fileURLWithPath: "/tmp/p7.sock"))
            XCTAssertTrue(args.contains("1,maxcpus=2"))
            XCTAssertEqual(try disk.read(offset: VirtualDisk.capacity - 4, count: 4), Data([9, 8, 7, 6]))
            XCTAssertThrowsError(try bundle.arguments(directory: URL(fileURLWithPath: "/tmp/a,readonly=off"), logs: root, qmp: root))
        }
    }

    func testSymlinksWrongArchitectureAndWrongDiskSizeFail() throws {
        try fixture { root in
            let pmp = root.appendingPathComponent("pmp.bin")
            try FileManager.default.removeItem(at: pmp)
            try FileManager.default.createSymbolicLink(at: pmp, withDestinationURL: root.appendingPathComponent("nvram.raw"))
            XCTAssertThrowsError(try BootBundle.read(directory: root))
            try FileManager.default.removeItem(at: pmp)
            try Data([1]).write(to: pmp)
            let elf = root.appendingPathComponent("boot.elf")
            var data = try Data(contentsOf: elf); data[18] = 0x3e
            try data.write(to: elf)
            XCTAssertThrowsError(try BootBundle.read(directory: root))
            data[18] = 0xb7; try data.write(to: elf)
            let disk = try FileHandle(forWritingTo: root.appendingPathComponent("disk.raw"))
            try disk.truncate(atOffset: 512); try disk.close()
            XCTAssertThrowsError(try BootBundle.read(directory: root))
        }
    }
}

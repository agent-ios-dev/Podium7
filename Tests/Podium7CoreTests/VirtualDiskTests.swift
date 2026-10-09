import XCTest
import Darwin
@testable import Podium7Core

final class VirtualDiskTests: XCTestCase {
    private func withImage(_ body: (URL) throws -> Void) throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        try body(folder.appendingPathComponent("disk.raw"))
    }

    func testFixedCapacitySparseHolesAndWritesAboveFourGiB() throws {
        try withImage { url in
            let disk = try VirtualDisk(url: url)
            let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
            XCTAssertEqual(size?.uint64Value, 17_179_869_184)
            var status = stat()
            XCTAssertEqual(url.withUnsafeFileSystemRepresentation { Darwin.stat($0!, &status) }, 0)
            XCTAssertLessThan(UInt64(status.st_blocks) * 512, 1024 * 1024)
            XCTAssertEqual(try disk.read(offset: 12 * 1024 * 1024 * 1024, count: 512), Data(repeating: 0, count: 512))
            let marker = Data([1, 2, 3, 4])
            try disk.write(offset: VirtualDisk.capacity - 4, data: marker)
            try disk.synchronize()
            let reopened = try VirtualDisk(url: url)
            XCTAssertEqual(try reopened.read(offset: VirtualDisk.capacity - 4, count: 4), marker)
            XCTAssertThrowsError(try disk.write(offset: VirtualDisk.capacity - 3, data: marker))
            XCTAssertThrowsError(try disk.read(offset: UInt64.max, count: 1))
            XCTAssertThrowsError(try disk.read(offset: 0, count: -1))
        }
    }

    func testExistingImageIsExpandedWithoutErasingAndOversizeIsNotShrunk() throws {
        try withImage { url in
            try Data([7, 8, 9]).write(to: url)
            let disk = try VirtualDisk(url: url)
            XCTAssertEqual(try disk.read(offset: 0, count: 3), Data([7, 8, 9]))
            let handle = try FileHandle(forWritingTo: url)
            try handle.truncate(atOffset: VirtualDisk.capacity + 512)
            try handle.close()
            XCTAssertThrowsError(try VirtualDisk(url: url)) { XCTAssertEqual($0 as? VirtualDiskFault, .oversizedImage) }
            let size = try FileManager.default.attributesOfItem(atPath: url.path)[.size] as? NSNumber
            XCTAssertEqual(size?.uint64Value, VirtualDisk.capacity + 512)
        }
    }
}

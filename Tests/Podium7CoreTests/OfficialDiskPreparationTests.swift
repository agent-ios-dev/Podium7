import XCTest
import Compression
@testable import Podium7Core

final class OfficialDiskPreparationTests: XCTestCase {
    func testRawAndLZFSEBlocksDecodeWithoutDeveloperImage() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let archive = folder.appendingPathComponent("fixture.ipsw"), disk = folder.appendingPathComponent("disk.raw")
        try makeArchive(archive, corrupt: false)
        try OfficialDiskPreparation.convert(archive: archive, destination: disk)
        let output = try FileHandle(forReadingFrom: disk)
        defer { try? output.close() }
        XCTAssertEqual(try output.seekToEnd(), 16 << 30)
        try output.seek(toOffset: 0)
        XCTAssertEqual(try output.read(upToCount: 1024), Data(repeating: 0xaa, count: 512) + Data(repeating: 0xbb, count: 512))
        XCTAssertThrowsError(try OfficialDiskPreparation.convert(archive: archive, destination: disk))
        try output.seek(toOffset: 0)
        XCTAssertEqual(try output.read(upToCount: 4), Data(repeating: 0xaa, count: 4))
    }

    func testCorruptCompressedBlockDoesNotLeaveReadyDisk() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let archive = folder.appendingPathComponent("fixture.ipsw"), disk = folder.appendingPathComponent("disk.raw")
        try makeArchive(archive, corrupt: true)
        XCTAssertThrowsError(try OfficialDiskPreparation.convert(archive: archive, destination: disk))
        XCTAssertFalse(FileManager.default.fileExists(atPath: disk.path))
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: folder.path), ["fixture.ipsw"])
    }

    private func makeArchive(_ url: URL, corrupt: Bool) throws {
        func put(_ bytes: inout Data, _ offset: Int, _ value: UInt64, _ count: Int, little: Bool = false) {
            for index in 0..<count { bytes[offset + index] = UInt8(truncatingIfNeeded: value >> (8 * (little ? index : count - 1 - index))) }
        }
        let raw = Data(repeating: 0xaa, count: 512), plain = Data(repeating: 0xbb, count: 512)
        var compressed = Data(count: 4096)
        let count = compressed.withUnsafeMutableBytes { target in plain.withUnsafeBytes { source in
            compression_encode_buffer(target.bindMemory(to: UInt8.self).baseAddress!, 4096,
                source.bindMemory(to: UInt8.self).baseAddress!, 512, nil, COMPRESSION_LZFSE)
        } }
        XCTAssertGreaterThan(count, 0)
        compressed.count = count
        if corrupt { compressed = Data(repeating: 0, count: count) }
        var table = Data(count: 284)
        table.replaceSubrange(0..<4, with: Data("mish".utf8)); put(&table, 200, 2, 4)
        put(&table, 204, 1, 4); put(&table, 220, 1, 8); put(&table, 236, 512, 8)
        put(&table, 244, 0x80000007, 4); put(&table, 252, 1, 8); put(&table, 260, 1, 8)
        put(&table, 268, 512, 8); put(&table, 276, UInt64(count), 8)
        let xml = try PropertyListSerialization.data(fromPropertyList: ["resource-fork": ["blkx": [["Data": table]]]], format: .xml, options: 0)
        let name = Data("098-68748-067.dmg".utf8)
        var local = Data(count: 30)
        put(&local, 0, 0x04034b50, 4, little: true); put(&local, 26, UInt64(name.count), 2, little: true)
        let start: UInt64 = 154_122_511 + 30 + UInt64(name.count)
        var footer = Data(count: 512)
        footer.replaceSubrange(0..<4, with: Data("koly".utf8))
        put(&footer, 4, 4, 4); put(&footer, 8, 512, 4); put(&footer, 60, 1, 4)
        put(&footer, 32, 4 << 20, 8); put(&footer, 216, 4 << 20, 8); put(&footer, 224, UInt64(xml.count), 8)
        XCTAssertTrue(FileManager.default.createFile(atPath: url.path, contents: nil))
        let file = try FileHandle(forUpdating: url); defer { try? file.close() }
        try file.truncate(atOffset: 5_013_514_038)
        for (offset, data) in [(154_122_511, local + name), (start, raw + compressed),
                               (start + (4 << 20), xml), (start + 4_813_157_696 - 512, footer)] {
            try file.seek(toOffset: offset); try file.write(contentsOf: data)
        }
    }
}

import Foundation
import Compression

/// Converts the OS member of the verified 19H422 IPSW on iOS/macOS, without
/// hdiutil or a developer disk. This stage is not a complete installed VM.
public enum OfficialDiskPreparation {
    public enum Failure: Error { case unsupportedArchive, malformedImage, existingDisk, insufficientSpace }
    private static let diskBytes: UInt64 = 16 << 30
    private static let memberHeader: UInt64 = 154_122_511
    private static let memberBytes: UInt64 = 4_813_157_696

    public static func convert(archive: URL, destination: URL,
                               progress: @Sendable (Double) -> Void = { _ in }) throws {
        let manager = FileManager.default
        guard !manager.fileExists(atPath: destination.path) else { throw Failure.existingDisk }
        let input = try FileHandle(forReadingFrom: archive)
        defer { try? input.close() }
        func read(_ offset: UInt64, _ count: Int) throws -> Data {
            guard count >= 0, count <= 8 << 20, offset <= 5_013_514_038,
                  UInt64(count) <= 5_013_514_038 - offset else { throw Failure.malformedImage }
            try input.seek(toOffset: offset)
            guard let data = try input.read(upToCount: count), data.count == count else { throw Failure.malformedImage }
            return data
        }
        guard try input.seekToEnd() == 5_013_514_038 else { throw Failure.unsupportedArchive }
        let local = try read(memberHeader, 30)
        guard little(local, 0, 4) == 0x04034b50, little(local, 8, 2) == 0,
              little(local, 6, 2) & 1 == 0 else { throw Failure.unsupportedArchive }
        let nameLength = Int(little(local, 26, 2)), extraLength = little(local, 28, 2)
        guard nameLength > 0, nameLength < 256,
              try read(memberHeader + 30, nameLength) == Data("098-68748-067.dmg".utf8) else {
            throw Failure.unsupportedArchive
        }
        let start = memberHeader + 30 + UInt64(nameLength) + extraLength
        let footer = try read(start + memberBytes - 512, 512)
        guard footer.prefix(4) == Data("koly".utf8), big(footer, 4, 4) == 4,
              big(footer, 8, 4) == 512, big(footer, 60, 4) == 1 else { throw Failure.malformedImage }
        let dataStart = big(footer, 24, 8), dataLength = big(footer, 32, 8)
        let xmlStart = big(footer, 216, 8), xmlLength = big(footer, 224, 8)
        guard xmlLength > 0, xmlLength <= 8 << 20, xmlStart < memberBytes - 512,
              xmlLength <= memberBytes - 512 - xmlStart,
              dataStart <= memberBytes, dataLength <= memberBytes - dataStart else { throw Failure.malformedImage }
        let plist = try PropertyListSerialization.propertyList(from: read(start + xmlStart, Int(xmlLength)), options: [], format: nil)
        guard let dictionary = plist as? [String: Any], let resources = dictionary["resource-fork"] as? [String: Any],
              let tables = resources["blkx"] as? [[String: Any]], !tables.isEmpty, tables.count <= 128 else {
            throw Failure.malformedImage
        }
        struct Block { let kind: UInt64; let output: UInt64; let size: Int; let input: UInt64; let compressed: Int }
        var blocks: [Block] = []
        for table in tables {
            guard let bytes = table["Data"] as? Data, bytes.count >= 204, bytes.prefix(4) == Data("mish".utf8) else {
                throw Failure.malformedImage
            }
            let partitionSector = big(bytes, 8, 8), base = big(bytes, 24, 8), count = big(bytes, 200, 4)
            guard count <= 100_000, count * 40 <= UInt64(bytes.count - 204), base <= dataLength else { throw Failure.malformedImage }
            for index in 0..<Int(count) {
                let offset = 204 + index * 40, kind = big(bytes, offset, 4)
                if kind == 0xffffffff { continue }
                guard [0, 1, 2, 0x80000007].contains(kind) else { throw Failure.malformedImage }
                let sector = big(bytes, offset + 8, 8), sectors = big(bytes, offset + 16, 8)
                let compressedOffset = big(bytes, offset + 24, 8), compressedSize = big(bytes, offset + 32, 8)
                guard partitionSector <= diskBytes / 512, sector <= diskBytes / 512 - partitionSector,
                      sectors <= diskBytes / 512 - partitionSector - sector,
                      compressedOffset <= dataLength - base, compressedSize <= dataLength - base - compressedOffset else { throw Failure.malformedImage }
                let size = sectors * 512
                if kind == 1 && size != compressedSize { throw Failure.malformedImage }
                if kind == 0x80000007 && (size == 0 || compressedSize == 0 || size > 8 << 20 || compressedSize > 8 << 20) { throw Failure.malformedImage }
                blocks.append(Block(kind: kind, output: (partitionSector + sector) * 512, size: Int(size),
                                    input: start + dataStart + base + compressedOffset, compressed: Int(compressedSize)))
            }
        }
        // Check all metadata before creating a disk. Write into a new staging
        // file; a decode error never replaces an existing VM or leaves a ready disk.
        let capacity = try destination.deletingLastPathComponent().resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        guard (capacity.volumeAvailableCapacityForImportantUsage ?? 0) > Int64(diskBytes) else { throw Failure.insufficientSpace }
        let temporary = destination.deletingLastPathComponent().appendingPathComponent("disk-\(UUID().uuidString).partial")
        guard manager.createFile(atPath: temporary.path, contents: nil) else { throw Failure.malformedImage }
        do {
            let output = try FileHandle(forUpdating: temporary)
            defer { try? output.close() }
            try output.truncate(atOffset: diskBytes)
            for (index, block) in blocks.enumerated() {
                if block.kind == 1 {
                    var offset = 0
                    while offset < block.size {
                        let chunk = try read(block.input + UInt64(offset), min(8 << 20, block.size - offset))
                        if chunk.contains(where: { $0 != 0 }) {
                            try output.seek(toOffset: block.output + UInt64(offset)); try output.write(contentsOf: chunk)
                        }
                        offset += chunk.count
                    }
                } else if block.kind == 0x80000007 {
                    let encoded = try read(block.input, block.compressed)
                    let decoded: Data
                    do {
                        var buffer = Data(count: block.size)
                        let count = buffer.withUnsafeMutableBytes { target in
                            encoded.withUnsafeBytes { source in
                                compression_decode_buffer(target.bindMemory(to: UInt8.self).baseAddress!, block.size,
                                    source.bindMemory(to: UInt8.self).baseAddress!, encoded.count, nil, COMPRESSION_LZFSE)
                            }
                        }
                        guard count == block.size else { throw Failure.malformedImage }
                        decoded = buffer
                    }
                    if decoded.contains(where: { $0 != 0 }) {
                        try output.seek(toOffset: block.output); try output.write(contentsOf: decoded)
                    }
                }
                progress(Double(index + 1) / Double(blocks.count))
            }
            try output.synchronize()
            // GPT relocation and APFS install roles are a following stage.
            try manager.moveItem(at: temporary, to: destination)
        } catch {
            try? manager.removeItem(at: temporary); throw error
        }
    }

    private static func big(_ data: Data, _ offset: Int, _ count: Int) -> UInt64 {
        data[offset..<(offset + count)].reduce(0) { ($0 << 8) | UInt64($1) }
    }
    private static func little(_ data: Data, _ offset: Int, _ count: Int) -> UInt64 {
        data[offset..<(offset + count)].reversed().reduce(0) { ($0 << 8) | UInt64($1) }
    }
}

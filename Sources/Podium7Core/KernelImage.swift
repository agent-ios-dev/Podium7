import Foundation

public enum KernelImageError: Error { case invalid(String) }

/// Mach-O virtual-address probe space. Not an A10 physical bus or an MMU.
public final class KernelProbeMemory: Memory64 {
    private struct Region { let base: UInt64; let size: UInt64; let data: Data }
    private var regions: [Region] = []
    private var writes: [UInt64: UInt8] = [:]
    public init() {}
    public func map(base: UInt64, size: UInt64, data: Data) throws {
        guard size > 0, size <= 2 * 1024 * 1024 * 1024, UInt64(data.count) <= size,
              base <= UInt64.max - size,
              regions.allSatisfy({ base >= $0.base + $0.size || $0.base >= base + size }) else {
            throw KernelImageError.invalid("invalid/overlapping segment")
        }
        regions.append(Region(base: base, size: size, data: data))
    }
    public func read(_ address: UInt64) throws -> UInt8 {
        guard let region = regions.first(where: { address >= $0.base && address - $0.base < $0.size }) else {
            throw MachineFault.unmapped(address)
        }
        if let value = writes[address] { return value }
        let offset = address - region.base
        return offset < UInt64(region.data.count) ? region.data[Int(offset)] : 0
    }
    public func write(_ address: UInt64, value: UInt8) throws {
        _ = try read(address)
        writes[address] = value
    }
}

public struct KernelImage {
    public let memory: KernelProbeMemory
    public let entry: UInt64
    public init(data: Data) throws {
        func integer(_ offset: Int, _ size: Int) throws -> UInt64 {
            guard offset >= 0, size <= data.count, offset <= data.count - size else {
                throw KernelImageError.invalid("truncated Mach-O integer")
            }
            var value: UInt64 = 0
            for i in 0..<size { value |= UInt64(data[offset + i]) << (8 * i) }
            return value
        }
        guard try integer(0, 4) == 0xfeedfacf, try integer(4, 4) == 0x100000c else {
            throw KernelImageError.invalid("expected ARM64 Mach-O")
        }
        let count = Int(try integer(16, 4)), commandBytes = Int(try integer(20, 4))
        guard count <= 10000, data.count >= 32, commandBytes <= data.count - 32 else {
            throw KernelImageError.invalid("load command bounds")
        }
        let memory = KernelProbeMemory()
        var cursor = 32, entry: UInt64?
        for _ in 0..<count {
            guard cursor <= 32 + commandBytes - 8 else { throw KernelImageError.invalid("missing command") }
            let command = try integer(cursor, 4), size = Int(try integer(cursor + 4, 4))
            guard size >= 8, size <= 32 + commandBytes - cursor else { throw KernelImageError.invalid("command size") }
            if command == 0x19 {
                guard size >= 72 else { throw KernelImageError.invalid("segment size") }
                let address = try integer(cursor + 24, 8), length = try integer(cursor + 32, 8)
                let offset = try integer(cursor + 40, 8), fileSize = try integer(cursor + 48, 8)
                guard offset <= UInt64(data.count), fileSize <= UInt64(data.count) - offset else {
                    throw KernelImageError.invalid("segment file bounds")
                }
                if length != 0 {
                    try memory.map(base: address, size: length,
                        data: data.subdata(in: Int(offset)..<Int(offset + fileSize)))
                } else if fileSize != 0 { throw KernelImageError.invalid("nonempty zero-length segment") }
            } else if command == 5 {
                guard size >= 288, try integer(cursor + 8, 4) == 6, try integer(cursor + 12, 4) == 68 else {
                    throw KernelImageError.invalid("unsupported ARM64 thread state")
                }
                entry = try integer(cursor + 272, 8)
            }
            cursor += size
        }
        guard cursor == 32 + commandBytes, let entry, entry & 3 == 0 else {
            throw KernelImageError.invalid("missing/alignment-invalid kernel entry")
        }
        for i in 0..<4 { _ = try memory.read(entry + UInt64(i)) }
        self.memory = memory; self.entry = entry
    }
}

import Foundation
import NativeJIT

public enum JITError: Error { case unavailable(Int32) }

/// Compiles only whitelisted register arithmetic; all guest memory stays in Swift.
/// One preallocated pool per backend, immutable native blocks, no guest code copied verbatim.
public final class AArch64BlockJIT {
    private let pool: OpaquePointer
    private struct Block { let words: [UInt32]; let code: UnsafeMutableRawPointer }
    private var blocks: [UInt64: Block] = [:]
    public private(set) var executedInstructions: UInt64 = 0
    public init(capacity: Int = 1 << 20) throws {
        guard capacity > 0 else { throw JITError.unavailable(22) }
        var error: Int32 = 0
        guard let pool = p7_jit_create(capacity, &error) else { throw JITError.unavailable(error) }
        self.pool = pool
    }
    deinit { p7_jit_destroy(pool) }
    private func translation(_ word: UInt32) -> [UInt32]? {
        let rd = word & 31, rn = (word >> 5) & 31
        if word == 0xd503201f { return [] }
        let kind = word & 0x7f800000
        if kind == 0x52800000 || kind == 0x72800000 {
            guard word >> 31 != 0 || (word >> 21) & 3 < 2 else { return nil }
            if rd == 31 { return [] }
            var native: [UInt32] = []
            if kind == 0x72800000 { native.append(0xf9400009 | (rd << 10)) }
            native.append((word & ~UInt32(31)) | 9)
            native.append(0xf9000009 | (rd << 10))
            return native
        }
        if word & 0x1f800000 == 0x11000000 && word & 0x20000000 == 0 && rd != 31 && rn != 31 {
            return [0xf9400009 | (rn << 10), (word & ~UInt32(0x3ff)) | (9 << 5) | 9, 0xf9000009 | (rd << 10)]
        }
        return nil
    }
    func execute(memory: any Memory64, pc: UInt64, registers: inout [UInt64], limit: Int) -> Int {
        var words: [UInt32] = [], code: [UInt32] = []
        for index in 0..<min(max(0, limit), 64) {
            var word: UInt32 = 0
            do { for byte in 0..<4 { word |= UInt32(try memory.read(pc &+ UInt64(index * 4 + byte))) << (byte * 8) } }
            catch { break }
            guard let translated = translation(word) else { break }
            words.append(word); code.append(contentsOf: translated)
        }
        guard !words.isEmpty else { return 0 }
        let block: Block
        // Revalidate guest words on every entry so self-modifying code never uses stale native code.
        if let cached = blocks[pc], cached.words == words { block = cached }
        else {
            code.append(0xd65f03c0)
            guard let native = code.withUnsafeBufferPointer({ p7_jit_emit(pool, $0.baseAddress, $0.count) }) else { return 0 }
            block = Block(words: words, code: native); blocks[pc] = block
        }
        registers.withUnsafeMutableBufferPointer { p7_jit_call(block.code, $0.baseAddress) }
        executedInstructions &+= UInt64(words.count)
        return words.count
    }
}

public enum JITAvailability {
    public static var debuggerAttached: Bool { p7_debugged() }
    public static var taskAllowed: Bool { p7_get_task_allow() }
    public static var txmPresence: Int32 { Int32(p7_txm_presence()) }
}

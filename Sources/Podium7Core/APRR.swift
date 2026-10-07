/// Research permission decoder derived from Siguza's hardware experiments.
/// Not yet connected to page-table walks; register storage alone is not APRR.
public struct APRRPermissions: Equatable {
    public let read: Bool
    public let write: Bool
    public let execute: Bool
    public init(register: UInt64, ap: UInt8, pxn: Bool, uxn: Bool) {
        let index = Int(ap & 3) * 4 + (pxn ? 2 : 0) + (uxn ? 1 : 0)
        let bits = (register >> (index * 4)) & 7
        self.read = bits & 4 != 0
        self.write = bits & 2 != 0
        self.execute = bits & 1 != 0
    }
}

/// Opt-in latch experiment. No permission enforcement; unknown controls trap.
public final class APRRResearchRegisters {
    private var values: [UInt32: UInt64] = [0: 0, 1: 0, 6: 0, 7: 0]
    public init() {}
    public func read(_ number: UInt32) -> UInt64? { values[number] }
    @discardableResult public func write(_ number: UInt32, value: UInt64) -> Bool {
        guard values[number] != nil else { return false }
        values[number] = value
        return true
    }
}

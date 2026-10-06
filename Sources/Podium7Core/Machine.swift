import Foundation

public enum MachineFault: Error, Equatable {
    case unmapped(UInt64), unalignedPC(UInt64), unsupported(pc: UInt64, opcode: UInt32), budgetExceeded
}

/// Development board only. These are synthetic addresses, not an A10 memory map.
public final class LabMemory {
    public static let ramBase: UInt64 = 0x1_0000_0000
    public static let uart: UInt64 = 0x2_0000_0000
    private var bytes: [UInt8]
    public private(set) var serial = ""
    public init(size: Int = 65536) { precondition(size > 0); bytes = .init(repeating: 0, count: size) }
    public func read(_ address: UInt64) throws -> UInt8 {
        guard address >= Self.ramBase, address - Self.ramBase < UInt64(bytes.count) else { throw MachineFault.unmapped(address) }
        return bytes[Int(address - Self.ramBase)]
    }
    public func write(_ address: UInt64, value: UInt8) throws {
        if address == Self.uart { serial += String(UnicodeScalar(value)); return }
        guard address >= Self.ramBase, address - Self.ramBase < UInt64(bytes.count) else { throw MachineFault.unmapped(address) }
        bytes[Int(address - Self.ramBase)] = value
    }
    public func load(_ words: [UInt32], at address: UInt64 = LabMemory.ramBase) throws {
        // Validate the entire image before mutating memory.
        guard address >= Self.ramBase, address - Self.ramBase <= UInt64(bytes.count),
              words.count <= (bytes.count - Int(address - Self.ramBase)) / 4 else { throw MachineFault.unmapped(address) }
        for (i, word) in words.enumerated() {
            for j in 0..<4 { try write(address + UInt64(i * 4 + j), value: UInt8(truncatingIfNeeded: word >> (j * 8))) }
        }
    }
}

/// Small AArch64 interpreter: no MMU, exception levels, SIMD or A10 peripherals yet.
public final class AArch64CPU {
    public private(set) var registers = [UInt64](repeating: 0, count: 31)
    public private(set) var pc = LabMemory.ramBase
    public private(set) var sp: UInt64 = 0
    public private(set) var retired: UInt64 = 0
    public private(set) var stopped = false
    public let memory: LabMemory
    public init(memory: LabMemory) { self.memory = memory }
    private func reg(_ index: Int) -> UInt64 { index == 31 ? 0 : registers[index] }
    private func set(_ index: Int, _ value: UInt64, wide: Bool) {
        if index != 31 { registers[index] = wide ? value : value & 0xffff_ffff }
    }
    private func signed(_ value: UInt32, bits: Int) -> Int64 {
        let shift = 64 - bits
        return Int64(bitPattern: UInt64(value) << shift) >> shift
    }
    public func step() throws {
        guard !stopped else { return }
        guard pc & 3 == 0 else { throw MachineFault.unalignedPC(pc) }
        var op: UInt32 = 0
        for i in 0..<4 { op |= UInt32(try memory.read(pc &+ UInt64(i))) << (i * 8) }
        let rd = Int(op & 31), rn = Int((op >> 5) & 31), wide = op >> 31 != 0
        var next = pc &+ 4
        switch op {
        case 0xd503201f: break // NOP
        case 0xd4200000: stopped = true // BRK #0 is the lab's explicit stop convention.
        default:
            if op & 0x7f800000 == 0x52800000 || op & 0x7f800000 == 0x72800000 {
                let shift = Int((op >> 21) & 3) * 16
                guard wide || shift < 32 else { throw MachineFault.unsupported(pc: pc, opcode: op) }
                let immediate = UInt64((op >> 5) & 0xffff) << shift
                let keep = op & 0x7f800000 == 0x72800000
                set(rd, keep ? (reg(rd) & ~(UInt64(0xffff) << shift)) | immediate : immediate, wide: wide)
            } else if op & 0x1f800000 == 0x11000000 && op & 0x20000000 == 0 {
                // ADD/SUB immediate, without flags. Register 31 denotes SP here.
                let immediate = UInt64((op >> 10) & 0xfff) << (op & 0x00400000 == 0 ? 0 : 12)
                let source = rn == 31 ? sp : reg(rn)
                var value = op & 0x40000000 == 0 ? source &+ immediate : source &- immediate
                if !wide { value &= 0xffff_ffff }
                if rd == 31 { sp = value } else { set(rd, value, wide: wide) }
            } else if op & 0xfc000000 == 0x14000000 {
                next = pc &+ UInt64(bitPattern: signed(op & 0x03ff_ffff, bits: 26) * 4)
            } else if op & 0x7e000000 == 0x34000000 {
                let value = wide ? reg(rd) : reg(rd) & 0xffff_ffff
                if (value == 0) == (op & 0x01000000 == 0) {
                    next = pc &+ UInt64(bitPattern: signed((op >> 5) & 0x7ffff, bits: 19) * 4)
                }
            } else if op & 0xffc00000 == 0x39000000 {
                let base = rn == 31 ? sp : reg(rn)
                try memory.write(base &+ UInt64((op >> 10) & 0xfff), value: UInt8(truncatingIfNeeded: reg(rd)))
            } else if op & 0xffc00000 == 0x39400000 {
                let base = rn == 31 ? sp : reg(rn)
                set(rd, UInt64(try memory.read(base &+ UInt64((op >> 10) & 0xfff))), wide: false)
            } else { throw MachineFault.unsupported(pc: pc, opcode: op) }
        }
        pc = next; retired &+= 1
    }
    public func run(budget: Int = 10000) throws {
        for _ in 0..<max(0, budget) { if stopped { return }; try step() }
        if !stopped { throw MachineFault.budgetExceeded }
    }
}

public enum DiagnosticROM {
    public static func words() -> [UInt32] {
        // MOVZ X1, #2, LSL #32 -> synthetic UART at 0x200000000.
        var code: [UInt32] = [0xd2c00041]
        for byte in "Podium7 ARM64 OK\n".utf8 {
            code += [0x52800000 | (UInt32(byte) << 5), 0x39000020] // MOVZ W0; STRB W0,[X1]
        }
        return code + [0xd4200000]
    }
    public static func execute() throws -> (output: String, instructions: UInt64) {
        let memory = LabMemory(); try memory.load(words())
        let cpu = AArch64CPU(memory: memory); try cpu.run()
        return (memory.serial, cpu.retired)
    }
}

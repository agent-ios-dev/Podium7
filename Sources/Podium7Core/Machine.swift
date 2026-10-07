import Foundation

public enum MachineFault: Error, Equatable {
    case unmapped(UInt64), unalignedPC(UInt64), unsupported(pc: UInt64, opcode: UInt32), budgetExceeded
}

public protocol Memory64: AnyObject {
    func read(_ address: UInt64) throws -> UInt8
    func write(_ address: UInt64, value: UInt8) throws
}

/// Development board only. These are synthetic addresses, not an A10 memory map.
public final class LabMemory: Memory64 {
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
    public private(set) var debugOSLock = true
    public private(set) var interruptMask: UInt8 = 0
    public private(set) var vectorBase: UInt64 = 0
    public private(set) var negative = false
    public private(set) var zero = false
    public private(set) var carry = false
    public private(set) var overflow = false
    public let memory: any Memory64
    public let researchAPRR: APRRResearchRegisters?
    public var jit: AArch64BlockJIT?
    public init(memory: any Memory64, entry: UInt64 = LabMemory.ramBase, researchAPRR: APRRResearchRegisters? = nil) {
        self.memory = memory; self.pc = entry; self.researchAPRR = researchAPRR
    }
    private func reg(_ index: Int) -> UInt64 { index == 31 ? 0 : registers[index] }
    private func set(_ index: Int, _ value: UInt64, wide: Bool) {
        if index != 31 { registers[index] = wide ? value : value & 0xffff_ffff }
    }
    private func signed(_ value: UInt32, bits: Int) -> Int64 {
        let shift = 64 - bits
        return Int64(bitPattern: UInt64(value) << shift) >> shift
    }
    private func arithmetic(_ a: UInt64, _ b: UInt64, subtract: Bool, wide: Bool, flags: Bool) -> UInt64 {
        let mask = wide ? UInt64.max : 0xffff_ffff
        let left = a & mask, right = b & mask
        let result = (subtract ? left &- right : left &+ right) & mask
        if flags {
            let sign: UInt64 = wide ? 1 << 63 : 1 << 31
            negative = result & sign != 0; zero = result == 0
            carry = subtract ? left >= right : (wide ? left.addingReportingOverflow(right).overflow : left + right > mask)
            overflow = ((subtract ? left ^ right : ~(left ^ right)) & (left ^ result) & sign) != 0
        }
        return result
    }
    private func condition(_ condition: UInt32) -> Bool {
        let result: Bool
        switch condition >> 1 {
        case 0: result = zero
        case 1: result = carry
        case 2: result = negative
        case 3: result = overflow
        case 4: result = carry && !zero
        case 5: result = negative == overflow
        case 6: result = !zero && negative == overflow
        default: return true
        }
        return condition & 1 == 0 ? result : !result
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
            if op & 0xffdfff00 == 0xd51cf200, let researchAPRR {
                let number = (op >> 5) & 7
                guard let value = researchAPRR.read(number) else { throw MachineFault.unsupported(pc: pc, opcode: op) }
                if op & 0x00200000 != 0 { set(rd, value, wide: true) }
                else { researchAPRR.write(number, value: reg(rd)) }
            } else if op & 0xffffffe0 == 0xd5101080 { // MSR OSLAR_EL1, Xt
                debugOSLock = reg(rd) & 1 != 0
            } else if op & 0xfffff0ff == 0xd50340df { // MSR DAIFSet, #imm
                interruptMask |= UInt8((op >> 8) & 15)
            } else if op & 0xfffff0ff == 0xd50340ff { // MSR DAIFClr, #imm
                interruptMask &= ~UInt8((op >> 8) & 15)
            } else if op & 0xffffffe0 == 0xd518c000 { // MSR VBAR_EL1, Xt
                vectorBase = reg(rd) & ~UInt64(0x7ff)
            } else if op & 0x9f000000 == 0x10000000 || op & 0x9f000000 == 0x90000000 {
                let immediate = ((op >> 5) & 0x7ffff) << 2 | ((op >> 29) & 3)
                let page = op & 0x80000000 != 0
                let delta = signed(immediate, bits: 21) * (page ? 4096 : 1)
                set(rd, (page ? pc & ~UInt64(4095) : pc) &+ UInt64(bitPattern: delta), wide: true)
            } else if op & 0x7fe0ffe0 == 0x2a0003e0 { // MOV alias: ORR Rd, ZR, Rm (LSL #0)
                set(rd, reg(Int((op >> 16) & 31)), wide: wide)
            } else if op & 0xfffffc1f == 0xd61f0000 || op & 0xfffffc1f == 0xd63f0000 || op & 0xfffffc1f == 0xd65f0000 {
                next = reg(rn)
                if op & 0xfffffc1f == 0xd63f0000 { set(30, pc &+ 4, wide: true) }
            } else if op & 0xffc00000 == 0xf9400000 || op & 0xffc00000 == 0xb9400000 {
                let size = op >> 30 == 3 ? 8 : 4
                let base = rn == 31 ? sp : reg(rn)
                let address = base &+ UInt64((op >> 10) & 0xfff) * UInt64(size)
                var value: UInt64 = 0
                for i in 0..<size { value |= UInt64(try memory.read(address &+ UInt64(i))) << (8 * i) }
                set(rd, value, wide: size == 8)
            } else if op & 0xff000010 == 0x54000000 {
                if condition(op & 15) { next = pc &+ UInt64(bitPattern: signed((op >> 5) & 0x7ffff, bits: 19) * 4) }
            } else if op & 0x7e000000 == 0x36000000 {
                let bit = ((op >> 19) & 31) | ((op >> 26) & 32)
                if (reg(rd) & (UInt64(1) << bit) == 0) == (op & 0x01000000 == 0) {
                    next = pc &+ UInt64(bitPattern: signed((op >> 5) & 0x3fff, bits: 14) * 4)
                }
            } else if op & 0x1f200000 == 0x0b000000 {
                let shift = (op >> 22) & 3, amount = (op >> 10) & 63
                guard shift < 3, wide || amount < 32 else { throw MachineFault.unsupported(pc: pc, opcode: op) }
                var value = reg(Int((op >> 16) & 31)) & (wide ? UInt64.max : 0xffff_ffff)
                if shift == 0 { value <<= amount }
                else if shift == 1 { value >>= amount }
                else if wide { value = UInt64(bitPattern: Int64(bitPattern: value) >> amount) }
                else { value = UInt64(UInt32(bitPattern: Int32(bitPattern: UInt32(value)) >> amount)) }
                set(rd, arithmetic(reg(rn), value, subtract: op & 0x40000000 != 0, wide: wide, flags: op & 0x20000000 != 0), wide: wide)
            } else if op & 0x7f800000 == 0x52800000 || op & 0x7f800000 == 0x72800000 {
                let shift = Int((op >> 21) & 3) * 16
                guard wide || shift < 32 else { throw MachineFault.unsupported(pc: pc, opcode: op) }
                let immediate = UInt64((op >> 5) & 0xffff) << shift
                let keep = op & 0x7f800000 == 0x72800000
                set(rd, keep ? (reg(rd) & ~(UInt64(0xffff) << shift)) | immediate : immediate, wide: wide)
            } else if op & 0x1f800000 == 0x11000000 {
                // Register 31 is SP as a source, and ZR as a flag-setting destination.
                let immediate = UInt64((op >> 10) & 0xfff) << (op & 0x00400000 == 0 ? 0 : 12)
                let source = rn == 31 ? sp : reg(rn)
                let flags = op & 0x20000000 != 0
                let value = arithmetic(source, immediate, subtract: op & 0x40000000 != 0, wide: wide, flags: flags)
                if rd == 31 && !flags { sp = value } else { set(rd, value, wide: wide) }
            } else if op & 0x7c000000 == 0x14000000 {
                next = pc &+ UInt64(bitPattern: signed(op & 0x03ff_ffff, bits: 26) * 4)
                if op & 0x80000000 != 0 { set(30, pc &+ 4, wide: true) }
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
        let start = retired
        while retired - start < UInt64(max(0, budget)) {
            if stopped { return }
            if let jit, pc & 3 == 0 {
                let count = jit.execute(memory: memory, pc: pc, registers: &registers, limit: max(0, budget) - Int(retired - start))
                if count > 0 { pc &+= UInt64(count * 4); retired &+= UInt64(count); continue }
            }
            try step()
        }
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
    public static func execute(jit: AArch64BlockJIT? = nil) throws -> (output: String, instructions: UInt64) {
        let memory = LabMemory(); try memory.load(words())
        let cpu = AArch64CPU(memory: memory); cpu.jit = jit; try cpu.run()
        return (memory.serial, cpu.retired)
    }
}

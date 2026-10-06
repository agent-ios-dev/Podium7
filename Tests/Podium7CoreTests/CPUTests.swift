import XCTest
@testable import Podium7Core

final class CPUTests: XCTestCase {
    func cpu(_ words: [UInt32]) throws -> AArch64CPU {
        let memory = LabMemory(); try memory.load(words); return AArch64CPU(memory: memory)
    }
    func testROMExecutesThroughUART() throws {
        let result = try DiagnosticROM.execute()
        XCTAssertEqual(result.output, "Podium7 ARM64 OK\n")
        XCTAssertEqual(result.instructions, 36)
    }
    func testMoveKeepAndWRegisterClearsUpperBits() throws {
        let c = try cpu([0xd2c00040, 0xf2800020, 0x528000e0, 0xd4200000])
        try c.step(); XCTAssertEqual(c.registers[0], 0x2_0000_0000)
        try c.step(); XCTAssertEqual(c.registers[0], 0x2_0000_0001)
        try c.step(); XCTAssertEqual(c.registers[0], 7)
    }
    func testSPAndZeroRegisterAreDistinct() throws {
        let c = try cpu([0xd280003f, 0x910043ff, 0x910003e0, 0xd4200000])
        try c.run(); XCTAssertEqual(c.sp, 16); XCTAssertEqual(c.registers[0], 16)
    }
    func testBackwardBranchAndSubtraction() throws {
        let c = try cpu([0xd2800060, 0xd1000400, 0xb5ffffe0, 0xd4200000])
        try c.run(); XCTAssertEqual(c.registers[0], 0); XCTAssertEqual(c.retired, 8)
    }
    func testBranchSkipsInstruction() throws {
        let c = try cpu([0x14000002, 0xffffffff, 0xd4200000])
        try c.run(); XCTAssertEqual(c.retired, 2)
    }
    func testByteMemoryRoundTripAboveFourGiB() throws {
        // Keep data at +0x100, outside the instruction stream.
        let c = try cpu([0xd2c00021, 0x52800aa0, 0x39040020, 0x39440022, 0xd4200000])
        try c.run(); XCTAssertEqual(c.registers[2], 85)
    }
    func testUnknownOpcodeDoesNotAdvancePC() throws {
        let c = try cpu([0xffffffff])
        XCTAssertThrowsError(try c.step()) {
            XCTAssertEqual($0 as? MachineFault, .unsupported(pc: LabMemory.ramBase, opcode: 0xffffffff))
        }
        XCTAssertEqual(c.retired, 0); XCTAssertEqual(c.pc, LabMemory.ramBase)
    }
    func testReserved32BitMoveIsRejected() throws {
        let c = try cpu([0x52c00000]); XCTAssertThrowsError(try c.step())
    }
    func testInfiniteLoopIsBounded() throws {
        let c = try cpu([0x14000000])
        XCTAssertThrowsError(try c.run(budget: 5)) { XCTAssertEqual($0 as? MachineFault, .budgetExceeded) }
        XCTAssertEqual(c.retired, 5)
    }
    func testMemoryBoundaryAndAtomicLoad() throws {
        let memory = LabMemory(size: 4)
        try memory.load([0xd503201f])
        XCTAssertThrowsError(try memory.load([0, 0]))
        XCTAssertEqual(try memory.read(LabMemory.ramBase), 0x1f)
        XCTAssertThrowsError(try memory.read(LabMemory.ramBase - 1))
        XCTAssertThrowsError(try memory.write(LabMemory.ramBase + 4, value: 0))
    }
}

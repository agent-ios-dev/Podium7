import XCTest
@testable import Podium7Core

final class FlagsTests: XCTestCase {
    func testSignedOverflowOnAdd64() throws {
        let m = LabMemory()
        try m.load([0xd2efffe0, 0xf2dfffe0, 0xf2bfffe0, 0xf29fffe0, 0xb1000401, 0xd4200000])
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.registers[1], 0x8000000000000000)
        XCTAssertTrue(cpu.negative); XCTAssertTrue(cpu.overflow)
        XCTAssertFalse(cpu.zero); XCTAssertFalse(cpu.carry)
    }
    func testSubtractionBorrowAndEquality() throws {
        let m = LabMemory()
        try m.load([0x71000400, 0x6b00001f, 0xd4200000])
        let cpu = AArch64CPU(memory: m)
        try cpu.step()
        XCTAssertEqual(cpu.registers[0], 0xffffffff)
        XCTAssertTrue(cpu.negative); XCTAssertFalse(cpu.carry); XCTAssertFalse(cpu.overflow)
        try cpu.step()
        XCTAssertTrue(cpu.zero); XCTAssertTrue(cpu.carry); XCTAssertFalse(cpu.negative)
    }
    func testConditionalBackwardLoop() throws {
        let m = LabMemory()
        try m.load([0xd2800060, 0xf1000400, 0x54ffffe1, 0xd4200000])
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.registers[0], 0); XCTAssertEqual(cpu.retired, 8)
    }
    func testTestBitBranch() throws {
        let m = LabMemory()
        try m.load([0xd2800020, 0x37000040, 0xffffffff, 0xd4200000])
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.retired, 3)
    }
}

import XCTest
@testable import Podium7Core

final class BootstrapTests: XCTestCase {
    func testEarlySystemRegisterStateChanges() throws {
        let m = LabMemory()
        try m.load([0xd510109f, 0xd5034fdf, 0xd50343ff, 0xd2802000, 0xd518c000, 0xd4200000])
        let cpu = AArch64CPU(memory: m)
        try cpu.run()
        XCTAssertFalse(cpu.debugOSLock)
        XCTAssertEqual(cpu.interruptMask, 12)
        XCTAssertEqual(cpu.vectorBase, 0x1000)
    }
    func testADRPPageAndSignedADR() throws {
        let m = LabMemory()
        try m.load([0x90000000, 0x10ffffe1, 0xd4200000])
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.registers[0], LabMemory.ramBase)
        XCTAssertEqual(cpu.registers[1], LabMemory.ramBase)
    }
    func testLinkBranchAndReturn() throws {
        let m = LabMemory()
        try m.load([0x94000002, 0xd4200000, 0xd28000e0, 0xd65f03c0])
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.registers[0], 7)
        XCTAssertEqual(cpu.registers[30], LabMemory.ramBase + 4)
        XCTAssertEqual(cpu.retired, 4)
    }
    func testMOVAliasAndLDR64() throws {
        let m = LabMemory()
        try m.load([0xd2c00020, 0xaa0003f4, 0xf9408296, 0xd4200000])
        try m.load([0x44332211, 0x88776655], at: LabMemory.ramBase + 0x100)
        let cpu = AArch64CPU(memory: m); try cpu.run()
        XCTAssertEqual(cpu.registers[20], LabMemory.ramBase)
        XCTAssertEqual(cpu.registers[22], 0x8877665544332211)
    }
}

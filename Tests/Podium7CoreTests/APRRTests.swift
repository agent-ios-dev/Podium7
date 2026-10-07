import XCTest
@testable import Podium7Core

final class APRRTests: XCTestCase {
    func testAllPermissionIndicesAndBits() {
        for index in 0..<16 {
            for bits in 0..<8 {
                let value = UInt64(bits) << (index * 4)
                let permissions = APRRPermissions(register: value, ap: UInt8(index >> 2), pxn: index & 2 != 0, uxn: index & 1 != 0)
                XCTAssertEqual(permissions.read, bits & 4 != 0)
                XCTAssertEqual(permissions.write, bits & 2 != 0)
                XCTAssertEqual(permissions.execute, bits & 1 != 0)
            }
        }
    }
    func testEL1EL0ControlsAreIndependent() {
        let registers = APRRResearchRegisters()
        XCTAssertTrue(registers.write(1, value: 0x4455405566666677))
        XCTAssertTrue(registers.write(0, value: 0x4545010167670101))
        XCTAssertEqual(registers.read(1), 0x4455405566666677)
        XCTAssertEqual(registers.read(0), 0x4545010167670101)
        XCTAssertFalse(registers.write(2, value: 1))
        XCTAssertNil(registers.read(2))
    }
    func testMSRMRSOptInAndUnknownRegisterTrap() throws {
        let m = LabMemory()
        try m.load([0xd2824680, 0xd51cf220, 0xd53cf221, 0xd4200000])
        let strict = AArch64CPU(memory: m)
        try strict.step()
        XCTAssertThrowsError(try strict.step())
        let research = AArch64CPU(memory: m, researchAPRR: APRRResearchRegisters())
        try research.run()
        XCTAssertEqual(research.registers[1], 0x1234)
        let unknown = LabMemory()
        try unknown.load([0xd51cf240])
        XCTAssertThrowsError(try AArch64CPU(memory: unknown, researchAPRR: APRRResearchRegisters()).step())
    }
}

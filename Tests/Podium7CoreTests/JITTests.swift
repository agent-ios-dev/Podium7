import XCTest
@testable import Podium7Core

final class JITTests: XCTestCase {
    func testStikURLContainsProcessAndExactlyOneConfiguredScript() throws {
        let absent = try StikDebugRequest.url(bundleID: "com.catyuragame.podium7", pid: 123, txm: 0)
        let present = try StikDebugRequest.url(bundleID: "com.catyuragame.podium7", pid: 123, txm: 1)
        XCTAssertFalse(absent.absoluteString.contains("script-name"))
        let query = URLComponents(url: present, resolvingAgainstBaseURL: false)!.queryItems!
        XCTAssertEqual(query.first { $0.name == "bundle-id" }?.value, "com.catyuragame.podium7")
        XCTAssertEqual(query.first { $0.name == "pid" }?.value, "123")
        XCTAssertEqual(query.filter { $0.name == "script-name" }.map(\.value), ["universal.js"])
        XCTAssertThrowsError(try StikDebugRequest.url(bundleID: "x", pid: 123, txm: -1))
    }
    func testNativeBlocksMatchInterpreterAndPreserve32BitSemantics() throws {
        #if arch(arm64)
        let words: [UInt32] = [0xd2c00040, 0xf2800020, 0x528000e0, 0x11001401, 0x51000422, 0xd4200000]
        let memory = LabMemory(); try memory.load(words)
        let reference = AArch64CPU(memory: memory); try reference.run()
        let jit = try AArch64BlockJIT()
        let native = AArch64CPU(memory: memory); native.jit = jit; try native.run()
        XCTAssertEqual(native.registers, reference.registers)
        XCTAssertEqual(native.pc, reference.pc)
        XCTAssertEqual(native.retired, reference.retired)
        XCTAssertEqual(jit.executedInstructions, 5)
        #else
        throw XCTSkip("Native execution requires ARM64 host")
        #endif
    }
    func testSelfModifiedBlockIsRecompiled() throws {
        #if arch(arm64)
        let memory = LabMemory(); try memory.load([0xd2800020, 0xd4200000])
        let jit = try AArch64BlockJIT(capacity: 64)
        let first = AArch64CPU(memory: memory); first.jit = jit; try first.run()
        try memory.load([0xd2800040, 0xd4200000])
        let second = AArch64CPU(memory: memory); second.jit = jit; try second.run()
        XCTAssertEqual(first.registers[0], 1); XCTAssertEqual(second.registers[0], 2)
        #else
        throw XCTSkip("Native execution requires ARM64 host")
        #endif
    }
    func testExhaustedNativePoolFallsBackWithoutDroppingGuestInstructions() throws {
        #if arch(arm64)
        let memory = LabMemory()
        let jit = try AArch64BlockJIT(capacity: 1)
        for value in 0..<1300 {
            try memory.load([0xd2800000 | UInt32(value << 5), 0xd4200000])
            let cpu = AArch64CPU(memory: memory); cpu.jit = jit; try cpu.run()
            XCTAssertEqual(cpu.registers[0], UInt64(value)); XCTAssertEqual(cpu.retired, 2)
        }
        XCTAssertGreaterThan(jit.executedInstructions, 0)
        XCTAssertLessThan(jit.executedInstructions, 1300)
        #else
        throw XCTSkip("Native execution requires ARM64 host")
        #endif
    }
    func testJITRespectsInstructionBudgetAndLeavesUnsupportedOpcodesForInterpreter() throws {
        #if arch(arm64)
        let memory = LabMemory(); try memory.load([0xd2800020, 0x91000400, 0xffffffff])
        let jit = try AArch64BlockJIT()
        let cpu = AArch64CPU(memory: memory); cpu.jit = jit
        XCTAssertThrowsError(try cpu.run(budget: 1)) { XCTAssertEqual($0 as? MachineFault, .budgetExceeded) }
        XCTAssertEqual(cpu.retired, 1); XCTAssertEqual(cpu.registers[0], 1)
        XCTAssertThrowsError(try cpu.run()) { XCTAssertEqual($0 as? MachineFault, .unsupported(pc: LabMemory.ramBase + 8, opcode: 0xffffffff)) }
        XCTAssertEqual(cpu.registers[0], 2)
        #else
        throw XCTSkip("Native execution requires ARM64 host")
        #endif
    }
}

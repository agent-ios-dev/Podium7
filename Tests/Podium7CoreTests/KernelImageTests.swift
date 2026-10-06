import XCTest
@testable import Podium7Core

final class KernelImageTests: XCTestCase {
    func testProbeMemoryZeroFillAndHighAddresses() throws {
        let memory = KernelProbeMemory()
        let base: UInt64 = 0xfffffff007000000
        try memory.map(base: base, size: 0x1000, data: Data([1, 2]))
        XCTAssertEqual(try memory.read(base), 1)
        XCTAssertEqual(try memory.read(base + 100), 0)
        try memory.write(base + 100, value: 42)
        XCTAssertEqual(try memory.read(base + 100), 42)
        XCTAssertThrowsError(try memory.read(base + 0x1000))
        XCTAssertThrowsError(try memory.map(base: base + 1, size: 10, data: Data()))
        XCTAssertThrowsError(try memory.map(base: UInt64.max - 1, size: 4, data: Data()))
    }
    func testKernelLoaderRejectsTruncatedAndWrongArchitectures() {
        for data in [Data(), Data(repeating: 0, count: 32), Data([0xcf, 0xfa, 0xed, 0xfe])] {
            XCTAssertThrowsError(try KernelImage(data: data))
        }
    }
}

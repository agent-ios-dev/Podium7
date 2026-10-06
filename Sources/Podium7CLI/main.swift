import Foundation
import Podium7Core

do {
    if CommandLine.arguments.count == 3 && CommandLine.arguments[1] == "--probe-kernel" {
        let image = try KernelImage(data: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[2])))
        let cpu = AArch64CPU(memory: image.memory, entry: image.entry)
        var fault = "none"
        do { try cpu.run(budget: 10000) } catch { fault = String(describing: error) }
        let report: [String: Any] = ["booted_ios": false, "mode": "Mach-O virtual entry probe; no boot args/MMU/devices",
            "entry": String(image.entry, radix: 16), "pc": String(cpu.pc, radix: 16), "instructions": cpu.retired,
            "fault": fault, "registers": cpu.registers.map { String($0, radix: 16) }]
        let json = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
        print(String(decoding: json, as: UTF8.self))
    } else {
    let result = try DiagnosticROM.execute()
    print(result.output, terminator: "")
    print("Retired: \(result.instructions). Development board; iOS boot is not implemented.")
    }
} catch { fatalError("Emulation failed: \(error)") }

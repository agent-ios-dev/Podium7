import Foundation
import Podium7Core

do {
    let result = try DiagnosticROM.execute()
    print(result.output, terminator: "")
    print("Retired: \(result.instructions). Development board; iOS boot is not implemented.")
} catch { fatalError("Emulation failed: \(error)") }

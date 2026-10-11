// swift-tools-version: 5.9
import PackageDescription

let package = Package(name: "Podium7", platforms: [.macOS(.v13), .iOS(.v17)],
    products: [.library(name: "Podium7Core", targets: ["Podium7Core"]),
               .library(name: "QEMUHost", targets: ["QEMUHost"]),
               .executable(name: "podium7", targets: ["Podium7CLI"])],
    targets: [.target(name: "QEMUHost"),
              .target(name: "NativeJIT", linkerSettings: [.linkedFramework("Security"), .linkedFramework("CoreFoundation")]),
              .target(name: "Podium7Core", dependencies: ["NativeJIT"]),
              .executableTarget(name: "Podium7CLI", dependencies: ["Podium7Core"]),
              .testTarget(name: "Podium7CoreTests", dependencies: ["Podium7Core"])])

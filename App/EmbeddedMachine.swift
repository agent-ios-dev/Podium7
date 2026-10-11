import Foundation
import Darwin
import Podium7Core
import QEMUHost

@MainActor final class EmbeddedMachine: ObservableObject {
    @Published var status = "Импортируй подготовленную папку виртуального iPod."
    @Published var serial = ""
    @Published private(set) var busy = false
    @Published private(set) var running = false
    @Published private(set) var consumed = false
    @Published private(set) var directory: URL?
    private var logs: URL?
    private var polling: Task<Void, Never>?

    var available: Bool {
        Bundle.main.privateFrameworksURL.map {
            FileManager.default.fileExists(atPath: $0.appendingPathComponent("Podium7QEMU.framework/Podium7QEMU").path)
        } ?? false
    }

    init() {
        if let path = UserDefaults.standard.string(forKey: "preparedMachine"),
           let support = try? FileManager.default.url(for: .applicationSupportDirectory,
                        in: .userDomainMask, appropriateFor: nil, create: true) {
            // Store an identifier, not the sandbox's changing absolute path.
            let candidate = support.appendingPathComponent("ImportedMachines").appendingPathComponent(path)
            if (try? BootBundle.read(directory: candidate)) != nil {
                directory = candidate; status = "Подготовленный диск: 16 ГБ."
            }
        }
    }

    func importFolder(_ source: URL) {
        guard !busy, !running, !consumed else { return }
        busy = true; status = "Копирование подготовленного диска…"
        Task {
            do {
                let imported = try await Task.detached { () throws -> URL in
                    let access = source.startAccessingSecurityScopedResource()
                    defer { if access { source.stopAccessingSecurityScopedResource() } }
                    _ = try BootBundle.read(directory: source)
                    let base = try FileManager.default.url(for: .applicationSupportDirectory,
                                in: .userDomainMask, appropriateFor: nil, create: true)
                                .appendingPathComponent("ImportedMachines")
                    try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
                    let destination = base.appendingPathComponent(UUID().uuidString)
                    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
                    do {
                        for name in ["boot.json"] + BootBundle.filenames {
                            try FileManager.default.copyItem(at: source.appendingPathComponent(name),
                                                             to: destination.appendingPathComponent(name))
                        }
                        _ = try BootBundle.read(directory: destination)
                        return destination
                    } catch {
                        try? FileManager.default.removeItem(at: destination)
                        throw error
                    }
                }.value
                directory = imported
                UserDefaults.standard.set(imported.lastPathComponent, forKey: "preparedMachine")
                status = "Образ импортирован. Диск: 16 ГБ."
            } catch { status = "Импорт не выполнен: \(error)" }
            busy = false
        }
    }

    func start() {
        guard !busy, !running, !consumed, let directory else { return }
        do {
            let bundle = try BootBundle.read(directory: directory)
            guard let frameworks = Bundle.main.privateFrameworksURL, available else {
                status = "В этой сборке ещё нет библиотеки QEMU для iPhone."; return
            }
            let framework = frameworks.appendingPathComponent("Podium7QEMU.framework/Podium7QEMU")
            guard p7_backend_load(framework.path) == 0 else {
                status = "Ошибка библиотеки: \(String(cString: p7_backend_error()))"; return
            }
            let logDirectory = directory.appendingPathComponent("Logs-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
            // Darwin UNIX socket paths are limited to 104 bytes. /tmp is the
            // app's sandbox temporary directory; a short path avoids long UUID roots.
            let socket = URL(fileURLWithPath: "/tmp/p7-\(ProcessInfo.processInfo.processIdentifier).sock")
            let arguments = try bundle.arguments(directory: directory, logs: logDirectory, qmp: socket)
            logs = logDirectory; consumed = true; running = true
            status = "QEMU выполняет гостевую систему. Графический вывод ещё разрабатывается."
            polling = Task { [weak self] in
                while !Task.isCancelled {
                    if let data = try? Data(contentsOf: logDirectory.appendingPathComponent("serial.txt")) {
                        self?.serial = String(decoding: data.suffix(65536), as: UTF8.self)
                    }
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
            Task {
                let code = await Task.detached {
                    let strings = arguments.map { strdup($0) }
                    defer { for string in strings { free(string) } }
                    var argv = strings + [nil]
                    return argv.withUnsafeMutableBufferPointer { p7_backend_run(Int32(strings.count), $0.baseAddress!) }
                }.value
                running = false; polling?.cancel()
                status = "QEMU завершился: \(code). Для нового запуска перезапусти приложение."
            }
        } catch { status = "Подготовка запуска не выполнена: \(error)" }
    }

    func stop() {
        guard running else { return }
        Task {
            let result = await Task.detached { p7_backend_stop() }.value
            status = result == 0 ? "Остановка QEMU и запись диска…" : "QEMU ещё инициализируется. Повтори остановку позже."
        }
    }

    var exportedLogs: [URL] {
        guard let logs else { return [] }
        return ["serial.txt", "qemu.txt"].map { logs.appendingPathComponent($0) }
            .filter { FileManager.default.fileExists(atPath: $0.path) }
    }
}

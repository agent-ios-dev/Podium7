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
    private var retainedJIT: AArch64BlockJIT?

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

    func start(jit: AArch64BlockJIT? = nil) {
        guard !busy, !running, !consumed, let directory else { return }
        do {
            let bundle = try BootBundle.read(directory: directory)
            guard let frameworks = Bundle.main.privateFrameworksURL, available else {
                status = "В этой сборке ещё нет библиотеки QEMU для iPhone."; return
            }
            let useJIT = jit != nil
            let name = useJIT ? "Podium7QEMUJIT" : "Podium7QEMU"
            let framework = frameworks.appendingPathComponent("\(name).framework/\(name)")
            guard FileManager.default.fileExists(atPath: framework.path) else {
                status = "В этой сборке отсутствует QEMU с нативным JIT."; return
            }
            guard p7_backend_load(framework.path) == 0 else {
                status = "Ошибка библиотеки: \(String(cString: p7_backend_error()))"; return
            }
            if let jit {
                guard let buffer = jit.qemuBuffers(),
                      p7_backend_set_jit_buffer(buffer.rx, buffer.rw, buffer.size) == 0 else {
                    status = "QEMU не принял исполняемую память StikDebug. Перезапусти приложение."; return
                }
                retainedJIT = jit
            }
            let logDirectory = directory.appendingPathComponent("Logs-\(UUID().uuidString)")
            try FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
            // Absolute /tmp is outside the iOS data-container sandbox.
            // Keep a short filename inside the actual app temporary directory.
            let socket = FileManager.default.temporaryDirectory.appendingPathComponent("p7.sock")
            let arguments = try bundle.arguments(directory: directory, logs: logDirectory, qmp: socket, nativeJIT: useJIT)
            logs = logDirectory; consumed = true; running = true
            status = "Запуск QEMU: \(useJIT ? "нативный TCG JIT" : "TCI без JIT"). Графический вывод ещё разрабатывается."
            polling = Task { [weak self] in
                while !Task.isCancelled {
                    if let file = try? FileHandle(forReadingFrom: logDirectory.appendingPathComponent("serial.txt")) {
                        if let size = try? file.seekToEnd() {
                            try? file.seek(toOffset: size > 65536 ? size - 65536 : 0)
                            if let data = try? file.read(upToCount: 65536) {
                                self?.serial = String(decoding: data, as: UTF8.self)
                            }
                        }
                        try? file.close()
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

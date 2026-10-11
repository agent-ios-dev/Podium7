import SwiftUI
import Podium7Core
import UniformTypeIdentifiers

@main struct Podium7App: App {
    var body: some Scene { WindowGroup { LaboratoryView() } }
}

struct LaboratoryView: View {
    @State private var output = ""
    @State private var disk: VirtualDisk?
    @State private var diskStatus = "Подготовка диска…"
    @StateObject private var jit = JITCoordinator()
    @StateObject private var machine = EmbeddedMachine()
    @StateObject private var firmware = FirmwareDownload()
    @State private var importing = false
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Text("iPod touch 7 · A10").font(.title2.bold())
                Text(machine.available ? "Встроенный QEMU · исследовательский режим" : "Перенос QEMU на iPhone. Библиотека ещё не собрана.")
                Text("Исследовательский образ использует отключённый AKS. SEP и защищённая загрузка не реализованы.").font(.caption)
                Text(machine.status).font(.footnote)
                Text(firmware.status).font(.footnote)
                if firmware.downloading {
                    ProgressView(value: firmware.progress)
                    Button("Отменить загрузку") { firmware.cancel() }
                } else if firmware.archive == nil {
                    Button("Скачать официальную iOS") { firmware.start() }
                        .disabled(machine.running || machine.busy)
                }
                HStack {
                    Button("Импортировать образ") { importing = true }
                        .disabled(machine.busy || machine.consumed)
                    Button("Запустить iOS") { machine.start() }
                        .disabled(!machine.available || machine.directory == nil || machine.busy || machine.consumed)
                }
                if !machine.exportedLogs.isEmpty {
                    ShareLink(items: machine.exportedLogs) { Text("Сохранить логи") }
                }
                if machine.running {
                    Button("Остановить эмуляцию") { machine.stop() }
                    ScrollView { Text(machine.serial).font(.system(.caption, design: .monospaced)).textSelection(.enabled) }
                }
                Text(diskStatus).font(.footnote)
                Text(jit.status).font(.footnote)
                Text("StikDebug сейчас ускоряет ARM64-тест. Подключение JIT к QEMU ещё разрабатывается.").font(.caption)
                HStack {
                    Button("Включить JIT в StikDebug") { jit.requestStikDebug() }
                    Button("Проверить JIT") { jit.prepare() }
                }.disabled(jit.preparing || jit.backend != nil)
                Button("Проверить ARM64") {
                    do {
                        let before = jit.backend?.executedInstructions ?? 0
                        let result = try DiagnosticROM.execute(jit: jit.backend)
                        output = result.output + "Инструкций: \(result.instructions)\nЧерез JIT: \((jit.backend?.executedInstructions ?? 0) - before)"
                    } catch { output = "Ошибка: \(error)" }
                }.buttonStyle(.borderedProminent)
                ScrollView { Text(output).font(.system(.body, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                Spacer()
            }.padding().navigationTitle("Podium7")
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.folder]) { result in
            switch result {
            case .success(let url): machine.importFolder(url)
            case .failure(let error): machine.status = "Импорт: \(error)"
            }
        }
        .task {
            guard disk == nil else { return }
            do {
                let directory = try FileManager.default.url(for: .applicationSupportDirectory,
                    in: .userDomainMask, appropriateFor: nil, create: true)
                    .appendingPathComponent("VirtualMachine", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                disk = try VirtualDisk(url: directory.appendingPathComponent("disk.raw"))
                diskStatus = "Диск: 16 ГБ. Для загрузки нужен импортированный образ iOS."
            } catch { diskStatus = "Ошибка подготовки диска: \(error)" }
        }
        .onChange(of: scenePhase) { _, phase in if phase == .active { jit.returnedToApp() } }
    }
}

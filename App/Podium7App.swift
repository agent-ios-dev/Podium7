import SwiftUI
import Podium7Core

@main struct Podium7App: App {
    var body: some Scene { WindowGroup { LaboratoryView() } }
}

struct LaboratoryView: View {
    @State private var output = ""
    @State private var disk: VirtualDisk?
    @State private var diskStatus = "Подготовка диска…"
    @StateObject private var jit = JITCoordinator()
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Text("iPod touch 7 · A10").font(.title2.bold())
                Text("Начальный этап разработки. Загрузка iOS пока не реализована.")
                Text(diskStatus).font(.footnote)
                Text(jit.status).font(.footnote)
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
        .task {
            guard disk == nil else { return }
            do {
                let directory = try FileManager.default.url(for: .applicationSupportDirectory,
                    in: .userDomainMask, appropriateFor: nil, create: true)
                    .appendingPathComponent("VirtualMachine", isDirectory: true)
                try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
                disk = try VirtualDisk(url: directory.appendingPathComponent("disk.raw"))
                diskStatus = "Диск: 16 ГБ. Подключение к гостевой iOS ещё разрабатывается."
            } catch { diskStatus = "Ошибка подготовки диска: \(error)" }
        }
        .onChange(of: scenePhase) { _, phase in if phase == .active { jit.returnedToApp() } }
    }
}

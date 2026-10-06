import SwiftUI
import Podium7Core

@main struct Podium7App: App {
    var body: some Scene { WindowGroup { LaboratoryView() } }
}

struct LaboratoryView: View {
    @State private var output = ""
    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                Text("iPod touch 7 · A10").font(.title2.bold())
                Text("Начальный этап разработки. Загрузка iOS пока не реализована.")
                Button("Проверить ARM64") {
                    do {
                        let result = try DiagnosticROM.execute()
                        output = result.output + "Инструкций: \(result.instructions)"
                    } catch { output = "Ошибка: \(error)" }
                }.buttonStyle(.borderedProminent)
                ScrollView { Text(output).font(.system(.body, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                Spacer()
            }.padding().navigationTitle("Podium7")
        }
    }
}

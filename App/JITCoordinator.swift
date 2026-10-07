import SwiftUI
import UIKit
import Darwin
import Podium7Core

@MainActor final class JITCoordinator: ObservableObject {
    @Published var status = "Интерпретатор. JIT не включён."
    @Published var preparing = false
    @Published private(set) var backend: AArch64BlockJIT?
    private var waiting = false
    func requestStikDebug() {
        guard #available(iOS 17.4, *) else { status = "StikDebug требует iOS 17.4 или новее."; return }
        guard JITAvailability.taskAllowed else {
            status = "Подпись приложения не содержит get-task-allow. Подпиши IPA с сохранением этого разрешения."; return
        }
        do {
            let url = try StikDebugRequest.url(bundleID: Bundle.main.bundleIdentifier ?? "", pid: getpid(), txm: JITAvailability.txmPresence)
            waiting = true
            status = "Ожидание StikDebug. После подключения вернись в Podium7."
            UIApplication.shared.open(url) { [weak self] opened in
                if !opened { Task { @MainActor in self?.waiting = false; self?.status = "Не удалось открыть StikDebug." } }
            }
        } catch { status = "Не удалось определить TXM/SPTM или параметры приложения: \(error)" }
    }
    func returnedToApp() { if waiting { prepare() } }
    func prepare() {
        guard backend == nil, !preparing else { return }
        #if !targetEnvironment(simulator)
        guard JITAvailability.debuggerAttached else { status = "Отладчик ещё не подключён. Включи JIT в StikDebug."; return }
        #endif
        preparing = true
        status = "Подготовка памяти и проверка нативного выполнения…"
        Task {
            let result = await Task.detached { () -> Result<AArch64BlockJIT, Error> in
                do {
                    let jit = try AArch64BlockJIT()
                    let memory = LabMemory(); try memory.load([0xd2800540, 0xd4200000])
                    let cpu = AArch64CPU(memory: memory); cpu.jit = jit; try cpu.run()
                    guard cpu.registers[0] == 42, jit.executedInstructions > 0 else { throw JITError.unavailable(5) }
                    return .success(jit)
                } catch { return .failure(error) }
            }.value
            preparing = false
            switch result {
            case .success(let jit): backend = jit; waiting = false; status = "JIT работает: нативный ARM64-тест пройден."
            case .failure(let error): status = "JIT не готов: \(error). Интерпретатор доступен."
            }
        }
    }
}

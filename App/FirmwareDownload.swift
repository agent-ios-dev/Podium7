import Foundation
import Combine
import Podium7Core

// Download official firmware directly; never label an IPSW as a prepared VM.
@MainActor final class FirmwareDownload: ObservableObject {
    static let source = URL(string: "https://updates.cdn-apple.com/2025FallFCS/fullrestores/122-76865/68174A8B-44B2-4689-B8D4-C8F42F4FFBEE/iPodtouch_7_15.8.8_19H422_Restore.ipsw")!
    static let bytes: Int64 = 5_013_514_038
    @Published private(set) var downloading = false
    @Published private(set) var progress = 0.0
    @Published private(set) var status = "Официальная iOS 15.8.8 · загрузка с Apple · 5 ГБ."
    @Published private(set) var archive: URL?
    @Published private(set) var preparing = false
    var busy: Bool { downloading || preparing }
    private var session: URLSession?
    private var task: URLSessionDownloadTask?
    private var delegate: FirmwareTransfer?

    init() {
        if let path = try? Self.destination(), Self.isArchive(path) {
            archive = path; progress = 1
            status = "IPSW скачана. Автоматическая подготовка диска ещё разрабатывается."
        }
    }

    private static func destination() throws -> URL {
        let base = try FileManager.default.url(for: .applicationSupportDirectory,
            in: .userDomainMask, appropriateFor: nil, create: true).appendingPathComponent("Firmware")
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return base.appendingPathComponent("iPod9,1-19H422.ipsw")
    }

    static func isArchive(_ url: URL) -> Bool {
        guard let values = try? url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey, .isSymbolicLinkKey]),
              values.isRegularFile == true, values.isSymbolicLink != true,
              values.fileSize == Int(bytes), let file = try? FileHandle(forReadingFrom: url) else { return false }
        defer { try? file.close() }
        return (try? file.read(upToCount: 4)) == Data([0x50, 0x4b, 0x03, 0x04])
    }

    func start() {
        guard !downloading, archive == nil else { return }
        do {
            let destination = try Self.destination()
            let capacity = try destination.deletingLastPathComponent().resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
            guard (capacity.volumeAvailableCapacityForImportantUsage ?? 0) > Self.bytes + (1 << 30) else {
                status = "Для загрузки IPSW нужно минимум 6 ГБ свободного места."; return
            }
            let receiver = FirmwareTransfer(destination: destination) { [weak self] fraction in
                Task { @MainActor in self?.progress = fraction }
            } finished: { [weak self] result in
                Task { @MainActor in
                    guard let self else { return }
                    self.downloading = false
                    switch result {
                    case .success(let url):
                        self.archive = url; self.progress = 1
                        self.prepareDisk()
                    case .failure(let error):
                        self.status = "Загрузка: \(error.localizedDescription)"
                    }
                    self.session?.finishTasksAndInvalidate()
                    self.task = nil; self.session = nil; self.delegate = nil
                }
            }
            let configuration = URLSessionConfiguration.default
            configuration.timeoutIntervalForResource = 7200
            configuration.waitsForConnectivity = true
            let connection = URLSession(configuration: configuration, delegate: receiver, delegateQueue: nil)
            delegate = receiver; session = connection
            task = connection.downloadTask(with: Self.source)
            downloading = true; progress = 0; status = "Скачивание официальной IPSW с Apple…"
            task?.resume()
        } catch { status = "Загрузка: \(error.localizedDescription)" }
    }

    func cancel() { task?.cancel() }

    func prepareDisk() {
        guard !busy, let archive else { return }
        let disk = archive.deletingLastPathComponent().appendingPathComponent("official-os-16g.raw")
        preparing = true; progress = 0
        status = "Преобразование официальной системы в диск 16 ГБ…"
        Task {
            do {
                try await Task.detached { [weak self] in
                    try OfficialDiskPreparation.convert(archive: archive, destination: disk) { fraction in
                        Task { @MainActor in self?.progress = fraction }
                    }
                }.value
                status = "Исходный диск iOS создан на телефоне. Служебные APFS-тома, загрузчик и экран ещё разрабатываются."
            } catch { status = "Подготовка диска: \(error)" }
            preparing = false
        }
    }
}

private final class FirmwareTransfer: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    let destination: URL
    let progress: @Sendable (Double) -> Void
    let finished: @Sendable (Result<URL, Error>) -> Void
    // URLSession invokes delegate methods serially on its delegate queue.
    private var outcome: Result<URL, Error>?

    init(destination: URL, progress: @escaping @Sendable (Double) -> Void,
         finished: @escaping @Sendable (Result<URL, Error>) -> Void) {
        self.destination = destination; self.progress = progress; self.finished = finished
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        let host = request.url?.host ?? ""
        completionHandler(request.url?.scheme == "https" &&
            (host == "cdn-apple.com" || host.hasSuffix(".cdn-apple.com")) ? request : nil)
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask,
                    didWriteData bytesWritten: Int64, totalBytesWritten: Int64, totalBytesExpectedToWrite: Int64) {
        progress(min(1, Double(totalBytesWritten) / 5_013_514_038))
        if totalBytesWritten > 5_013_514_038 { downloadTask.cancel() }
    }

    func urlSession(_ session: URLSession, downloadTask: URLSessionDownloadTask, didFinishDownloadingTo location: URL) {
        do {
            guard let response = downloadTask.response as? HTTPURLResponse, response.statusCode == 200 else {
                throw URLError(.badServerResponse)
            }
            // This validates transport/file identity, not the firmware manifest or bootability.
            let values = try location.resourceValues(forKeys: [.fileSizeKey])
            guard values.fileSize == 5_013_514_038 else { throw URLError(.cannotDecodeContentData) }
            let file = try FileHandle(forReadingFrom: location)
            defer { try? file.close() }
            guard try file.read(upToCount: 4) == Data([0x50, 0x4b, 0x03, 0x04]) else {
                throw URLError(.cannotDecodeContentData)
            }
            // moveItem refuses replacing an existing archive/VM.
            try FileManager.default.moveItem(at: location, to: destination)
            outcome = .success(destination)
        } catch { outcome = .failure(error) }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        finished(error.map { .failure($0) } ?? outcome ?? .failure(URLError(.unknown)))
    }
}

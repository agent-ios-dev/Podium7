import Foundation
import Darwin

public enum VirtualDiskFault: Error, Equatable {
    case invalidImage, oversizedImage, outOfBounds, truncatedRead
}

/// Fixed 16-GiB raw sparse backing store. Not yet a guest NVMe controller.
public final class VirtualDisk {
    public static let capacity: UInt64 = 16 * 1024 * 1024 * 1024
    public static let sectorSize: UInt64 = 512
    public let url: URL
    private let handle: FileHandle
    private let lock = NSLock()

    public init(url: URL) throws {
        self.url = url
        let descriptor = url.withUnsafeFileSystemRepresentation {
            Darwin.open($0!, O_RDWR | O_CREAT | O_NOFOLLOW, S_IRUSR | S_IWUSR)
        }
        guard descriptor >= 0 else { throw POSIXError(POSIXErrorCode(rawValue: errno) ?? .EIO) }
        let opened = FileHandle(fileDescriptor: descriptor, closeOnDealloc: true)
        var status = stat()
        guard fstat(descriptor, &status) == 0, (status.st_mode & S_IFMT) == S_IFREG,
              status.st_size >= 0 else {
            try? opened.close()
            throw VirtualDiskFault.invalidImage
        }
        guard UInt64(status.st_size) <= Self.capacity else {
            try? opened.close()
            throw VirtualDiskFault.oversizedImage
        }
        do {
            // Extending with ftruncate creates holes on APFS; never fill 16 GiB
            // with zeros or map it into guest RAM. Existing bytes are retained.
            if UInt64(status.st_size) < Self.capacity {
                try opened.truncate(atOffset: Self.capacity)
                try opened.synchronize()
            }
        } catch {
            try? opened.close()
            throw error
        }
        handle = opened
    }

    private func validate(offset: UInt64, count: Int) throws {
        guard count >= 0, offset <= Self.capacity,
              UInt64(count) <= Self.capacity - offset else { throw VirtualDiskFault.outOfBounds }
    }

    public func read(offset: UInt64, count: Int) throws -> Data {
        try validate(offset: offset, count: count)
        lock.lock(); defer { lock.unlock() }
        try handle.seek(toOffset: offset)
        let data = try handle.read(upToCount: count) ?? Data()
        guard data.count == count else { throw VirtualDiskFault.truncatedRead }
        return data
    }

    public func write(offset: UInt64, data: Data) throws {
        try validate(offset: offset, count: data.count)
        lock.lock(); defer { lock.unlock() }
        try handle.seek(toOffset: offset)
        try handle.write(contentsOf: data)
    }

    public func synchronize() throws {
        lock.lock(); defer { lock.unlock() }
        try handle.synchronize()
    }
}

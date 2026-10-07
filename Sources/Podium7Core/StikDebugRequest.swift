import Foundation

public enum StikDebugRequestError: Error { case unknownTXM, invalidIdentity }
public enum StikDebugRequest {
    public static func url(bundleID: String, pid: Int32, txm: Int32) throws -> URL {
        guard !bundleID.isEmpty, pid > 0 else { throw StikDebugRequestError.invalidIdentity }
        guard txm == 0 || txm == 1 else { throw StikDebugRequestError.unknownTXM }
        var components = URLComponents()
        components.scheme = "stikdebug"; components.host = "enable-jit"
        components.queryItems = [URLQueryItem(name: "bundle-id", value: bundleID), URLQueryItem(name: "pid", value: String(pid))]
        if txm == 1 { components.queryItems?.append(URLQueryItem(name: "script-name", value: "universal.js")) }
        guard let url = components.url else { throw StikDebugRequestError.invalidIdentity }
        return url
    }
}

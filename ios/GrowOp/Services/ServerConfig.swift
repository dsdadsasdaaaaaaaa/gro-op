import Foundation

/// Where the grow brain lives. Stored in UserDefaults (single-user LAN app).
struct ServerConfig: Equatable {
    var baseURL: String
    var apiKey: String

    static let defaultURL = "http://homeassistant.local:8099"

    private static let urlKey = "growop.server.url"
    private static let keyKey = "growop.server.apiKey"

    static func load() -> ServerConfig {
        let d = UserDefaults.standard
        return ServerConfig(
            baseURL: d.string(forKey: urlKey) ?? "",
            apiKey: d.string(forKey: keyKey) ?? ""
        )
    }

    func save() {
        let d = UserDefaults.standard
        d.set(baseURL, forKey: Self.urlKey)
        d.set(apiKey, forKey: Self.keyKey)
    }

    static func clear() {
        let d = UserDefaults.standard
        d.removeObject(forKey: urlKey)
        d.removeObject(forKey: keyKey)
    }

    /// Normalised base URL: adds http:// if missing, strips trailing slash.
    var normalizedBaseURL: String {
        var s = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.isEmpty, !s.lowercased().hasPrefix("http://"), !s.lowercased().hasPrefix("https://") {
            s = "http://" + s
        }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    var isConfigured: Bool {
        !normalizedBaseURL.isEmpty && !apiKey.trimmingCharacters(in: .whitespaces).isEmpty
    }
}

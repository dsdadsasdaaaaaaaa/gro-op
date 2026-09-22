import Foundation

/// How the app reaches the grow brain.
enum ConnectionMode: String, CaseIterable, Codable {
    /// Plain HTTP to the add-on's own port on the home LAN.
    case direct
    /// Through Home Assistant's add-on ingress proxy (works remotely via Nabu Casa).
    case homeAssistant

    var title: String {
        switch self {
        case .direct: return "Same Wi‑Fi"
        case .homeAssistant: return "Through Home Assistant"
        }
    }
}

/// Where the grow brain lives. Stored in UserDefaults (single-user app).
struct ServerConfig: Equatable {
    var mode: ConnectionMode = .direct
    /// Direct mode: the add-on's base URL, e.g. http://homeassistant.local:8099
    var baseURL: String = ""
    /// Grow Brain API key (sent as X-API-Key in BOTH modes).
    var apiKey: String = ""
    /// Home Assistant mode: HA base URL, e.g. https://xxxx.ui.nabu.casa
    var haURL: String = ""
    /// Home Assistant long-lived access token.
    var haToken: String = ""
    /// Cached discovery results (refreshed automatically when stale).
    var haAddonSlug: String? = nil
    var haIngressPath: String? = nil

    static let defaultURL = "http://homeassistant.local:8099"

    private enum Keys {
        static let mode = "growop.server.mode"
        static let url = "growop.server.url"
        static let apiKey = "growop.server.apiKey"
        static let haURL = "growop.server.haURL"
        static let haToken = "growop.server.haToken"
        static let haAddonSlug = "growop.server.haAddonSlug"
        static let haIngressPath = "growop.server.haIngressPath"
    }

    static func load() -> ServerConfig {
        let d = UserDefaults.standard
        // Provisioning: values passed as launch arguments (`-growop.server.mode homeAssistant -growop.server.haURL …`)
        // live only in the volatile argument domain; persist them once so the app stays configured after relaunch.
        let args = d.volatileDomain(forName: UserDefaults.argumentDomain)
        if args[Keys.apiKey] != nil, (args[Keys.url] != nil || args[Keys.haURL] != nil) {
            let provisioned = ServerConfig(
                mode: ConnectionMode(rawValue: args[Keys.mode] as? String ?? "") ?? .direct,
                baseURL: args[Keys.url] as? String ?? "",
                apiKey: args[Keys.apiKey] as? String ?? "",
                haURL: args[Keys.haURL] as? String ?? "",
                haToken: args[Keys.haToken] as? String ?? "",
                haAddonSlug: nil, haIngressPath: nil)
            provisioned.save()
            d.removeVolatileDomain(forName: UserDefaults.argumentDomain)
            d.setVolatileDomain([:], forName: UserDefaults.argumentDomain)
            return provisioned
        }
        return ServerConfig(
            mode: ConnectionMode(rawValue: d.string(forKey: Keys.mode) ?? "") ?? .direct,
            baseURL: d.string(forKey: Keys.url) ?? "",
            apiKey: d.string(forKey: Keys.apiKey) ?? "",
            haURL: d.string(forKey: Keys.haURL) ?? "",
            haToken: d.string(forKey: Keys.haToken) ?? "",
            haAddonSlug: d.string(forKey: Keys.haAddonSlug),
            haIngressPath: d.string(forKey: Keys.haIngressPath)
        )
    }

    func save() {
        let d = UserDefaults.standard
        d.set(mode.rawValue, forKey: Keys.mode)
        d.set(baseURL, forKey: Keys.url)
        d.set(apiKey, forKey: Keys.apiKey)
        d.set(haURL, forKey: Keys.haURL)
        d.set(haToken, forKey: Keys.haToken)
        d.set(haAddonSlug, forKey: Keys.haAddonSlug)
        d.set(haIngressPath, forKey: Keys.haIngressPath)
    }

    static func clear() {
        let d = UserDefaults.standard
        [Keys.mode, Keys.url, Keys.apiKey, Keys.haURL, Keys.haToken, Keys.haAddonSlug, Keys.haIngressPath]
            .forEach { d.removeObject(forKey: $0) }
    }

    /// Adds a scheme if missing (http:// for direct, https:// for HA) and strips trailing slashes.
    static func normalize(_ raw: String, defaultScheme: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if !s.isEmpty, !s.lowercased().hasPrefix("http://"), !s.lowercased().hasPrefix("https://") {
            s = defaultScheme + "://" + s
        }
        while s.hasSuffix("/") { s.removeLast() }
        return s
    }

    /// Direct-mode base URL, normalised.
    var normalizedBaseURL: String { Self.normalize(baseURL, defaultScheme: "http") }

    /// Home Assistant base URL, normalised.
    var normalizedHAURL: String { Self.normalize(haURL, defaultScheme: "https") }

    var trimmedAPIKey: String { apiKey.trimmingCharacters(in: .whitespacesAndNewlines) }
    var trimmedHAToken: String { haToken.trimmingCharacters(in: .whitespacesAndNewlines) }

    var isConfigured: Bool {
        guard !trimmedAPIKey.isEmpty else { return false }
        switch mode {
        case .direct: return !normalizedBaseURL.isEmpty
        case .homeAssistant: return !normalizedHAURL.isEmpty && !trimmedHAToken.isEmpty
        }
    }

    /// True when the user-entered fields differ (ignores cached discovery values).
    func differsInUserFields(from other: ServerConfig) -> Bool {
        mode != other.mode || baseURL != other.baseURL || apiKey != other.apiKey
            || haURL != other.haURL || haToken != other.haToken
    }
}

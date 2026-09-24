import Foundation

// MARK: - Errors

enum APIError: LocalizedError {
    case notConfigured
    case invalidURL(String)
    case http(status: Int, detail: String?)
    case unauthorized
    case network(URLError)
    case decoding(Error)
    case other(Error)
    // Home Assistant (ingress) mode
    case haTokenRejected
    case haTokenMalformed(Int)
    case haNotAdmin
    case haAddonNotFound
    case haIngressSessionFailed(String)
    case haError(status: Int, message: String?)
    /// The WebSocket to Home Assistant could not be opened or misbehaved (detail includes the URL).
    case haWebSocket(String)
    /// Wraps an error with the name of the connection step that failed.
    case step(String, Error)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "This phone isn't set up yet. Scan the setup QR code from the dashboard."
        case .invalidURL(let s):
            return "\"\(s)\" doesn't look like a valid address."
        case .unauthorized:
            return "GrowOp at home didn't accept this phone's setup code. Use Settings → Set up this phone again, then scan the QR code."
        case .http(let status, let detail):
            if let detail, !detail.isEmpty { return detail }
            return "The server replied with an error (\(status))."
        case .network(let e):
            switch e.code {
            case .timedOut:
                return "The server took too long to respond. Try again in a moment."
            case .cannotFindHost, .dnsLookupFailed:
                return "Can't find that address. If it ends in .local, try the server's IP address instead (for example http://192.168.1.50:8099)."
            case .cannotConnectToHost:
                return "Nothing answered at that address. Check the address and port, and that the Grow Brain add-on is running."
            case .networkConnectionLost:
                return "The connection was reset (\(e.code.rawValue)). Three usual causes: a VPN on this iPhone (turn it off, or allow local network access in the VPN app); the address starting with https:// instead of http://; or Local Network permission (iPhone Settings → Privacy & Security → Local Network → GrowOp ON, then quit and reopen the app)."
            case .notConnectedToInternet:
                return "No network connection (\(e.code.rawValue)). Check Wi‑Fi, and that Local Network is ON for GrowOp in iPhone Settings → Privacy & Security."
            case .secureConnectionFailed, .serverCertificateUntrusted, .serverCertificateHasBadDate:
                return "Secure connection failed (\(e.code.rawValue)). For a Nabu Casa address this almost always means a typo in the long name: paste it from Home Assistant → Settings → Home Assistant Cloud instead of typing it. For a Same Wi‑Fi address, use http:// not https://."
            case .cancelled:
                return "Cancelled."
            default:
                return "Network problem (\(e.code.rawValue)): \(e.localizedDescription)"
            }
        case .decoding(let e):
            return "The server sent something the app didn't understand. (\(e.localizedDescription))"
        case .other(let e):
            return e.localizedDescription
        case .haTokenRejected:
            return "Home Assistant rejected the access token. Create a new one in Home Assistant (your profile → Security → Create token), copy ALL of it (about 180 characters), and paste it in. The Grow Brain API key goes in the separate field below."
        case .haTokenMalformed(let n):
            return "That doesn't look like a Home Assistant long-lived access token (\(n) characters; a real one is about 180 characters with two dots). Create one under your profile → Security → Create token and copy the whole thing."
        case .haNotAdmin:
            return "That Home Assistant account isn't an administrator, so it can't reach add-ons. Make a token from an admin account."
        case .haAddonNotFound:
            return "Grow Brain add-on not found in Home Assistant. Make sure it's installed and running."
        case .haIngressSessionFailed(let why):
            return "Ingress session failed: Home Assistant wouldn't open a session for the add-on. \(why)"
        case .haError(let status, let message):
            if status == 0, let message, !message.isEmpty { return "Home Assistant replied: \(message)" }
            if let message, !message.isEmpty { return "Home Assistant replied: \(message) (\(status))" }
            if status == 404 { return "Home Assistant replied 404. This needs a Home Assistant OS or Supervised install with the Grow Brain add-on." }
            return "Home Assistant replied with an error (\(status))."
        case .haWebSocket(let detail):
            return "Couldn't open Home Assistant's WebSocket at \(detail)"
        case .step(let name, let e):
            return "\(name): \(e.localizedDescription)"
        }
    }
}

// MARK: - Home Assistant WebSocket (what the HA frontend uses; the REST /api/hassio proxy allow-lists almost nothing)

/// One short-lived, authenticated WebSocket conversation with Home Assistant.
/// Protocol: server `auth_required` → client `auth` → server `auth_ok` | `auth_invalid`,
/// then `supervisor/api` commands with incrementing integer ids answered by `result` messages.
final class HASocket {
    private let task: URLSessionWebSocketTask
    let urlString: String
    private var nextID = 1
    private var closed = false

    init(cfg: ServerConfig, session: URLSession) throws {
        let base = cfg.normalizedHAURL
        var ws = base
        if ws.lowercased().hasPrefix("https://") { ws = "wss://" + ws.dropFirst(8) }
        else if ws.lowercased().hasPrefix("http://") { ws = "ws://" + ws.dropFirst(7) }
        let str = ws + "/api/websocket"
        guard let url = URL(string: str), url.host != nil else { throw APIError.invalidURL(base) }
        urlString = str
        task = session.webSocketTask(with: url)
        task.resume()
    }

    deinit { close() }

    func close() {
        guard !closed else { return }
        closed = true
        task.cancel(with: .normalClosure, reason: nil)
    }

    // MARK: Auth

    func authenticate(token: String) async throws {
        let first = try await receive()
        guard first["type"] as? String == "auth_required" else {
            throw APIError.haWebSocket("\(urlString): it didn't ask for authentication. Is this address really Home Assistant?")
        }
        try await send(["type": "auth", "access_token": token])
        let reply = try await receive()
        switch reply["type"] as? String {
        case "auth_ok": return
        case "auth_invalid": throw APIError.haTokenRejected
        default: throw APIError.haWebSocket("\(urlString): unexpected reply while signing in (\(reply["type"] ?? "?"))")
        }
    }

    // MARK: supervisor/api

    /// Sends one `supervisor/api` command and returns the Supervisor's data object.
    /// HA returns the Supervisor's `data` directly in `result`; the `{result, data}` envelope is tolerated too.
    func supervisor(_ endpoint: String, method: String) async throws -> [String: Any] {
        let id = nextID
        nextID += 1
        try await send(["id": id, "type": "supervisor/api", "endpoint": endpoint, "method": method])
        var msg: [String: Any]
        repeat {
            msg = try await receive()
        } while (msg["id"] as? Int) != id || (msg["type"] as? String) != "result"

        if (msg["success"] as? Bool) != true {
            let err = msg["error"] as? [String: Any]
            let code = (err?["code"] as? String) ?? ""
            let message = (err?["message"] as? String) ?? "Supervisor command failed"
            switch code {
            case "unauthorized": throw APIError.haNotAdmin
            case "unknown_command": throw APIError.haError(status: 404, message: nil)
            default: throw APIError.haError(status: 0, message: message)
            }
        }
        var result = (msg["result"] as? [String: Any]) ?? [:]
        if let envelopeResult = result["result"] as? String {
            if envelopeResult == "error" {
                throw APIError.haError(status: 0, message: (result["message"] as? String) ?? "Supervisor error")
            }
            if let inner = result["data"] as? [String: Any] { result = inner }
        }
        return result
    }

    // MARK: Plumbing

    private func send(_ obj: [String: Any]) async throws {
        let data = try JSONSerialization.data(withJSONObject: obj)
        let text = String(decoding: data, as: UTF8.self)
        let task = self.task
        do {
            try await HASocket.withTimeout(15, url: urlString) { try await task.send(.string(text)) }
        } catch let e as APIError {
            throw e
        } catch {
            throw APIError.haWebSocket("\(urlString): \(HASocket.describe(error))")
        }
    }

    private func receive() async throws -> [String: Any] {
        let task = self.task
        let message: URLSessionWebSocketTask.Message
        do {
            message = try await HASocket.withTimeout(20, url: urlString) { try await task.receive() }
        } catch let e as APIError {
            throw e
        } catch {
            throw APIError.haWebSocket("\(urlString): \(HASocket.describe(error))")
        }
        let data: Data
        switch message {
        case .string(let s): data = Data(s.utf8)
        case .data(let d): data = d
        @unknown default: throw APIError.haWebSocket("\(urlString): unexpected message type")
        }
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw APIError.haWebSocket("\(urlString): it sent something that isn't JSON")
        }
        return obj
    }

    private static func withTimeout<T>(_ seconds: Double, url: String, _ op: @escaping @Sendable () async throws -> T) async throws -> T {
        try await withThrowingTaskGroup(of: T.self) { group in
            group.addTask { try await op() }
            group.addTask {
                try await Task.sleep(for: .seconds(seconds))
                throw APIError.haWebSocket("\(url): no reply after \(Int(seconds)) s")
            }
            guard let first = try await group.next() else { throw APIError.haWebSocket("\(url): no reply") }
            group.cancelAll()
            return first
        }
    }

    static func describe(_ error: Error) -> String {
        if let e = error as? URLError { return "\(e.localizedDescription) (\(e.code.rawValue))" }
        return error.localizedDescription
    }
}

// MARK: - Home Assistant ingress resolver

/// Discovers the Grow Brain add-on's ingress path and keeps a fresh ingress session,
/// using Home Assistant's WebSocket API. One instance per configured connection;
/// concurrent callers share in-flight work. A fresh socket is opened for each
/// discovery and each session renewal and closed right after.
actor HAIngress {
    struct Resolved: Equatable {
        /// HA base + ingress path (no trailing slash). API paths are appended directly.
        var base: String
        /// Value for the `Cookie` header.
        var cookie: String
    }

    static let sessionMaxAge: TimeInterval = 10 * 60

    private let session: URLSession
    private(set) var slug: String?
    private(set) var ingressPath: String?
    private var sessionID: String?
    private var sessionCreatedAt = Date.distantPast
    private var pendingDiscovery: Task<(String, String), Error>?
    private var pendingSession: Task<String, Error>?

    init(session: URLSession, slug: String? = nil, ingressPath: String? = nil) {
        self.session = session
        self.slug = slug
        self.ingressPath = ingressPath
    }

    func resolve(_ cfg: ServerConfig, forceNewSession: Bool = false, forceDiscovery: Bool = false) async throws -> Resolved {
        let ha = cfg.normalizedHAURL
        guard !ha.isEmpty, !cfg.trimmedHAToken.isEmpty else { throw APIError.notConfigured }
        if forceDiscovery || ingressPath == nil || slug == nil {
            try await discover(cfg)
        }
        let sid = try await currentSession(cfg, force: forceNewSession)
        var path = ingressPath ?? ""
        while path.hasSuffix("/") { path.removeLast() }
        if !path.hasPrefix("/") { path = "/" + path }
        return Resolved(base: ha + path, cookie: "ingress_session=\(sid)")
    }

    // MARK: Discovery (steps 1 + 2, one socket)

    private func discover(_ cfg: ServerConfig) async throws {
        var created = false
        let task: Task<(String, String), Error>
        if let p = pendingDiscovery {
            task = p
        } else {
            let s = session
            task = Task { try await HAIngress.performDiscovery(cfg, session: s) }
            pendingDiscovery = task
            created = true
        }
        defer { if created { pendingDiscovery = nil } }
        let (foundSlug, foundPath) = try await task.value
        slug = foundSlug
        ingressPath = foundPath
    }

    private static func performDiscovery(_ cfg: ServerConfig, session: URLSession) async throws -> (String, String) {
        let sock = try HASocket(cfg: cfg, session: session)
        defer { sock.close() }
        do {
            try await sock.authenticate(token: cfg.trimmedHAToken)
        } catch {
            throw APIError.step("Signing in to Home Assistant", error)
        }
        let list: [String: Any]
        do {
            list = try await sock.supervisor("/addons", method: "get")
        } catch {
            throw APIError.step("Listing Home Assistant add-ons", error)
        }
        let slugs = ((list["addons"] as? [[String: Any]]) ?? []).compactMap { $0["slug"] as? String }
        guard let slug = slugs.first(where: { $0 == "grow_brain" || $0.hasSuffix("_grow_brain") }) else {
            throw APIError.haAddonNotFound
        }
        let info: [String: Any]
        do {
            info = try await sock.supervisor("/addons/\(slug)/info", method: "get")
        } catch {
            throw APIError.step("Reading the Grow Brain add-on's ingress address", error)
        }
        guard let path = info["ingress_url"] as? String, !path.isEmpty else {
            throw APIError.haError(status: 200, message: "The Grow Brain add-on has no ingress URL. Is ingress enabled and the add-on running?")
        }
        return (slug, path)
    }

    // MARK: Session (step 3, its own socket)

    private func currentSession(_ cfg: ServerConfig, force: Bool) async throws -> String {
        if !force, let sid = sessionID, Date().timeIntervalSince(sessionCreatedAt) < Self.sessionMaxAge {
            return sid
        }
        var created = false
        let task: Task<String, Error>
        if let p = pendingSession {
            task = p
        } else {
            let s = session
            task = Task { try await HAIngress.createSession(cfg, session: s) }
            pendingSession = task
            created = true
        }
        defer { if created { pendingSession = nil } }
        let sid = try await task.value
        sessionID = sid
        sessionCreatedAt = Date()
        return sid
    }

    private static func createSession(_ cfg: ServerConfig, session: URLSession) async throws -> String {
        let sock = try HASocket(cfg: cfg, session: session)
        defer { sock.close() }
        do {
            try await sock.authenticate(token: cfg.trimmedHAToken)
        } catch {
            throw APIError.step("Signing in to Home Assistant", error)
        }
        let d: [String: Any]
        do {
            d = try await sock.supervisor("/ingress/session", method: "post")
        } catch let e as APIError {
            if case .haNotAdmin = e { throw APIError.step("Opening an ingress session", e) }
            throw APIError.haIngressSessionFailed(e.localizedDescription)
        }
        guard let sid = d["session"] as? String, !sid.isEmpty else {
            throw APIError.haIngressSessionFailed("No session id was returned.")
        }
        return sid
    }
}

// MARK: - Client

final class APIClient: @unchecked Sendable {
    /// A stable id for this phone, so "read the brief" is remembered per person, not for the whole tent.
    static let deviceId: String = {
        let key = "growop.deviceId"
        if let id = UserDefaults.standard.string(forKey: key) { return id }
        let id = "ios-" + UUID().uuidString.prefix(8).lowercased()
        UserDefaults.standard.set(id, forKey: key)
        return id
    }()

    static let shortTimeout: TimeInterval = 20
    static let longTimeout: TimeInterval = 90

    private(set) var config: ServerConfig
    private let session: URLSession
    private var ingress: HAIngress
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(config: ServerConfig) {
        self.config = config
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = APIClient.shortTimeout
        cfg.timeoutIntervalForResource = 300
        cfg.waitsForConnectivity = false
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        // We manage the ingress cookie ourselves; don't let URLSession add or store any.
        cfg.httpShouldSetCookies = false
        cfg.httpCookieAcceptPolicy = .never
        cfg.httpCookieStorage = nil
        session = URLSession(configuration: cfg)
        ingress = HAIngress(session: session, slug: config.haAddonSlug, ingressPath: config.haIngressPath)
    }

    func update(config: ServerConfig) {
        self.config = config
        ingress = HAIngress(session: session, slug: config.haAddonSlug, ingressPath: config.haIngressPath)
    }

    // MARK: Request plumbing

    private struct RequestSpec {
        var method: String
        var path: String
        var query: [URLQueryItem] = []
        var body: Data? = nil
        var contentType: String? = nil
        var timeout: TimeInterval = APIClient.shortTimeout
        var auth: Bool = true
    }

    private func build(_ spec: RequestSpec, base: String, headers: [String: String]) throws -> URLRequest {
        guard !base.isEmpty else { throw APIError.notConfigured }
        guard var comps = URLComponents(string: base + spec.path) else { throw APIError.invalidURL(base) }
        if !spec.query.isEmpty { comps.queryItems = spec.query }
        guard let url = comps.url, url.host != nil else { throw APIError.invalidURL(base) }
        var req = URLRequest(url: url)
        req.httpMethod = spec.method
        req.timeoutInterval = spec.timeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue(APIClient.deviceId, forHTTPHeaderField: "X-Device-Id")
        for (k, v) in headers { req.setValue(v, forHTTPHeaderField: k) }
        if let body = spec.body {
            req.httpBody = body
            req.setValue(spec.contentType ?? "application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    /// Runs a request. Throws only on transport failures; returns the HTTP status and body.
    private func execute(_ req: URLRequest) async throws -> (Int, Data) {
        do {
            let (data, response) = try await session.data(for: req)
            return ((response as? HTTPURLResponse)?.statusCode ?? 200, data)
        } catch let e as URLError {
            throw APIError.network(e)
        } catch {
            throw APIError.other(error)
        }
    }

    private func check(_ status: Int, _ data: Data) throws -> Data {
        if (200..<300).contains(status) { return data }
        if status == 401 || status == 403 { throw APIError.unauthorized }
        let detail = (try? decoder.decode(APIErrorBody.self, from: data))?.detail
            ?? String(data: data, encoding: .utf8).flatMap { $0.count < 300 && !$0.contains("<html") ? $0 : nil }
        throw APIError.http(status: status, detail: detail)
    }

    /// The one place that decides how a grow-brain request reaches the server.
    private func perform(_ spec: RequestSpec, config override: ServerConfig? = nil, ingress overrideIngress: HAIngress? = nil) async throws -> Data {
        let cfg = override ?? config
        switch cfg.mode {
        case .direct:
            var headers: [String: String] = [:]
            if spec.auth { headers["X-API-Key"] = cfg.trimmedAPIKey }
            let req = try build(spec, base: cfg.normalizedBaseURL, headers: headers)
            let (status, data) = try await execute(req)
            return try check(status, data)
        case .homeAssistant:
            return try await performViaHA(spec, cfg: cfg, ingress: overrideIngress ?? ingress)
        }
    }

    /// Step 4: call the add-on through HA ingress, with session renewal on 401 and
    /// ingress-path rediscovery on 404 (each retried once).
    private func performViaHA(_ spec: RequestSpec, cfg: ServerConfig, ingress: HAIngress) async throws -> Data {
        func run(_ r: HAIngress.Resolved) async throws -> (Int, Data) {
            var headers = [
                "Authorization": "Bearer \(cfg.trimmedHAToken)",
                "Cookie": r.cookie,
            ]
            if spec.auth { headers["X-API-Key"] = cfg.trimmedAPIKey }
            let req = try build(spec, base: r.base, headers: headers)
            return try await execute(req)
        }

        var resolved = try await ingress.resolve(cfg)
        var (status, data) = try await run(resolved)
        if status == 401 {
            resolved = try await ingress.resolve(cfg, forceNewSession: true)
            (status, data) = try await run(resolved)
        } else if status == 404 {
            let previous = resolved.base
            resolved = try await ingress.resolve(cfg, forceDiscovery: true)
            if resolved.base != previous {
                (status, data) = try await run(resolved)
            }
        }
        await persistDiscovery(from: ingress)
        return try check(status, data)
    }

    /// Keeps the cached add-on slug / ingress path in the saved config up to date.
    private func persistDiscovery(from ingress: HAIngress) async {
        guard ingress === self.ingress else { return }
        let slug = await ingress.slug
        let path = await ingress.ingressPath
        guard let slug, let path else { return }
        if config.haAddonSlug != slug || config.haIngressPath != path {
            config.haAddonSlug = slug
            config.haIngressPath = path
            config.save()
        }
    }

    private func decode<T: Decodable>(_ data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private func encode<B: Encodable>(_ body: B) throws -> Data {
        do { return try encoder.encode(body) } catch { throw APIError.other(error) }
    }

    private func get<T: Decodable>(_ path: String, query: [URLQueryItem] = [], timeout: TimeInterval = APIClient.shortTimeout, auth: Bool = true) async throws -> T {
        try decode(try await perform(RequestSpec(method: "GET", path: path, query: query, timeout: timeout, auth: auth)))
    }

    private func send<T: Decodable, B: Encodable>(_ method: String, _ path: String, body: B, timeout: TimeInterval = APIClient.shortTimeout) async throws -> T {
        try decode(try await perform(RequestSpec(method: method, path: path, body: try encode(body), timeout: timeout)))
    }

    private func send<T: Decodable>(_ method: String, _ path: String, timeout: TimeInterval = APIClient.shortTimeout) async throws -> T {
        try decode(try await perform(RequestSpec(method: method, path: path, timeout: timeout)))
    }

    private func sendIgnoringBody<B: Encodable>(_ method: String, _ path: String, body: B, timeout: TimeInterval = APIClient.shortTimeout) async throws {
        _ = try await perform(RequestSpec(method: method, path: path, body: try encode(body), timeout: timeout))
    }

    private func sendIgnoringBody(_ method: String, _ path: String, timeout: TimeInterval = APIClient.shortTimeout) async throws {
        _ = try await perform(RequestSpec(method: method, path: path, timeout: timeout))
    }

    // MARK: Connection test

    struct VerifyResult {
        /// The candidate config with discovery cache filled in (HA mode).
        var config: ServerConfig
        var health: HealthResponse
        var status: StatusResponse
    }

    /// Runs the full connection chain for a candidate config without saving anything,
    /// reporting which step failed.
    func verify(_ candidate: ServerConfig) async throws -> VerifyResult {
        var cfg = candidate
        guard cfg.isConfigured else { throw APIError.notConfigured }
        var tempIngress: HAIngress? = nil
        if cfg.mode == .homeAssistant {
            let tok = cfg.trimmedHAToken
            if tok.count < 100 || tok.filter({ $0 == "." }).count != 2 {
                throw APIError.step("Checking the Home Assistant token", APIError.haTokenMalformed(tok.count))
            }
            let ing = HAIngress(session: session)
            tempIngress = ing
            // Steps 1–3: find the add-on, read its ingress path, open a session.
            _ = try await ing.resolve(cfg, forceNewSession: true, forceDiscovery: true)
            cfg.haAddonSlug = await ing.slug
            cfg.haIngressPath = await ing.ingressPath
        }
        let health: HealthResponse
        do {
            health = try decode(try await perform(RequestSpec(method: "GET", path: "/api/health", timeout: 15, auth: false), config: cfg, ingress: tempIngress))
        } catch {
            throw APIError.step(cfg.mode == .homeAssistant ? "Reaching the grow brain through Home Assistant" : "Reaching the grow brain", error)
        }
        let status: StatusResponse
        do {
            status = try decode(try await perform(RequestSpec(method: "GET", path: "/api/status", timeout: APIClient.shortTimeout), config: cfg, ingress: tempIngress))
        } catch {
            throw APIError.step("Checking the Grow Brain API key", error)
        }
        return VerifyResult(config: cfg, health: health, status: status)
    }

    // MARK: Health / status

    /// GET /api/health (no API key). Optionally against a config that isn't saved yet.
    func health(using cfg: ServerConfig? = nil) async throws -> HealthResponse {
        try decode(try await perform(RequestSpec(method: "GET", path: "/api/health", timeout: 15, auth: false), config: cfg))
    }

    func status(using cfg: ServerConfig? = nil) async throws -> StatusResponse {
        try decode(try await perform(RequestSpec(method: "GET", path: "/api/status"), config: cfg))
    }

    // MARK: Devices

    func devices() async throws -> DevicesResponse { try await get("/api/devices") }

    func mapDevice(role: String, entityId: String?) async throws -> DeviceStatus {
        try await send("PUT", "/api/devices/\(role)", body: DeviceMapRequest(entityId: entityId))
    }

    func overrideDevice(role: String, mode: String, minutes: Int?) async throws -> DeviceStatus {
        try await send("POST", "/api/devices/\(role)/override", body: DeviceOverrideRequest(mode: mode, minutes: minutes))
    }

    func haEntities() async throws -> HAEntitiesResponse { try await get("/api/ha/entities") }

    func automap() async throws -> DevicesResponse { try await send("POST", "/api/ha/automap") }

    // MARK: Grow

    func grow() async throws -> GrowProfile { try await get("/api/grow") }

    func updateGrow(_ profile: GrowProfile) async throws -> GrowProfile {
        try await send("PUT", "/api/grow", body: profile)
    }

    func setStage(_ stage: String) async throws -> GrowProfile {
        try await send("POST", "/api/grow/stage", body: StageChangeRequest(stage: stage))
    }

    // MARK: Targets

    func targets() async throws -> Targets { try await get("/api/targets") }

    func updateTargets(_ fields: [String: JSONValue]) async throws -> Targets {
        try await send("PUT", "/api/targets", body: fields)
    }

    func resetTargets() async throws -> Targets { try await send("DELETE", "/api/targets") }

    // MARK: History

    func history(hours: Int = 24) async throws -> HistoryResponse {
        try await get("/api/history", query: [URLQueryItem(name: "hours", value: String(hours))])
    }

    // MARK: Log

    func submitLog(_ entry: LogRequest) async throws -> LogResponse {
        try await send("POST", "/api/log", body: entry, timeout: APIClient.longTimeout)
    }

    func humidifierRefilled() async throws { try await sendIgnoringBody("POST", "/api/humidifier/refilled") }

    func notifyTest(service: String) async throws {
        let enc = service.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? service
        try await sendIgnoringBody("POST", "/api/notify/test?service=\(enc)")
    }

    func logEntries(limit: Int = 50) async throws -> LogListResponse {
        try await get("/api/log", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    // MARK: Photos

    func photoRequests(status: String = "open") async throws -> PhotoRequestsResponse {
        try await get("/api/photo-requests", query: [URLQueryItem(name: "status", value: status)])
    }

    func skipPhotoRequest(id: Int) async throws {
        try await sendIgnoringBody("POST", "/api/photo-requests/\(id)/skip")
    }

    func uploadPhoto(jpeg: Data, requestId: Int?, note: String?, plantId: Int? = nil) async throws -> Photo {
        let boundary = "GrowOpBoundary-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append(value.data(using: .utf8)!)
            body.append("\r\n".data(using: .utf8)!)
        }
        if let requestId { field("request_id", String(requestId)) }
        if let plantId { field("plant_id", String(plantId)) }
        if let note, !note.isEmpty { field("note", note) }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(jpeg)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        let spec = RequestSpec(method: "POST", path: "/api/photos", body: body,
                               contentType: "multipart/form-data; boundary=\(boundary)",
                               timeout: APIClient.longTimeout)
        return try decode(try await perform(spec))
    }

    func photos(limit: Int = 30) async throws -> PhotosResponse {
        try await get("/api/photos", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    func photoImageData(id: Int) async throws -> Data {
        try await perform(RequestSpec(method: "GET", path: "/api/photos/\(id)/image", timeout: 30))
    }

    func photoThumbData(id: Int) async throws -> Data {
        try await perform(RequestSpec(method: "GET", path: "/api/photos/\(id)/thumb", timeout: 20))
    }

    // MARK: Tasks

    func tasks(status: String = "open") async throws -> TasksResponse {
        try await get("/api/tasks", query: [URLQueryItem(name: "status", value: status)])
    }

    func createTask(_ task: NewTaskRequest) async throws -> TaskItem {
        try await send("POST", "/api/tasks", body: task)
    }

    func completeTask(id: Int) async throws -> TaskItem { try await send("POST", "/api/tasks/\(id)/complete") }

    func reopenTask(id: Int) async throws -> TaskItem { try await send("POST", "/api/tasks/\(id)/reopen") }

    // MARK: Brief

    /// GET /api/brief → Brief or JSON null.
    func brief() async throws -> Brief? {
        let data = try await perform(RequestSpec(method: "GET", path: "/api/brief"))
        let trimmed = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmed.isEmpty || trimmed == "null" { return nil }
        return try decode(data)
    }

    func runBrief() async throws -> Brief { try await send("POST", "/api/brief/run", timeout: APIClient.longTimeout) }

    func markBriefRead(id: Int) async throws { try await sendIgnoringBody("POST", "/api/brief/\(id)/read") }

    // MARK: Chat

    func sendChat(_ message: String, plantId: Int? = nil, author: String? = nil) async throws -> ChatReply {
        try await send("POST", "/api/chat", body: ChatSendRequest(message: message, plantId: plantId, author: author), timeout: APIClient.longTimeout)
    }

    func chatMessages(limit: Int = 50) async throws -> ChatListResponse {
        try await get("/api/chat", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    func clearChat() async throws { try await sendIgnoringBody("DELETE", "/api/chat") }

    // MARK: Events

    func events(limit: Int = 50) async throws -> EventsResponse {
        try await get("/api/events", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    // MARK: Settings

    func settings() async throws -> Settings { try await get("/api/settings") }

    func updateSettings(_ fields: [String: JSONValue]) async throws -> Settings {
        try await send("PUT", "/api/settings", body: fields)
    }

    // MARK: Plants

    func plants() async throws -> PlantsResponse { try await get("/api/plants") }

    func createPlant(_ fields: [String: JSONValue]) async throws -> Plant {
        try await send("POST", "/api/plants", body: fields)
    }

    func updatePlant(id: Int, _ fields: [String: JSONValue]) async throws -> Plant {
        try await send("PUT", "/api/plants/\(id)", body: fields)
    }

    func deletePlant(id: Int) async throws {
        try await sendIgnoringBody("DELETE", "/api/plants/\(id)")
    }

    // MARK: Plan

    func getPlan(plantId: Int? = nil) async throws -> GrowPlan {
        var q: [URLQueryItem] = []
        if let plantId { q.append(URLQueryItem(name: "plant_id", value: String(plantId))) }
        return try await get("/api/plan", query: q)
    }

    // MARK: Tent camera

    func camera() async throws -> CameraResponse { try await get("/api/camera") }

    func setCamera(entityId: String?) async throws -> CameraResponse {
        try await send("PUT", "/api/camera", body: CameraSelectRequest(entityId: entityId))
    }

    /// Fresh JPEG. Cache-busting query so no proxy/URLSession layer can serve an old frame.
    func cameraSnapshot() async throws -> Data {
        let stamp = URLQueryItem(name: "t", value: String(Int(Date().timeIntervalSince1970 * 1000)))
        return try await perform(RequestSpec(method: "GET", path: "/api/camera/snapshot", query: [stamp], timeout: 10))
    }

    func cameraFrames(days: Int) async throws -> CameraFramesResponse {
        try await get("/api/camera/frames", query: [URLQueryItem(name: "days", value: String(days))])
    }

    func cameraFrameData(id: Int) async throws -> Data {
        try await perform(RequestSpec(method: "GET", path: "/api/camera/frames/\(id)", timeout: 20))
    }

    func cameraAnalyse(plantId: Int?, note: String?) async throws -> Photo {
        try await send("POST", "/api/camera/analyse", body: CameraAnalyseRequest(plantId: plantId, note: note), timeout: APIClient.longTimeout)
    }

    // MARK: Control

    func pauseControl(minutes: Int) async throws {
        try await sendIgnoringBody("POST", "/api/control/pause", body: PauseRequest(minutes: minutes))
    }

    func resumeControl() async throws { try await sendIgnoringBody("POST", "/api/control/resume") }

    /// Whole-tent OFF: every device off and kept off until `startTent()`.
    func setStandby() async throws -> StandbyResponse { try await send("POST", "/api/control/standby") }

    /// Back to fully automatic (also clears pause and manual overrides on the backend).
    func startTent() async throws -> StandbyResponse { try await send("POST", "/api/control/start") }
}

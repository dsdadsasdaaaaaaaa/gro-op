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

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "The app isn't connected to your grow brain yet. Open Settings to set it up."
        case .invalidURL(let s):
            return "\"\(s)\" doesn't look like a valid server address."
        case .unauthorized:
            return "The grow brain rejected the API key. Check it in Settings."
        case .http(let status, let detail):
            if let detail, !detail.isEmpty { return detail }
            return "The server replied with an error (\(status))."
        case .network(let e):
            switch e.code {
            case .timedOut:
                return "The grow brain took too long to respond. Try again in a moment."
            case .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed:
                return "Can't reach the grow brain. Make sure you're on your home Wi-Fi and the server is running."
            case .notConnectedToInternet, .networkConnectionLost:
                return "No network connection. Connect to your home Wi-Fi and try again."
            case .cancelled:
                return "Cancelled."
            default:
                return "Network problem: \(e.localizedDescription)"
            }
        case .decoding(let e):
            return "The server sent something the app didn't understand. (\(e.localizedDescription))"
        case .other(let e):
            return e.localizedDescription
        }
    }
}

// MARK: - Client

final class APIClient: @unchecked Sendable {
    static let shortTimeout: TimeInterval = 20
    static let longTimeout: TimeInterval = 90

    private(set) var config: ServerConfig
    private let session: URLSession
    private let decoder = JSONDecoder()
    private let encoder = JSONEncoder()

    init(config: ServerConfig) {
        self.config = config
        let cfg = URLSessionConfiguration.default
        cfg.timeoutIntervalForRequest = APIClient.shortTimeout
        cfg.timeoutIntervalForResource = 180
        cfg.waitsForConnectivity = false
        cfg.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: cfg)
    }

    func update(config: ServerConfig) {
        self.config = config
    }

    // MARK: Request plumbing

    private func makeRequest(method: String,
                             path: String,
                             query: [URLQueryItem] = [],
                             body: Data? = nil,
                             contentType: String? = nil,
                             timeout: TimeInterval,
                             auth: Bool = true,
                             overrideConfig: ServerConfig? = nil) throws -> URLRequest {
        let cfg = overrideConfig ?? config
        let base = cfg.normalizedBaseURL
        guard !base.isEmpty else { throw APIError.notConfigured }
        guard var comps = URLComponents(string: base + path) else { throw APIError.invalidURL(base) }
        if !query.isEmpty { comps.queryItems = query }
        guard let url = comps.url, url.host != nil else { throw APIError.invalidURL(base) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = timeout
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if auth {
            req.setValue(cfg.apiKey, forHTTPHeaderField: "X-API-Key")
        }
        if let body {
            req.httpBody = body
            req.setValue(contentType ?? "application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    private func perform(_ req: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: req)
        } catch let e as URLError {
            throw APIError.network(e)
        } catch {
            throw APIError.other(error)
        }
        guard let http = response as? HTTPURLResponse else { return data }
        if (200..<300).contains(http.statusCode) { return data }
        if http.statusCode == 401 || http.statusCode == 403 { throw APIError.unauthorized }
        let detail = (try? decoder.decode(APIErrorBody.self, from: data))?.detail
            ?? String(data: data, encoding: .utf8).flatMap { $0.count < 300 ? $0 : nil }
        throw APIError.http(status: http.statusCode, detail: detail)
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
        let req = try makeRequest(method: "GET", path: path, query: query, timeout: timeout, auth: auth)
        return try decode(try await perform(req))
    }

    private func send<T: Decodable, B: Encodable>(_ method: String, _ path: String, body: B, timeout: TimeInterval = APIClient.shortTimeout) async throws -> T {
        let req = try makeRequest(method: method, path: path, body: try encode(body), timeout: timeout)
        return try decode(try await perform(req))
    }

    private func send<T: Decodable>(_ method: String, _ path: String, timeout: TimeInterval = APIClient.shortTimeout) async throws -> T {
        let req = try makeRequest(method: method, path: path, timeout: timeout)
        return try decode(try await perform(req))
    }

    private func sendIgnoringBody<B: Encodable>(_ method: String, _ path: String, body: B, timeout: TimeInterval = APIClient.shortTimeout) async throws {
        let req = try makeRequest(method: method, path: path, body: try encode(body), timeout: timeout)
        _ = try await perform(req)
    }

    private func sendIgnoringBody(_ method: String, _ path: String, timeout: TimeInterval = APIClient.shortTimeout) async throws {
        let req = try makeRequest(method: method, path: path, timeout: timeout)
        _ = try await perform(req)
    }

    // MARK: Health / status

    /// GET /api/health (no auth). Optionally test a config that isn't saved yet.
    func health(using cfg: ServerConfig? = nil) async throws -> HealthResponse {
        let req = try makeRequest(method: "GET", path: "/api/health", timeout: 10, auth: false, overrideConfig: cfg)
        return try decode(try await perform(req))
    }

    func status(using cfg: ServerConfig? = nil) async throws -> StatusResponse {
        let req = try makeRequest(method: "GET", path: "/api/status", timeout: APIClient.shortTimeout, overrideConfig: cfg)
        return try decode(try await perform(req))
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

    func uploadPhoto(jpeg: Data, requestId: Int?, note: String?) async throws -> Photo {
        let boundary = "GrowOpBoundary-\(UUID().uuidString)"
        var body = Data()
        func field(_ name: String, _ value: String) {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
            body.append(value.data(using: .utf8)!)
            body.append("\r\n".data(using: .utf8)!)
        }
        if let requestId { field("request_id", String(requestId)) }
        if let note, !note.isEmpty { field("note", note) }
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(jpeg)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)

        let req = try makeRequest(method: "POST", path: "/api/photos", body: body,
                                  contentType: "multipart/form-data; boundary=\(boundary)",
                                  timeout: APIClient.longTimeout)
        return try decode(try await perform(req))
    }

    func photos(limit: Int = 30) async throws -> PhotosResponse {
        try await get("/api/photos", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    func photoImageData(id: Int) async throws -> Data {
        let req = try makeRequest(method: "GET", path: "/api/photos/\(id)/image", timeout: 30)
        return try await perform(req)
    }

    func photoThumbData(id: Int) async throws -> Data {
        let req = try makeRequest(method: "GET", path: "/api/photos/\(id)/thumb", timeout: 20)
        return try await perform(req)
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
        let req = try makeRequest(method: "GET", path: "/api/brief", timeout: APIClient.shortTimeout)
        let data = try await perform(req)
        let trimmed = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if trimmed.isEmpty || trimmed == "null" { return nil }
        return try decode(data)
    }

    func runBrief() async throws -> Brief { try await send("POST", "/api/brief/run", timeout: APIClient.longTimeout) }

    func markBriefRead(id: Int) async throws { try await sendIgnoringBody("POST", "/api/brief/\(id)/read") }

    // MARK: Chat

    func sendChat(_ message: String) async throws -> ChatReply {
        try await send("POST", "/api/chat", body: ChatSendRequest(message: message), timeout: APIClient.longTimeout)
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

    // MARK: Control

    func pauseControl(minutes: Int) async throws {
        try await sendIgnoringBody("POST", "/api/control/pause", body: PauseRequest(minutes: minutes))
    }

    func resumeControl() async throws { try await sendIgnoringBody("POST", "/api/control/resume") }
}

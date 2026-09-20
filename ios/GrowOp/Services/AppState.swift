import Foundation
import SwiftUI
import UIKit

/// Central observable store. Polls /api/status every 15s while the app is in the foreground
/// and caches everything the screens need.
@Observable
@MainActor
final class AppState {
    // MARK: Connection
    private(set) var config: ServerConfig
    let client: APIClient
    private(set) var isConfigured: Bool

    // MARK: Dashboard
    var status: StatusResponse?
    var statusError: String?
    var lastStatusAt: Date?
    var isRefreshingStatus = false

    // MARK: Other cached data
    var settings: Settings?
    var brief: Brief?
    var chatMessages: [ChatMessage] = []
    var logEntries: [LogEntry] = []
    var openPhotoRequests: [PhotoRequest] = []
    var photos: [Photo] = []
    var openTasks: [TaskItem] = []
    var doneTasks: [TaskItem] = []

    @ObservationIgnored private var pollTask: Task<Void, Never>?
    @ObservationIgnored private var thumbCache: [Int: UIImage] = [:]
    @ObservationIgnored private var thumbInFlight: [Int: Task<UIImage?, Never>] = [:]
    @ObservationIgnored private let fullImageCache = NSCache<NSNumber, UIImage>()

    static let pollInterval: Duration = .seconds(15)
    private static let unitsDefaultsKey = "growop.units"

    init() {
        let cfg = ServerConfig.load()
        config = cfg
        client = APIClient(config: cfg)
        isConfigured = cfg.isConfigured
        fullImageCache.countLimit = 10
    }

    // MARK: Units

    var units: String {
        settings?.units ?? UserDefaults.standard.string(forKey: Self.unitsDefaultsKey) ?? "c"
    }
    var usesFahrenheit: Bool { units == "f" }
    var tempUnitLabel: String { usesFahrenheit ? "°F" : "°C" }

    // MARK: Connection management

    /// Runs the full connection chain for a candidate config (direct or through Home
    /// Assistant); if every step succeeds, saves it and becomes configured.
    @discardableResult
    func connect(_ candidate: ServerConfig) async throws -> HealthResponse {
        let result = try await client.verify(candidate)
        result.config.save()
        config = result.config
        client.update(config: result.config)
        isConfigured = true
        status = result.status
        statusError = nil
        lastStatusAt = Date()
        startPolling()
        Task { await refreshSettings() }
        return result.health
    }

    /// Convenience for direct (same Wi‑Fi) mode.
    @discardableResult
    func connect(url: String, key: String) async throws -> HealthResponse {
        try await connect(ServerConfig(mode: .direct, baseURL: url, apiKey: key))
    }

    func disconnect() {
        stopPolling()
        ServerConfig.clear()
        config = ServerConfig()
        client.update(config: config)
        isConfigured = false
        status = nil
        settings = nil
        brief = nil
        chatMessages = []
        logEntries = []
        openPhotoRequests = []
        photos = []
        openTasks = []
        doneTasks = []
        thumbCache = [:]
    }

    // MARK: Polling

    func startPolling() {
        guard isConfigured else { return }
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshStatus()
                try? await Task.sleep(for: AppState.pollInterval)
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel()
        pollTask = nil
    }

    func refreshStatus() async {
        guard isConfigured else { return }
        isRefreshingStatus = true
        defer { isRefreshingStatus = false }
        do {
            let st = try await client.status()
            status = st
            statusError = nil
            lastStatusAt = Date()
        } catch {
            statusError = error.localizedDescription
        }
    }

    // MARK: Settings

    func refreshSettings() async {
        guard isConfigured else { return }
        if let s = try? await client.settings() {
            settings = s
            if let u = s.units { UserDefaults.standard.set(u, forKey: Self.unitsDefaultsKey) }
        }
    }

    func saveSettings(_ fields: [String: JSONValue]) async throws {
        let s = try await client.updateSettings(fields)
        settings = s
        if let u = s.units { UserDefaults.standard.set(u, forKey: Self.unitsDefaultsKey) }
    }

    // MARK: Brief

    func loadBrief() async {
        guard isConfigured else { return }
        if let b = try? await client.brief() { brief = b }
    }

    func runBrief() async throws {
        let b = try await client.runBrief()
        brief = b
        await refreshStatus()
    }

    func markBriefRead() async {
        guard let b = brief, b.read != true else { return }
        try? await client.markBriefRead(id: b.id)
        brief?.read = true
        status?.unreadBrief = false
    }

    // MARK: Chat

    func loadChat() async {
        guard isConfigured else { return }
        if let r = try? await client.chatMessages(limit: 50) {
            chatMessages = (r.messages ?? []).sorted { $0.id < $1.id }
        }
    }

    func sendChat(_ text: String) async throws {
        // Optimistically show the user's message.
        let tempId = -(Int(Date().timeIntervalSince1970 * 1000))
        chatMessages.append(ChatMessage(id: tempId, role: "user", content: text, createdAt: Formatting.iso.string(from: Date())))
        do {
            let reply = try await client.sendChat(text)
            chatMessages.append(ChatMessage(id: reply.id ?? tempId - 1, role: "assistant", content: reply.reply ?? "", createdAt: Formatting.iso.string(from: Date())))
            await loadChat()
        } catch {
            chatMessages.removeAll { $0.id == tempId }
            throw error
        }
    }

    func clearChat() async throws {
        try await client.clearChat()
        chatMessages = []
    }

    // MARK: Log

    func loadLog() async {
        guard isConfigured else { return }
        if let r = try? await client.logEntries(limit: 50) {
            logEntries = (r.entries ?? []).sorted { $0.id > $1.id }
        }
    }

    func submitLog(_ req: LogRequest) async throws -> LogResponse {
        let r = try await client.submitLog(req)
        await loadLog()
        await refreshStatus()
        return r
    }

    // MARK: Photos

    func loadPhotoRequests() async {
        guard isConfigured else { return }
        if let r = try? await client.photoRequests(status: "open") {
            openPhotoRequests = (r.requests ?? []).sorted { $0.id > $1.id }
        }
    }

    func loadPhotos() async {
        guard isConfigured else { return }
        if let r = try? await client.photos(limit: 30) {
            photos = (r.photos ?? []).sorted { $0.id > $1.id }
        }
    }

    func skipPhotoRequest(id: Int) async throws {
        try await client.skipPhotoRequest(id: id)
        openPhotoRequests.removeAll { $0.id == id }
        await refreshStatus()
    }

    func uploadPhoto(image: UIImage, requestId: Int?, note: String?) async throws -> Photo {
        guard let data = ImageUtils.uploadData(for: image) else {
            throw APIError.other(NSError(domain: "GrowOp", code: 1, userInfo: [NSLocalizedDescriptionKey: "Couldn't prepare that photo."]))
        }
        let photo = try await client.uploadPhoto(jpeg: data, requestId: requestId, note: note)
        if let requestId { openPhotoRequests.removeAll { $0.id == requestId } }
        // Cache the (downscaled) image we just sent as the thumbnail for instant display.
        thumbCache[photo.id] = ImageUtils.downscaled(image, maxLongEdge: 300)
        await loadPhotos()
        await loadPhotoRequests()
        await refreshStatus()
        return photo
    }

    func thumbnail(for id: Int) async -> UIImage? {
        if let img = thumbCache[id] { return img }
        if let t = thumbInFlight[id] { return await t.value }
        let client = self.client
        let task = Task<UIImage?, Never> {
            guard let data = try? await client.photoThumbData(id: id) else { return nil }
            return UIImage(data: data)
        }
        thumbInFlight[id] = task
        let img = await task.value
        thumbInFlight[id] = nil
        if let img { thumbCache[id] = img }
        return img
    }

    func fullImage(for id: Int) async -> UIImage? {
        if let img = fullImageCache.object(forKey: NSNumber(value: id)) { return img }
        guard let data = try? await client.photoImageData(id: id), let img = UIImage(data: data) else { return nil }
        fullImageCache.setObject(img, forKey: NSNumber(value: id))
        return img
    }

    // MARK: Tasks

    func loadTasks(includeDone: Bool = false) async {
        guard isConfigured else { return }
        if let r = try? await client.tasks(status: "open") {
            openTasks = sortTasks(r.tasks ?? [])
        }
        if includeDone, let r = try? await client.tasks(status: "done") {
            doneTasks = (r.tasks ?? []).sorted { $0.id > $1.id }
        }
    }

    private func sortTasks(_ tasks: [TaskItem]) -> [TaskItem] {
        tasks.sorted { a, b in
            if a.isHigh != b.isHigh { return a.isHigh }
            let da = a.due ?? "9999", db = b.due ?? "9999"
            if da != db { return da < db }
            return a.id < b.id
        }
    }

    func completeTask(_ task: TaskItem) async throws {
        let updated = try await client.completeTask(id: task.id)
        openTasks.removeAll { $0.id == task.id }
        doneTasks.insert(updated, at: 0)
        status?.openTasks = openTasks.count
    }

    func reopenTask(_ task: TaskItem) async throws {
        let updated = try await client.reopenTask(id: task.id)
        doneTasks.removeAll { $0.id == task.id }
        openTasks = sortTasks(openTasks + [updated])
        status?.openTasks = openTasks.count
    }

    func addTask(title: String, detail: String?, due: String?) async throws {
        let t = try await client.createTask(NewTaskRequest(title: title, detail: detail, due: due))
        openTasks = sortTasks(openTasks + [t])
        status?.openTasks = openTasks.count
    }

    // MARK: Devices / control

    func setOverride(role: String, mode: String) async throws {
        let minutes: Int? = (mode == "auto") ? nil : 60
        let updated = try await client.overrideDevice(role: role, mode: mode, minutes: minutes)
        if var devs = status?.devices, let i = devs.firstIndex(where: { $0.role == role }) {
            devs[i] = updated
            status?.devices = devs
        }
    }

    func pauseControl(minutes: Int = 30) async throws {
        try await client.pauseControl(minutes: minutes)
        await refreshStatus()
    }

    func resumeControl() async throws {
        try await client.resumeControl()
        await refreshStatus()
    }
}

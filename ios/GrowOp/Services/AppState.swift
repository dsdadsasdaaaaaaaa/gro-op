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
    var history: [HistoryPoint] = []
    @ObservationIgnored private var lastPlanAt: [Int: Date] = [:]

    // MARK: Plants (one person per plant; the tent itself is shared)
    var plants: [Plant] = []
    /// nil = not known yet; false = the backend has no /api/plants (older add-on).
    var plantsSupported: Bool?
    private(set) var myPlantId: Int? = UserDefaults.standard.object(forKey: AppState.myPlantKey) as? Int
    var selectedPlantId: Int?
    private var plantChoiceDismissed = UserDefaults.standard.bool(forKey: AppState.plantSkipKey)
    private static let myPlantKey = "growop.myPlantId"
    private static let plantSkipKey = "growop.plantChoiceSkipped"
    /// Plans cached per plant id (0 = no plant / older backend).
    var plans: [Int: GrowPlan] = [:]

    // MARK: Tent camera
    var cameraImage: UIImage?
    var cameraImageAt: Date?
    var cameraError: String?
    @ObservationIgnored private var snapshotInFlight = false
    @ObservationIgnored private let frameCache = NSCache<NSNumber, UIImage>()
    @ObservationIgnored private var frameInFlight: [Int: Task<UIImage?, Never>] = [:]
    @ObservationIgnored private var lastHistoryAt: Date?
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
        frameCache.countLimit = 120
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
        stopPolling()
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
        plans = [:]
        lastPlanAt = [:]
        plants = []
        plantsSupported = nil
        selectedPlantId = nil
        plantChoiceDismissed = false
        tasksLoaded = false
        requestsLoaded = false
        history = []
        lastHistoryAt = nil
        cameraImage = nil
        cameraImageAt = nil
        cameraError = nil
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
        guard isConfigured, pollTask == nil else { return }
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
            let previous = status
            status = st
            statusError = nil
            lastStatusAt = Date()
            if let list = st.plants {
                plantsSupported = true
                applyPlants(list)
            }
            // The plan only changes with the grow (stage / the plant's start date), so reload it when
            // those change, when we don't have one yet, or every 10 minutes as a safety net.
            let prevStart = previous?.plants?.first { $0.id == selectedPlantId }?.startDate ?? previous?.grow?.startDate
            let newStart = selectedPlant?.startDate ?? st.grow?.startDate
            let growChanged = previous?.grow?.stage != st.grow?.stage || prevStart != newStart
            let stale = lastPlanAt[planKey].map { Date().timeIntervalSince($0) > 600 } ?? true
            if plan == nil || growChanged || stale {
                await loadPlan()
            }
            let historyStale = lastHistoryAt.map { Date().timeIntervalSince($0) > 300 } ?? true
            if historyStale { await loadHistory() }
            // keep the tab badges honest: if the server's counts moved, reload the lists behind them
            if tasksLoaded, st.openTasks != previous?.openTasks { await loadTasks() }
            if requestsLoaded, st.openPhotoRequests != previous?.openPhotoRequests { await loadPhotoRequests() }
        } catch {
            if case APIError.network(let e) = error, e.code == .cancelled { return }
            statusError = error.localizedDescription
        }
    }

    // MARK: History (24 h sparklines)

    func loadHistory(force: Bool = false) async {
        guard isConfigured else { return }
        if !force, let t = lastHistoryAt, Date().timeIntervalSince(t) < 60 { return }
        if let h = try? await client.history(hours: 24) {
            history = (h.points ?? []).sorted { ($0.t ?? "") < ($1.t ?? "") }
            lastHistoryAt = Date()
        }
    }

    // MARK: Plants

    var selectedPlant: Plant? { plants.first { $0.id == selectedPlantId } }
    var myPlant: Plant? { plants.first { $0.id == myPlantId } }

    /// True when the backend knows about plants but this phone hasn't said which one is "mine".
    var needsPlantChoice: Bool {
        plantsSupported == true && (myPlantId == nil || !plants.contains { $0.id == myPlantId })
    }
    var showPlantChoice: Bool { needsPlantChoice && !plantChoiceDismissed }
    func dismissPlantChoice() {
        plantChoiceDismissed = true
        UserDefaults.standard.set(true, forKey: Self.plantSkipKey)
    }

    func loadPlants() async {
        guard isConfigured else { return }
        do {
            let r = try await client.plants()
            plantsSupported = true
            applyPlants(r.plants ?? [])
        } catch let e as APIError {
            if case .http(let status, _) = e, status == 404 { plantsSupported = false }
        } catch {}
    }

    private func applyPlants(_ list: [Plant]) {
        plants = list.sorted { $0.id < $1.id }
        // Keep a valid selection: my plant first, else the first plant.
        if selectedPlantId == nil || !plants.contains(where: { $0.id == selectedPlantId }) {
            selectedPlantId = (myPlantId.flatMap { id in plants.first { $0.id == id } } ?? plants.first)?.id
        }
    }

    func selectPlant(_ id: Int?) {
        guard id != selectedPlantId else { return }
        selectedPlantId = id
        if plan == nil { Task { await loadPlan() } }
    }

    func setMyPlant(_ id: Int?) {
        myPlantId = id
        if let id { UserDefaults.standard.set(id, forKey: Self.myPlantKey) } else { UserDefaults.standard.removeObject(forKey: Self.myPlantKey) }
        if let id { selectPlant(id) }
    }

    @discardableResult
    func createPlant(_ fields: [String: JSONValue]) async throws -> Plant {
        let p = try await client.createPlant(fields)
        plantsSupported = true
        applyPlants(plants.filter { $0.id != p.id } + [p])
        return p
    }

    @discardableResult
    func updatePlant(id: Int, _ fields: [String: JSONValue]) async throws -> Plant {
        let p = try await client.updatePlant(id: id, fields)
        applyPlants(plants.map { $0.id == p.id ? p : $0 })
        plans[p.id] = nil
        if selectedPlantId == p.id { await loadPlan() }
        return p
    }

    func deletePlant(id: Int) async throws {
        try await client.deletePlant(id: id)
        plans[id] = nil
        if myPlantId == id { setMyPlant(nil) }
        applyPlants(plants.filter { $0.id != id })
        if selectedPlantId == id { selectedPlantId = plants.first?.id }
    }

    /// Items with no plant_id belong to the whole tent and show under every plant.
    func belongsToSelected(_ plantId: Int?) -> Bool {
        plantId == nil || plantId == selectedPlantId || plants.isEmpty
    }
    var logEntriesForSelected: [LogEntry] { logEntries.filter { belongsToSelected($0.plantId) } }
    var openRequestsForSelected: [PhotoRequest] { openPhotoRequests.filter { belongsToSelected($0.plantId) } }
    var photosForSelected: [Photo] { photos.filter { belongsToSelected($0.plantId) } }
    var plantTasks: [TaskItem] { openTasks.filter { plants.isEmpty ? true : $0.plantId == selectedPlantId } }
    var tentTasks: [TaskItem] { plants.isEmpty ? [] : openTasks.filter { $0.plantId == nil } }
    var doneTasksForSelected: [TaskItem] { doneTasks.filter { belongsToSelected($0.plantId) } }
    var needsYouTaskCount: Int { tasksLoaded ? plantTasks.count + tentTasks.count : (status?.openTasks ?? 0) }
    var needsYouPhotoCount: Int { requestsLoaded ? openRequestsForSelected.count : (status?.openPhotoRequests ?? 0) }
    private var tasksLoaded = false
    private var requestsLoaded = false

    // MARK: Humidifier water

    func markHumidifierRefilled() async throws {
        try await client.humidifierRefilled()
        await refreshStatus()
    }

    // MARK: Tent camera

    var hasCamera: Bool { status?.camera != nil }

    /// One fresh snapshot; overlapping calls are coalesced.
    func refreshCameraSnapshot() async {
        guard isConfigured, !snapshotInFlight else { return }
        snapshotInFlight = true
        defer { snapshotInFlight = false }
        do {
            let data = try await client.cameraSnapshot()
            if let img = UIImage(data: data) {
                cameraImage = img
                cameraImageAt = Date()
                cameraError = nil
            } else {
                cameraError = "The camera sent something that isn't an image."
            }
        } catch let e as APIError {
            if case .http(_, let detail) = e, let detail, !detail.isEmpty { cameraError = detail } else { cameraError = e.localizedDescription }
        } catch {
            cameraError = error.localizedDescription
        }
    }

    func cameraFrames(days: Int) async -> [CameraFrame] {
        guard isConfigured else { return [] }
        let r = try? await client.cameraFrames(days: days)
        return (r?.frames ?? []).sorted { ($0.t ?? "") < ($1.t ?? "") }
    }

    func cachedFrame(for id: Int) -> UIImage? { frameCache.object(forKey: NSNumber(value: id)) }

    func frame(for id: Int) async -> UIImage? {
        if let img = cachedFrame(for: id) { return img }
        if let t = frameInFlight[id] { return await t.value }
        let client = self.client
        let task = Task<UIImage?, Never> {
            guard let data = try? await client.cameraFrameData(id: id) else { return nil }
            return UIImage(data: data)
        }
        frameInFlight[id] = task
        let img = await task.value
        frameInFlight[id] = nil
        if let img { frameCache.setObject(img, forKey: NSNumber(value: id)) }
        return img
    }

    /// "Look now": the backend takes a snapshot and runs the advisor on it for the selected plant.
    func analyseCamera(note: String? = nil) async throws -> Photo {
        let photo = try await client.cameraAnalyse(plantId: selectedPlantId, note: note)
        await loadPhotos()
        await loadPhotoRequests()
        await refreshStatus()
        return photo
    }

    @discardableResult
    func setCamera(entityId: String?) async throws -> CameraResponse {
        let r = try await client.setCamera(entityId: entityId)
        status?.camera = r.camera
        cameraImage = nil
        cameraImageAt = nil
        cameraError = nil
        return r
    }

    // MARK: Plan (per selected plant)

    private var planKey: Int { selectedPlantId ?? 0 }
    var plan: GrowPlan? { plans[planKey] }

    func loadPlan() async {
        guard isConfigured else { return }
        let key = planKey
        if let p = try? await client.getPlan(plantId: selectedPlantId) {
            plans[key] = p
            lastPlanAt[key] = Date()
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

    func sendChat(_ text: String, plantId: Int?) async throws {
        // Optimistically show the user's message.
        let tempId = -(Int(Date().timeIntervalSince1970 * 1000))
        let author = myPlant?.owner ?? plants.first { $0.id == plantId }?.owner
        chatMessages.append(ChatMessage(id: tempId, role: "user", content: text, createdAt: Formatting.iso.string(from: Date()), author: author, plantId: plantId))
        do {
            let reply = try await client.sendChat(text, plantId: plantId, author: myPlant?.owner)
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
        var req = req
        if req.plantId == nil { req.plantId = selectedPlantId }
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
            requestsLoaded = true
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

    func uploadPhoto(image: UIImage, requestId: Int?, note: String?, plantId: Int? = nil) async throws -> Photo {
        guard let data = ImageUtils.uploadData(for: image) else {
            throw APIError.other(NSError(domain: "GrowOp", code: 1, userInfo: [NSLocalizedDescriptionKey: "Couldn't prepare that photo."]))
        }
        let photo = try await client.uploadPhoto(jpeg: data, requestId: requestId, note: note, plantId: plantId ?? selectedPlantId)
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
            tasksLoaded = true
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

    /// The task just ticked off, offered back for a few seconds in case the tap was a slip.
    var undoTask: TaskItem?
    @ObservationIgnored private var undoClear: Task<Void, Never>?

    func completeWithUndo(_ task: TaskItem) async throws {
        try await completeTask(task)
        undoTask = task
        undoClear?.cancel()
        undoClear = Task { [weak self] in
            try? await Task.sleep(for: .seconds(6))
            if !Task.isCancelled { self?.undoTask = nil }
        }
    }

    func undoLastComplete() async {
        guard let t = undoTask else { return }
        undoTask = nil
        undoClear?.cancel()
        try? await reopenTask(t)
        await refreshStatus()
    }

    func reopenTask(_ task: TaskItem) async throws {
        let updated = try await client.reopenTask(id: task.id)
        doneTasks.removeAll { $0.id == task.id }
        openTasks = sortTasks(openTasks + [updated])
        status?.openTasks = openTasks.count
    }

    /// `plantId` nil = a task for the whole tent.
    func addTask(title: String, detail: String?, due: String?, plantId: Int?) async throws {
        let t = try await client.createTask(NewTaskRequest(title: title, detail: detail, due: due, plantId: plantId))
        openTasks = sortTasks(openTasks + [t])
        status?.openTasks = openTasks.count
    }

    // MARK: Devices / control

    var isStandby: Bool { status?.standby == true }

    /// `minutes` nil = until changed back to auto (ignored for "auto").
    func setOverride(role: String, mode: String, minutes: Int? = 60) async throws {
        let minutes: Int? = (mode == "auto") ? nil : minutes
        let updated = try await client.overrideDevice(role: role, mode: mode, minutes: minutes)
        if var devs = status?.devices, let i = devs.firstIndex(where: { $0.role == role }) {
            devs[i] = updated
            status?.devices = devs
        }
    }

    func setStandby() async throws {
        let r = try await client.setStandby()
        status?.standby = r.standby ?? true
        await refreshStatus()
    }

    func startTent() async throws {
        let r = try await client.startTent()
        status?.standby = r.standby ?? false
        status?.controlPausedUntil = nil
        await refreshStatus()
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

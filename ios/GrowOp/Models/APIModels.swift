import Foundation

// MARK: - Codable models mirroring docs/API.md exactly.
// All keys use explicit CodingKeys. Most fields are optional so a partially
// implemented backend never crashes the app; required-by-contract fields have
// sensible fallbacks where the UI needs them.

// MARK: JSON value (for target_changes from/to and partial PUT bodies)

enum JSONValue: Codable, Equatable, CustomStringConvertible {
    case string(String)
    case number(Double)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null; return }
        if let b = try? c.decode(Bool.self) { self = .bool(b); return }
        if let d = try? c.decode(Double.self) { self = .number(d); return }
        if let s = try? c.decode(String.self) { self = .string(s); return }
        // Fall back to a string description for arrays/objects we don't model.
        self = .string("")
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .string(let s): try c.encode(s)
        case .number(let d):
            if d == d.rounded(), abs(d) < 1e15 { try c.encode(Int(d)) } else { try c.encode(d) }
        case .bool(let b): try c.encode(b)
        case .null: try c.encodeNil()
        }
    }

    var description: String {
        switch self {
        case .string(let s): return s
        case .number(let d): return Formatting.number(d)
        case .bool(let b): return b ? "yes" : "no"
        case .null: return "—"
        }
    }
}

// MARK: Health

struct HealthResponse: Codable {
    var ok: Bool
    var version: String?
    var haConnected: Bool?
    var advisorEnabled: Bool?

    enum CodingKeys: String, CodingKey {
        case ok, version
        case haConnected = "ha_connected"
        case advisorEnabled = "advisor_enabled"
    }
}

// MARK: Error body

struct APIErrorBody: Codable {
    var detail: String?
}

// MARK: Status

struct SensorReading: Codable {
    var tempC: Double?
    var tempF: Double?
    var humidity: Double?
    var vpdKpa: Double?
    var updatedAt: String?
    var stale: Bool?

    enum CodingKeys: String, CodingKey {
        case tempC = "temp_c"
        case tempF = "temp_f"
        case humidity
        case vpdKpa = "vpd_kpa"
        case updatedAt = "updated_at"
        case stale
    }
}

struct GrowProfile: Codable {
    var strain: String?
    var breeder: String?
    var seedType: String?
    var medium: String?
    var potSizeL: Double?
    var plantCount: Int?
    var startDate: String?
    var stage: String?
    var stageStarted: String?
    var flowerStartDate: String?
    var expectedFlowerDays: Int?
    var exhaustDucted: Bool?
    var notes: String?
    // Present only inside GET /api/status "grow"
    var dayInStage: Int?
    var dayTotal: Int?
    var expectedHarvestDate: String?

    enum CodingKeys: String, CodingKey {
        case strain, breeder, medium, stage, notes
        case seedType = "seed_type"
        case potSizeL = "pot_size_l"
        case plantCount = "plant_count"
        case startDate = "start_date"
        case stageStarted = "stage_started"
        case flowerStartDate = "flower_start_date"
        case expectedFlowerDays = "expected_flower_days"
        case exhaustDucted = "exhaust_ducted"
        case dayInStage = "day_in_stage"
        case dayTotal = "day_total"
        case expectedHarvestDate = "expected_harvest_date"
    }

    static let stages = ["seedling", "veg", "flower", "flush", "drying", "curing", "done"]
    static let mediums = ["soil", "coco", "hydro", "other"]
}

struct Targets: Codable {
    var tempMinC: Double?
    var tempMaxC: Double?
    var tempMinF: Double?
    var tempMaxF: Double?
    var humidityMin: Double?
    var humidityMax: Double?
    var vpdMin: Double?
    var vpdMax: Double?
    var lightOnTime: String?
    var lightHours: Double?
    var source: String?
    var note: String?

    enum CodingKeys: String, CodingKey {
        case tempMinC = "temp_min_c"
        case tempMaxC = "temp_max_c"
        case tempMinF = "temp_min_f"
        case tempMaxF = "temp_max_f"
        case humidityMin = "humidity_min"
        case humidityMax = "humidity_max"
        case vpdMin = "vpd_min"
        case vpdMax = "vpd_max"
        case lightOnTime = "light_on_time"
        case lightHours = "light_hours"
        case source, note
    }
}

struct LightStatus: Codable {
    var isOn: Bool?
    var nextChangeAt: String?
    var schedule: String?

    enum CodingKeys: String, CodingKey {
        case isOn = "is_on"
        case nextChangeAt = "next_change_at"
        case schedule
    }
}

struct DeviceStatus: Codable, Identifiable {
    var role: String
    var label: String?
    var kind: String?
    var entityId: String?
    var state: String?
    var mode: String?
    var overrideUntil: String?
    var reason: String?
    var available: Bool?

    var id: String { role }

    enum CodingKeys: String, CodingKey {
        case role, label, kind, state, mode, reason, available
        case entityId = "entity_id"
        case overrideUntil = "override_until"
    }

    var displayLabel: String { label ?? role.replacingOccurrences(of: "_", with: " ").capitalized }
    var isSwitch: Bool { (kind ?? "switch") == "switch" }
    var isOn: Bool { state == "on" }
}

/// Known assessment levels. Unknown strings decode as `.warn` so a newer backend never crashes the app.
enum AssessmentLevel: String {
    case good, warn, alert, standby
}

struct Assessment: Codable {
    var level: String?
    var headline: String?
    var details: [String]?

    enum CodingKeys: String, CodingKey { case level, headline, details }

    var levelValue: AssessmentLevel { AssessmentLevel(rawValue: (level ?? "").lowercased()) ?? .warn }
}

struct AlertItem: Codable, Identifiable {
    var id: Int
    var level: String?
    var message: String?
    var at: String?
}

struct StatusResponse: Codable {
    var time: String?
    var haConnected: Bool?
    var sensor: SensorReading?
    var grow: GrowProfile?
    var targets: Targets?
    var light: LightStatus?
    var devices: [DeviceStatus]?
    var assessment: Assessment?
    var openTasks: Int?
    var openPhotoRequests: Int?
    var unreadBrief: Bool?
    var alerts: [AlertItem]?
    var controlPausedUntil: String?
    var standby: Bool?
    var plants: [Plant]?
    var camera: CameraInfo?

    enum CodingKeys: String, CodingKey {
        case time, sensor, grow, targets, light, devices, assessment, alerts, standby, plants, camera
        case haConnected = "ha_connected"
        case openTasks = "open_tasks"
        case openPhotoRequests = "open_photo_requests"
        case unreadBrief = "unread_brief"
        case controlPausedUntil = "control_paused_until"
    }
}

// MARK: Devices

struct DeviceRole: Codable, Identifiable {
    var role: String
    var label: String?
    var kind: String?
    var required: Bool?
    var description: String?

    var id: String { role }
    var displayLabel: String { label ?? role.replacingOccurrences(of: "_", with: " ").capitalized }
    var isSwitch: Bool { (kind ?? "switch") == "switch" }
}

struct DevicesResponse: Codable {
    var devices: [DeviceStatus]?
    var roles: [DeviceRole]?
}

struct DeviceMapRequest: Codable {
    var entityId: String?
    enum CodingKeys: String, CodingKey { case entityId = "entity_id" }
    // Always emit the key (null to unmap), per API.md.
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(entityId, forKey: .entityId)
    }
}

struct DeviceOverrideRequest: Codable {
    var mode: String
    var minutes: Int?
}

// MARK: Home Assistant entities

struct HAEntity: Codable, Identifiable {
    var entityId: String
    var name: String?
    var domain: String?
    var state: String?
    var unit: String?
    var deviceClass: String?
    var suggestedRole: String?

    var id: String { entityId }

    enum CodingKeys: String, CodingKey {
        case name, domain, state, unit
        case entityId = "entity_id"
        case deviceClass = "device_class"
        case suggestedRole = "suggested_role"
    }

    var displayName: String {
        if let n = name, !n.isEmpty { return n }
        return entityId
    }
}

struct HAEntitiesResponse: Codable {
    var entities: [HAEntity]?
}

// MARK: Plants

struct Plant: Codable, Identifiable, Equatable {
    var id: Int
    var name: String?
    var owner: String?
    var strain: String?
    var breeder: String?
    var seedType: String?
    var medium: String?
    var potSizeL: Double?
    var startDate: String?
    var notes: String?
    var notifyService: String?
    var dayTotal: Int?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, name, owner, strain, breeder, medium, notes
        case seedType = "seed_type"
        case potSizeL = "pot_size_l"
        case startDate = "start_date"
        case notifyService = "notify_service"
        case dayTotal = "day_total"
        case createdAt = "created_at"
    }

    var displayName: String {
        if let n = name, !n.isEmpty { return n }
        if let o = owner, !o.isEmpty { return "\(o)'s plant" }
        return "Plant \(id)"
    }

    /// Short label for the segmented switcher: "Levi's plant" → "Levi's".
    var shortName: String {
        let n = displayName
        for suffix in [" plant", " Plant"] where n.hasSuffix(suffix) {
            let t = String(n.dropLast(suffix.count)).trimmingCharacters(in: .whitespaces)
            if !t.isEmpty { return t }
        }
        if let o = owner, !o.isEmpty, n.count > 12 { return "\(o)'s" }
        return n
    }
}

struct PlantsResponse: Codable {
    var plants: [Plant]?
}

struct OKResponse: Codable {
    var ok: Bool?
}

// MARK: Tent camera

struct CameraInfo: Codable {
    var entityId: String?
    var name: String?
    var available: Bool?
    var snapshotUrl: String?
    var streamUrl: String?
    var lastFrameAt: String?
    var frameCount: Int?
    var error: String?

    enum CodingKeys: String, CodingKey {
        case name, available, error
        case entityId = "entity_id"
        case snapshotUrl = "snapshot_url"
        case streamUrl = "stream_url"
        case lastFrameAt = "last_frame_at"
        case frameCount = "frame_count"
    }

    var displayName: String {
        if let n = name, !n.isEmpty { return n }
        return entityId ?? "Tent camera"
    }
}

struct CameraCandidate: Codable, Identifiable {
    var entityId: String
    var name: String?
    var state: String?
    var brand: String?
    var model: String?

    var id: String { entityId }

    enum CodingKeys: String, CodingKey {
        case name, state, brand, model
        case entityId = "entity_id"
    }

    var displayName: String { (name?.isEmpty == false) ? name! : entityId }
}

struct CameraResponse: Codable {
    var camera: CameraInfo?
    var candidates: [CameraCandidate]?
}

struct CameraSelectRequest: Codable {
    var entityId: String?
    enum CodingKeys: String, CodingKey { case entityId = "entity_id" }
    // Always emit the key (null = off).
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(entityId, forKey: .entityId)
    }
}

struct CameraFrame: Codable, Identifiable {
    var id: Int
    var t: String?
    var lightsOn: Bool?
    var url: String?

    enum CodingKeys: String, CodingKey {
        case id, t, url
        case lightsOn = "lights_on"
    }
}

struct CameraFramesResponse: Codable {
    var frames: [CameraFrame]?
}

struct CameraAnalyseRequest: Codable {
    var plantId: Int?
    var note: String?

    enum CodingKeys: String, CodingKey {
        case note
        case plantId = "plant_id"
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(plantId, forKey: .plantId)
        try c.encodeIfPresent(note, forKey: .note)
    }
}

// MARK: Grow stage

struct StageChangeRequest: Codable {
    var stage: String
}

// MARK: History

struct HistoryPoint: Codable {
    var t: String?
    var tempC: Double?
    var tempF: Double?
    var humidity: Double?
    var vpdKpa: Double?
    var lightOn: Bool?

    enum CodingKeys: String, CodingKey {
        case t, humidity
        case tempC = "temp_c"
        case tempF = "temp_f"
        case vpdKpa = "vpd_kpa"
        case lightOn = "light_on"
    }
}

struct HistoryResponse: Codable {
    var points: [HistoryPoint]?
}

// MARK: Log

struct LogRequest: Codable {
    var kind: String
    var value: Double?
    var unit: String?
    var context: String?
    var note: String?
    var plantId: Int? = nil

    enum CodingKeys: String, CodingKey {
        case kind, value, unit, context, note
        case plantId = "plant_id"
    }
}

struct LogEntry: Codable, Identifiable {
    var id: Int
    var createdAt: String?
    var kind: String?
    var value: Double?
    var unit: String?
    var context: String?
    var note: String?
    var adviceSummary: String?
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case id, kind, value, unit, context, note
        case createdAt = "created_at"
        case adviceSummary = "advice_summary"
        case plantId = "plant_id"
    }
}

struct Advice: Codable {
    var summary: String?
    var steps: [String]?
    var urgency: String?
    var photoRequests: [PhotoRequest]?
    var tasks: [TaskItem]?

    enum CodingKeys: String, CodingKey {
        case summary, steps, urgency, tasks
        case photoRequests = "photo_requests"
    }
}

struct LogResponse: Codable {
    var entry: LogEntry?
    var advice: Advice?
}

struct LogListResponse: Codable {
    var entries: [LogEntry]?
}

// MARK: Photos

struct PhotoRequest: Codable, Identifiable {
    var id: Int
    var createdAt: String?
    var title: String?
    var instructions: String?
    var reason: String?
    var status: String?
    var photoId: Int?
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, instructions, reason, status
        case createdAt = "created_at"
        case photoId = "photo_id"
        case plantId = "plant_id"
    }
}

struct PhotoRequestsResponse: Codable {
    var requests: [PhotoRequest]?
}

struct PhotoFinding: Codable, Identifiable {
    var title: String?
    var severity: String?
    var detail: String?
    var id: String { (title ?? "") + (detail ?? "") }
}

struct PhotoAnalysis: Codable {
    var summary: String?
    var healthScore: Double?
    var findings: [PhotoFinding]?
    var actions: [String]?
    var photoRequests: [PhotoRequest]?
    var tasks: [TaskItem]?

    enum CodingKeys: String, CodingKey {
        case summary, findings, actions, tasks
        case healthScore = "health_score"
        case photoRequests = "photo_requests"
    }
}

struct Photo: Codable, Identifiable {
    var id: Int
    var createdAt: String?
    var requestId: Int?
    var note: String?
    var analysis: PhotoAnalysis?
    var imageUrl: String?
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case id, note, analysis
        case createdAt = "created_at"
        case requestId = "request_id"
        case imageUrl = "image_url"
        case plantId = "plant_id"
    }

    /// Photos the backend took from the tent camera ("look now" or brief frames).
    var isFromCamera: Bool { (note ?? "").hasPrefix("Tent camera snapshot") }
}

struct PhotosResponse: Codable {
    var photos: [Photo]?
}

// MARK: Tasks

struct TaskItem: Codable, Identifiable {
    var id: Int
    var title: String?
    var detail: String?
    var due: String?
    var priority: String?
    var status: String?
    var createdBy: String?
    var createdAt: String?
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, detail, due, priority, status
        case createdBy = "created_by"
        case createdAt = "created_at"
        case plantId = "plant_id"
    }

    var isDone: Bool { status == "done" }
    var isHigh: Bool { priority == "high" }
}

struct TasksResponse: Codable {
    var tasks: [TaskItem]?
}

struct NewTaskRequest: Codable {
    var title: String
    var detail: String?
    var due: String?
    /// nil = a task for the whole tent (sent as an explicit JSON null).
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case title, detail, due
        case plantId = "plant_id"
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(title, forKey: .title)
        try c.encodeIfPresent(detail, forKey: .detail)
        try c.encodeIfPresent(due, forKey: .due)
        try c.encode(plantId, forKey: .plantId)
    }
}

// MARK: Brief

struct TargetChange: Codable, Identifiable {
    var field: String?
    var from: JSONValue?
    var to: JSONValue?
    var reason: String?
    var id: String { (field ?? "") + (reason ?? "") }
}

struct Brief: Codable, Identifiable {
    var id: Int
    var createdAt: String?
    var headline: String?
    var summary: String?
    var concerns: [String]?
    var actions: [String]?
    var targetChanges: [TargetChange]?
    var photoRequests: [PhotoRequest]?
    var tasks: [TaskItem]?
    var read: Bool?
    var perPlant: [BriefPerPlant]?
    var cameraFrameAt: String?

    enum CodingKeys: String, CodingKey {
        case id, headline, summary, concerns, actions, tasks, read
        case createdAt = "created_at"
        case targetChanges = "target_changes"
        case photoRequests = "photo_requests"
        case perPlant = "per_plant"
        case cameraFrameAt = "camera_frame_at"
    }
}

struct BriefPerPlant: Codable, Identifiable {
    var plantId: Int?
    var name: String?
    var headline: String?
    var summary: String?

    var id: String { "\(plantId ?? -1)-\(name ?? "")" }

    enum CodingKeys: String, CodingKey {
        case name, headline, summary
        case plantId = "plant_id"
    }
}

// MARK: Chat

struct ChatMessage: Codable, Identifiable {
    var id: Int
    var role: String?
    var content: String?
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, role, content
        case createdAt = "created_at"
    }
    var isUser: Bool { role == "user" }
}

struct ChatListResponse: Codable {
    var messages: [ChatMessage]?
}

struct ChatSendRequest: Codable {
    var message: String
    var plantId: Int?

    enum CodingKeys: String, CodingKey {
        case message
        case plantId = "plant_id"
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(message, forKey: .message)
        try c.encode(plantId, forKey: .plantId)
    }
}

struct ChatReply: Codable {
    var id: Int?
    var reply: String?
}

// MARK: Events

struct EventItem: Codable, Identifiable {
    var id: Int
    var at: String?
    var level: String?
    var kind: String?
    var message: String?
}

struct EventsResponse: Codable {
    var events: [EventItem]?
}

// MARK: Settings

struct Settings: Codable {
    var units: String?
    var briefTime: String?
    var timezone: String?
    var autoApplyAdvisorTargets: Bool?
    var notifyService: String?
    var notifyServicesAvailable: [String]?
    var model: String?
    var advisorEnabled: Bool?
    var safetyTempMaxC: Double?
    var safetyTempMinC: Double?
    var controlIntervalS: Double?
    var minSwitchIntervalS: Double?
    var cameraEntity: String?
    var cameraCaptureMinutes: Double?
    var advisorMonthUsd: Double?

    enum CodingKeys: String, CodingKey {
        case units, timezone, model
        case cameraEntity = "camera_entity"
        case cameraCaptureMinutes = "camera_capture_minutes"
        case briefTime = "brief_time"
        case autoApplyAdvisorTargets = "auto_apply_advisor_targets"
        case notifyService = "notify_service"
        case notifyServicesAvailable = "notify_services_available"
        case advisorEnabled = "advisor_enabled"
        case safetyTempMaxC = "safety_temp_max_c"
        case safetyTempMinC = "safety_temp_min_c"
        case controlIntervalS = "control_interval_s"
        case minSwitchIntervalS = "min_switch_interval_s"
        case advisorMonthUsd = "advisor_month_usd"
    }
}

// MARK: Control

struct PauseRequest: Codable {
    var minutes: Int
}

struct StandbyResponse: Codable {
    var standby: Bool?
    var controlPausedUntil: String?
    enum CodingKeys: String, CodingKey {
        case standby
        case controlPausedUntil = "control_paused_until"
    }
}

// MARK: Grow plan (GET /api/plan)

struct PlanPhase: Codable, Identifiable {
    var key: String
    var title: String?
    var subtitle: String?
    var startDay: Int?
    var endDay: Int?
    var startDate: String?
    var endDate: String?
    var status: String?
    var what: [String]?
    var watchFor: [String]?
    var environment: String?

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, title, subtitle, status, what, environment
        case startDay = "start_day"
        case endDay = "end_day"
        case startDate = "start_date"
        case endDate = "end_date"
        case watchFor = "watch_for"
    }

    var displayTitle: String { title ?? key.replacingOccurrences(of: "_", with: " ").capitalized }
    var isDone: Bool { status == "done" }
    var isCurrent: Bool { status == "current" }
    var isUpcoming: Bool { !isDone && !isCurrent }
}

struct GrowPlan: Codable {
    var startDate: String?
    var today: String?
    var dayTotal: Int?
    var currentPhase: String?
    var phases: [PlanPhase]?

    enum CodingKeys: String, CodingKey {
        case today, phases
        case startDate = "start_date"
        case dayTotal = "day_total"
        case currentPhase = "current_phase"
    }

    var orderedPhases: [PlanPhase] { phases ?? [] }

    /// The phase flagged `current` (authoritative), falling back to `current_phase` by key.
    var current: PlanPhase? {
        orderedPhases.first { $0.isCurrent } ?? orderedPhases.first { $0.key == currentPhase }
    }

    /// The phase that follows the current one, or the first upcoming phase.
    var next: PlanPhase? {
        let phases = orderedPhases
        if let cur = current, let i = phases.firstIndex(where: { $0.key == cur.key }), i + 1 < phases.count {
            return phases[i + 1]
        }
        if current == nil { return phases.first { $0.isUpcoming } }
        return nil
    }

    var allDone: Bool { !orderedPhases.isEmpty && orderedPhases.allSatisfy { $0.isDone } }
}

// MARK: - Formatting helpers shared by views

enum Formatting {
    static let isoWithFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    static let iso: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
    static let dayFormatter: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone.current
        return f
    }()

    /// Parses ISO-8601 timestamps (with or without fractional seconds, with or without "Z").
    static func parseISO(_ s: String?) -> Date? {
        guard var s = s, !s.isEmpty else { return nil }
        if let d = isoWithFraction.date(from: s) { return d }
        if let d = iso.date(from: s) { return d }
        // Tolerate a missing timezone designator: treat as UTC.
        if !s.hasSuffix("Z"), !s.contains("+"), s.range(of: #"-\d\d:\d\d$"#, options: .regularExpression) == nil {
            s += "Z"
            if let d = isoWithFraction.date(from: s) { return d }
            if let d = iso.date(from: s) { return d }
        }
        return dayFormatter.date(from: String(s.prefix(10)))
    }

    static func parseDay(_ s: String?) -> Date? {
        guard let s = s, s.count >= 10 else { return nil }
        return dayFormatter.date(from: String(s.prefix(10)))
    }

    static func dayString(_ d: Date) -> String { dayFormatter.string(from: d) }

    static func number(_ d: Double, decimals: Int = 1) -> String {
        if d == d.rounded() { return String(Int(d)) }
        return String(format: "%.\(decimals)f", d)
    }

    static func relative(_ s: String?) -> String {
        guard let d = parseISO(s) else { return "" }
        let f = RelativeDateTimeFormatter()
        f.unitsStyle = .short
        return f.localizedString(for: d, relativeTo: Date())
    }

    static func shortDateTime(_ s: String?) -> String {
        guard let d = parseISO(s) else { return s ?? "" }
        return d.formatted(date: .abbreviated, time: .shortened)
    }

    static func friendlyDay(_ s: String?) -> String {
        guard let d = parseDay(s) else { return s ?? "" }
        return d.formatted(date: .abbreviated, time: .omitted)
    }

    /// "4h 12m" style countdown to a future date.
    static func countdown(to date: Date, from now: Date = Date()) -> String {
        let secs = max(0, Int(date.timeIntervalSince(now)))
        let h = secs / 3600
        let m = (secs % 3600) / 60
        if h > 0 { return "\(h)h \(m)m" }
        return "\(m)m"
    }

    static func cToF(_ c: Double) -> Double { c * 9 / 5 + 32 }
    static func fToC(_ f: Double) -> Double { (f - 32) * 5 / 9 }
}

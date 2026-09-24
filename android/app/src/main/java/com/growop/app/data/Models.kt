package com.growop.app.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull

// Serializable models mirroring docs/API.md. Enum-like fields are kept as plain Strings so a
// newer backend can never crash the app with an unknown value; most fields are nullable.

// MARK: Health

@Serializable
data class HealthResponse(
    val ok: Boolean = false,
    val version: String? = null,
    @SerialName("ha_connected") val haConnected: Boolean? = null,
    @SerialName("advisor_enabled") val advisorEnabled: Boolean? = null,
)

@Serializable
data class ApiErrorBody(val detail: String? = null)

// MARK: Status

@Serializable
data class SensorReading(
    @SerialName("temp_c") val tempC: Double? = null,
    @SerialName("temp_f") val tempF: Double? = null,
    val humidity: Double? = null,
    @SerialName("vpd_kpa") val vpdKpa: Double? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    val stale: Boolean? = null,
)

@Serializable
data class GrowProfile(
    val strain: String? = null,
    val breeder: String? = null,
    @SerialName("seed_type") val seedType: String? = null,
    val medium: String? = null,
    @SerialName("pot_size_l") val potSizeL: Double? = null,
    @SerialName("plant_count") val plantCount: Int? = null,
    @SerialName("start_date") val startDate: String? = null,
    val stage: String? = null,
    @SerialName("stage_started") val stageStarted: String? = null,
    @SerialName("flower_start_date") val flowerStartDate: String? = null,
    @SerialName("expected_flower_days") val expectedFlowerDays: Int? = null,
    @SerialName("exhaust_ducted") val exhaustDucted: Boolean? = null,
    val notes: String? = null,
    // Present only inside GET /api/status "grow"
    @SerialName("day_in_stage") val dayInStage: Int? = null,
    @SerialName("day_total") val dayTotal: Int? = null,
    @SerialName("expected_harvest_date") val expectedHarvestDate: String? = null,
) {
    companion object {
        val stages = listOf("seedling", "veg", "flower", "flush", "drying", "curing", "done")
        val mediums = listOf("soil", "coco", "hydro", "other")
    }
}

@Serializable
data class Targets(
    @SerialName("temp_min_c") val tempMinC: Double? = null,
    @SerialName("temp_max_c") val tempMaxC: Double? = null,
    @SerialName("temp_min_f") val tempMinF: Double? = null,
    @SerialName("temp_max_f") val tempMaxF: Double? = null,
    @SerialName("humidity_min") val humidityMin: Double? = null,
    @SerialName("humidity_max") val humidityMax: Double? = null,
    @SerialName("vpd_min") val vpdMin: Double? = null,
    @SerialName("vpd_max") val vpdMax: Double? = null,
    @SerialName("light_on_time") val lightOnTime: String? = null,
    @SerialName("light_hours") val lightHours: Double? = null,
    val source: String? = null,
    val note: String? = null,
    /** "day" or "night": which band the numbers are (status only). */
    val band: String? = null,
) {
    val isNight: Boolean get() = band == "night"
}

@Serializable
data class LightStatus(
    @SerialName("is_on") val isOn: Boolean? = null,
    @SerialName("next_change_at") val nextChangeAt: String? = null,
    val schedule: String? = null,
)

@Serializable
data class DeviceStatus(
    val role: String,
    val label: String? = null,
    val kind: String? = null,
    @SerialName("entity_id") val entityId: String? = null,
    val state: String? = null,
    val mode: String? = null,
    @SerialName("override_until") val overrideUntil: String? = null,
    val reason: String? = null,
    val available: Boolean? = null,
    @SerialName("power_w") val powerW: Double? = null,
) {
    val displayLabel: String get() = label ?: role.replace('_', ' ').replaceFirstChar { it.uppercase() }
    val isSwitch: Boolean get() = (kind ?: "switch") == "switch"
    val isOn: Boolean get() = state == "on"
    /** Switched on or off by hand (not following the automation). */
    val isSetByHand: Boolean get() = mode == "on" || mode == "off"
}

enum class AssessmentLevel { GOOD, WARN, ALERT, STANDBY;
    companion object {
        fun from(s: String?): AssessmentLevel = when ((s ?: "").lowercase()) {
            "good", "ok" -> GOOD
            "alert" -> ALERT
            "standby" -> STANDBY
            else -> WARN
        }
    }
}

@Serializable
data class Assessment(
    val level: String? = null,
    val headline: String? = null,
    val details: List<String>? = null,
) {
    val levelValue: AssessmentLevel get() = AssessmentLevel.from(level)
}

@Serializable
data class AlertItem(
    val id: Int = 0,
    val level: String? = null,
    val kind: String? = null,
    val message: String? = null,
    val at: String? = null,
)

@Serializable
data class StatusResponse(
    val time: String? = null,
    @SerialName("ha_connected") val haConnected: Boolean? = null,
    val sensor: SensorReading? = null,
    val grow: GrowProfile? = null,
    val targets: Targets? = null,
    val light: LightStatus? = null,
    val devices: List<DeviceStatus>? = null,
    val assessment: Assessment? = null,
    @SerialName("open_tasks") val openTasks: Int? = null,
    @SerialName("open_photo_requests") val openPhotoRequests: Int? = null,
    @SerialName("unread_brief") val unreadBrief: Boolean? = null,
    val alerts: List<AlertItem>? = null,
    @SerialName("control_paused_until") val controlPausedUntil: String? = null,
    val standby: Boolean? = null,
    val plants: List<Plant>? = null,
    val camera: CameraInfo? = null,
    @SerialName("humidifier_tank") val humidifierTank: HumidifierTank? = null,
)

/** How much water the humidifier has left, estimated from misting time since the last refill. */
@Serializable
data class HumidifierTank(
    @SerialName("hours_left") val hoursLeft: Double? = null,
    @SerialName("percent_left") val percentLeft: Int? = null,
    val dry: Boolean? = null,
    @SerialName("tank_hours") val tankHours: Double? = null,
)

// MARK: Tent camera (v0.3.0)

@Serializable
data class CameraInfo(
    @SerialName("entity_id") val entityId: String? = null,
    val name: String? = null,
    val available: Boolean? = null,
    @SerialName("snapshot_url") val snapshotUrl: String? = null,
    @SerialName("stream_url") val streamUrl: String? = null,
    @SerialName("last_frame_at") val lastFrameAt: String? = null,
    @SerialName("frame_count") val frameCount: Int? = null,
    val error: String? = null,
) {
    val displayName: String get() = if (!name.isNullOrEmpty()) name else (entityId ?: "Tent camera")
}

@Serializable
data class CameraCandidate(
    @SerialName("entity_id") val entityId: String,
    val name: String? = null,
    val state: String? = null,
    val brand: String? = null,
    val model: String? = null,
) {
    val displayName: String get() = if (!name.isNullOrEmpty()) name else entityId
}

@Serializable
data class CameraResponse(val camera: CameraInfo? = null, val candidates: List<CameraCandidate>? = null)

@Serializable
data class CameraFrame(
    val id: Int,
    val t: String? = null,
    @SerialName("lights_on") val lightsOn: Boolean? = null,
    val url: String? = null,
)

@Serializable
data class CameraFramesResponse(val frames: List<CameraFrame>? = null)

// MARK: Devices

@Serializable
data class DeviceOverrideRequest(val mode: String, val minutes: Int? = null)

// MARK: Plants

@Serializable
data class Plant(
    val id: Int,
    val name: String? = null,
    val owner: String? = null,
    val strain: String? = null,
    val breeder: String? = null,
    @SerialName("seed_type") val seedType: String? = null,
    val medium: String? = null,
    @SerialName("pot_size_l") val potSizeL: Double? = null,
    @SerialName("start_date") val startDate: String? = null,
    val notes: String? = null,
    @SerialName("notify_service") val notifyService: String? = null,
    @SerialName("day_total") val dayTotal: Int? = null,
    @SerialName("created_at") val createdAt: String? = null,
) {
    val displayName: String
        get() {
            if (!name.isNullOrBlank()) return name
            if (!owner.isNullOrBlank()) return "$owner's plant"
            return "Plant $id"
        }

    /** Short label for the segmented switcher: "Levi's plant" -> "Levi's". */
    val shortName: String
        get() {
            val n = displayName
            for (suffix in listOf(" plant", " Plant")) {
                if (n.endsWith(suffix)) {
                    val t = n.dropLast(suffix.length).trim()
                    if (t.isNotEmpty()) return t
                }
            }
            if (!owner.isNullOrBlank() && n.length > 12) return "$owner's"
            return n
        }
}

@Serializable
data class PlantsResponse(val plants: List<Plant>? = null)

@Serializable
data class OKResponse(val ok: Boolean? = null)

@Serializable
data class StageChangeRequest(val stage: String)

// MARK: History

@Serializable
data class HistoryPoint(
    val t: String? = null,
    @SerialName("temp_c") val tempC: Double? = null,
    @SerialName("temp_f") val tempF: Double? = null,
    val humidity: Double? = null,
    @SerialName("vpd_kpa") val vpdKpa: Double? = null,
    @SerialName("light_on") val lightOn: Boolean? = null,
)

@Serializable
data class HistoryResponse(val points: List<HistoryPoint>? = null)

// MARK: Log

@Serializable
data class LogRequest(
    val kind: String,
    val value: Double? = null,
    val unit: String? = null,
    val context: String? = null,
    val note: String? = null,
    @SerialName("plant_id") val plantId: Int? = null,
    /** true: ask the advisor now (paid, 10–40 s). false: saved instantly; the next brief reads it. */
    val advise: Boolean = false,
)

@Serializable
data class LogEntry(
    val id: Int,
    @SerialName("created_at") val createdAt: String? = null,
    val kind: String? = null,
    val value: Double? = null,
    val unit: String? = null,
    val context: String? = null,
    val note: String? = null,
    @SerialName("advice_summary") val adviceSummary: String? = null,
    @SerialName("advice_steps") val adviceSteps: List<String>? = null,
    @SerialName("plant_id") val plantId: Int? = null,
)

@Serializable
data class Advice(
    val summary: String? = null,
    val steps: List<String>? = null,
    val urgency: String? = null,
    @SerialName("photo_requests") val photoRequests: List<PhotoRequest>? = null,
    val tasks: List<TaskItem>? = null,
)

@Serializable
data class LogResponse(val entry: LogEntry? = null, val advice: Advice? = null)

@Serializable
data class LogListResponse(val entries: List<LogEntry>? = null)

// MARK: Photos

@Serializable
data class PhotoRequest(
    val id: Int,
    @SerialName("created_at") val createdAt: String? = null,
    val title: String? = null,
    val instructions: String? = null,
    val reason: String? = null,
    val status: String? = null,
    @SerialName("photo_id") val photoId: Int? = null,
    @SerialName("plant_id") val plantId: Int? = null,
)

@Serializable
data class PhotoRequestsResponse(val requests: List<PhotoRequest>? = null)

@Serializable
data class PhotoFinding(
    val title: String? = null,
    val severity: String? = null,
    val detail: String? = null,
)

@Serializable
data class PhotoAnalysis(
    val summary: String? = null,
    @SerialName("health_score") val healthScore: Double? = null,
    val findings: List<PhotoFinding>? = null,
    val actions: List<String>? = null,
    @SerialName("photo_requests") val photoRequests: List<PhotoRequest>? = null,
    val tasks: List<TaskItem>? = null,
) {
    /** health_score 0 means "no score" (advisor off), never "0/10". */
    val score: Double? get() = healthScore?.takeIf { it > 0 }
}

@Serializable
data class Photo(
    val id: Int,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("request_id") val requestId: Int? = null,
    val note: String? = null,
    val analysis: PhotoAnalysis? = null,
    @SerialName("image_url") val imageUrl: String? = null,
    @SerialName("plant_id") val plantId: Int? = null,
    val source: String? = null,
) {
    /** Pictures GrowOp took from the tent camera ("look now" or the daily check). */
    val isFromCamera: Boolean get() = source == "camera" || (note ?: "").startsWith("Tent camera")
    /** The note the grower wrote (camera shots don't have one). */
    val userNote: String? get() = if (isFromCamera) null else note
}

@Serializable
data class PhotosResponse(val photos: List<Photo>? = null)

// MARK: Tasks

@Serializable
data class TaskItem(
    val id: Int,
    val title: String? = null,
    val detail: String? = null,
    val due: String? = null,
    val priority: String? = null,
    val status: String? = null,
    @SerialName("created_by") val createdBy: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("plant_id") val plantId: Int? = null,
) {
    val isDone: Boolean get() = status == "done"
    val isHigh: Boolean get() = priority == "high"
}

@Serializable
data class TasksResponse(val tasks: List<TaskItem>? = null)

// MARK: Brief

@Serializable
data class TargetChange(
    val field: String? = null,
    val from: JsonElement? = null,
    val to: JsonElement? = null,
    val reason: String? = null,
)

@Serializable
data class BriefPerPlant(
    @SerialName("plant_id") val plantId: Int? = null,
    val name: String? = null,
    val headline: String? = null,
    val summary: String? = null,
)

@Serializable
data class Brief(
    val id: Int,
    @SerialName("created_at") val createdAt: String? = null,
    val headline: String? = null,
    val summary: String? = null,
    val concerns: List<String>? = null,
    val actions: List<String>? = null,
    @SerialName("target_changes") val targetChanges: List<TargetChange>? = null,
    @SerialName("photo_requests") val photoRequests: List<PhotoRequest>? = null,
    val tasks: List<TaskItem>? = null,
    val read: Boolean? = null,
    @SerialName("per_plant") val perPlant: List<BriefPerPlant>? = null,
    @SerialName("camera_frame_at") val cameraFrameAt: String? = null,
)

// MARK: Chat

@Serializable
data class ChatMessage(
    val id: Int,
    val role: String? = null,
    val content: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    val author: String? = null,
    @SerialName("plant_id") val plantId: Int? = null,
) {
    val isUser: Boolean get() = role == "user"
}

@Serializable
data class ChatListResponse(val messages: List<ChatMessage>? = null)

@Serializable
data class ChatReply(val id: Int? = null, val reply: String? = null)

// MARK: Events

@Serializable
data class EventItem(
    val id: Int,
    val at: String? = null,
    val level: String? = null,
    val kind: String? = null,
    val message: String? = null,
)

@Serializable
data class EventsResponse(val events: List<EventItem>? = null)

// MARK: Settings

@Serializable
data class Settings(
    val units: String? = null,
    @SerialName("brief_time") val briefTime: String? = null,
    val timezone: String? = null,
    @SerialName("auto_apply_advisor_targets") val autoApplyAdvisorTargets: Boolean? = null,
    @SerialName("notify_service") val notifyService: String? = null,
    @SerialName("notify_services_available") val notifyServicesAvailable: List<String>? = null,
    val model: String? = null,
    @SerialName("advisor_enabled") val advisorEnabled: Boolean? = null,
    @SerialName("safety_temp_max_c") val safetyTempMaxC: Double? = null,
    @SerialName("safety_temp_min_c") val safetyTempMinC: Double? = null,
    @SerialName("control_interval_s") val controlIntervalS: Double? = null,
    @SerialName("min_switch_interval_s") val minSwitchIntervalS: Double? = null,
    @SerialName("camera_entity") val cameraEntity: String? = null,
    @SerialName("camera_capture_minutes") val cameraCaptureMinutes: Int? = null,
    @SerialName("advisor_month_usd") val advisorMonthUsd: Double? = null,
    @SerialName("advisor_budget_usd") val advisorBudgetUsd: Double? = null,
    @SerialName("models_available") val modelsAvailable: List<String>? = null,
)

// MARK: Control

@Serializable
data class PauseRequest(val minutes: Int)

@Serializable
data class StandbyResponse(
    val standby: Boolean? = null,
    @SerialName("control_paused_until") val controlPausedUntil: String? = null,
)

// MARK: Grow plan

@Serializable
data class PlanPhase(
    val key: String,
    val title: String? = null,
    val subtitle: String? = null,
    @SerialName("start_day") val startDay: Int? = null,
    @SerialName("end_day") val endDay: Int? = null,
    @SerialName("start_date") val startDate: String? = null,
    @SerialName("end_date") val endDate: String? = null,
    val status: String? = null,
    val what: List<String>? = null,
    @SerialName("watch_for") val watchFor: List<String>? = null,
    val environment: String? = null,
) {
    val displayTitle: String get() = title ?: key.replace('_', ' ').replaceFirstChar { it.uppercase() }
    val isDone: Boolean get() = status == "done"
    val isCurrent: Boolean get() = status == "current"
    val isUpcoming: Boolean get() = !isDone && !isCurrent
}

@Serializable
data class GrowPlan(
    @SerialName("start_date") val startDate: String? = null,
    val today: String? = null,
    @SerialName("day_total") val dayTotal: Int? = null,
    @SerialName("current_phase") val currentPhase: String? = null,
    @SerialName("plant_id") val plantId: Int? = null,
    val phases: List<PlanPhase>? = null,
) {
    val orderedPhases: List<PlanPhase> get() = phases ?: emptyList()

    /** The phase flagged `current` (authoritative), falling back to `current_phase` by key. */
    val current: PlanPhase?
        get() = orderedPhases.firstOrNull { it.isCurrent } ?: orderedPhases.firstOrNull { it.key == currentPhase }

    /** The phase that follows the current one, or the first upcoming phase. */
    val next: PlanPhase?
        get() {
            val ph = orderedPhases
            val cur = current
            if (cur != null) {
                val i = ph.indexOfFirst { it.key == cur.key }
                return if (i >= 0 && i + 1 < ph.size) ph[i + 1] else null
            }
            return ph.firstOrNull { it.isUpcoming }
        }

    val allDone: Boolean get() = orderedPhases.isNotEmpty() && orderedPhases.all { it.isDone }
}

// MARK: JSON helpers

/** Human-readable form of a target_changes from/to value. */
fun JsonElement?.display(): String {
    if (this == null || this is JsonNull) return "—"
    val p = this as? JsonPrimitive ?: return this.toString()
    p.booleanOrNull?.let { return if (it) "yes" else "no" }
    if (!p.isString) p.doubleOrNull?.let { return Formatting.number(it) }
    return p.content
}

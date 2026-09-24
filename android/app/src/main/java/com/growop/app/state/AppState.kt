package com.growop.app.state

import android.content.Context
import com.growop.app.data.ApiClient
import com.growop.app.data.ApiError
import com.growop.app.data.Brief
import com.growop.app.data.ChatMessage
import com.growop.app.data.ConfigStore
import com.growop.app.data.GrowPlan
import com.growop.app.data.HealthResponse
import com.growop.app.data.HistoryPoint
import com.growop.app.data.LogEntry
import com.growop.app.data.LogRequest
import com.growop.app.data.LogResponse
import com.growop.app.data.Photo
import com.growop.app.data.PhotoRequest
import com.growop.app.data.Plant
import com.growop.app.data.ConnectionMode
import com.growop.app.data.ServerConfig
import com.growop.app.data.Settings
import com.growop.app.data.StatusResponse
import com.growop.app.data.TaskItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import android.graphics.BitmapFactory
import android.util.LruCache
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import com.growop.app.data.CameraFrame
import com.growop.app.data.CameraResponse
import kotlinx.coroutines.withContext
import java.time.Instant

enum class AppTab { HOME, ADVISOR, LOG, PHOTOS, TASKS }

/** Everything the screens read. Immutable snapshot; AppState publishes new copies. */
data class AppUi(
    val configLoaded: Boolean = false,
    val config: ServerConfig = ServerConfig(),
    val isConfigured: Boolean = false,

    val status: StatusResponse? = null,
    val statusError: String? = null,
    val lastStatusAt: Instant? = null,
    val isRefreshingStatus: Boolean = false,

    val settings: Settings? = null,
    val brief: Brief? = null,
    val history: List<HistoryPoint> = emptyList(),

    val plants: List<Plant> = emptyList(),
    /** null = not known yet; false = the backend has no /api/plants (older add-on). */
    val plantsSupported: Boolean? = null,
    val myPlantId: Int? = null,
    val selectedPlantId: Int? = null,
    val plantChoiceDismissed: Boolean = false,
    /** Plans cached per plant id (0 = no plant / older backend). */
    val plans: Map<Int, GrowPlan> = emptyMap(),

    val chatMessages: List<ChatMessage> = emptyList(),
    val logEntries: List<LogEntry> = emptyList(),
    val openPhotoRequests: List<PhotoRequest> = emptyList(),
    val photos: List<Photo> = emptyList(),
    val openTasks: List<TaskItem> = emptyList(),
    val doneTasks: List<TaskItem> = emptyList(),
    val tasksLoaded: Boolean = false,
    val requestsLoaded: Boolean = false,
    /** The task just ticked off, offered back for a few seconds in case the tap was a slip. */
    val undoTask: TaskItem? = null,

    val unitsPref: String? = null,
    /** From GET /api/health (shown read-only in Settings). */
    val serverVersion: String? = null,

    // Tent camera live view (shared by the Home card and the camera screen)
    val cameraImage: ImageBitmap? = null,
    val cameraImageAt: Instant? = null,
    val cameraError: String? = null,
) {
    val hasCamera: Boolean get() = status?.camera != null
    val units: String get() = settings?.units ?: unitsPref ?: "c"
    val usesFahrenheit: Boolean get() = units == "f"
    val tempUnitLabel: String get() = if (usesFahrenheit) "°F" else "°C"

    val selectedPlant: Plant? get() = plants.firstOrNull { it.id == selectedPlantId }
    val myPlant: Plant? get() = plants.firstOrNull { it.id == myPlantId }

    /** True when the backend knows about plants but this phone hasn't said which one is "mine". */
    val needsPlantChoice: Boolean get() = plantsSupported == true && (myPlantId == null || plants.none { it.id == myPlantId })
    val showPlantChoice: Boolean get() = needsPlantChoice && !plantChoiceDismissed

    /** Items with no plant_id belong to the whole tent and show under every plant. */
    fun belongsToSelected(plantId: Int?): Boolean = plantId == null || plantId == selectedPlantId || plants.isEmpty()
    val logEntriesForSelected: List<LogEntry> get() = logEntries.filter { belongsToSelected(it.plantId) }
    val openRequestsForSelected: List<PhotoRequest> get() = openPhotoRequests.filter { belongsToSelected(it.plantId) }
    val photosForSelected: List<Photo> get() = photos.filter { belongsToSelected(it.plantId) }
    val plantTasks: List<TaskItem> get() = openTasks.filter { if (plants.isEmpty()) true else it.plantId == selectedPlantId }
    val tentTasks: List<TaskItem> get() = if (plants.isEmpty()) emptyList() else openTasks.filter { it.plantId == null }
    val doneTasksForSelected: List<TaskItem> get() = doneTasks.filter { belongsToSelected(it.plantId) }
    val needsYouTaskCount: Int get() = if (tasksLoaded) plantTasks.size + tentTasks.size else (status?.openTasks ?: 0)
    val needsYouPhotoCount: Int get() = if (requestsLoaded) openRequestsForSelected.size else (status?.openPhotoRequests ?: 0)

    val planKey: Int get() = selectedPlantId ?: 0
    val plan: GrowPlan? get() = plans[planKey]
    val isStandby: Boolean get() = status?.standby == true
}

/**
 * Central store. Polls /api/status every 15 s while the app is in the foreground and caches
 * everything the screens need. Mirrors the iOS AppState.
 */
class AppState(context: Context) {
    private val store = ConfigStore(context.applicationContext)
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    private val _ui = MutableStateFlow(AppUi())
    val ui: StateFlow<AppUi> = _ui
    val value: AppUi get() = _ui.value

    /** Deep-link / notification tab requests (growop://advisor etc.). */
    val pendingTab = MutableStateFlow<AppTab?>(null)

    /**
     * Debug-only onboarding prefill (`adb shell am start ... --es growop.prefill.url http://10.0.2.2:8099
     * --es growop.prefill.apiKey test`), mirroring the iOS `-growop.prefill.*` launch arguments.
     * Keys: url, apiKey, haURL, haToken. Empty unless MainActivity sets it from a debuggable build.
     */
    val prefill = MutableStateFlow<Map<String, String>>(emptyMap())

    val client: ApiClient = ApiClient(ServerConfig()) { slug, path ->
        scope.launch {
            val cfg = value.config.copy(haAddonSlug = slug, haIngressPath = path)
            _ui.update { it.copy(config = cfg) }
            store.saveConfig(cfg)
        }
    }

    private var pollJob: Job? = null
    private var pollingWanted = false
    private val lastPlanAt = mutableMapOf<Int, Long>()
    private var lastHistoryAt = 0L

    companion object {
        const val POLL_INTERVAL_MS = 15_000L
    }

    init {
        scope.launch {
            val loaded = store.load()
            client.update(loaded.config)
            client.deviceId = loaded.deviceId
            _ui.update {
                it.copy(configLoaded = true, config = loaded.config, isConfigured = loaded.config.isConfigured,
                    myPlantId = loaded.myPlantId, unitsPref = loaded.units, plantChoiceDismissed = loaded.plantChoiceSkipped)
            }
            if (loaded.config.isConfigured && pollingWanted) startPolling()
        }
    }

    // MARK: Connection management

    /** Runs the full connection chain for a candidate config; if every step succeeds, saves it and becomes configured. */
    /** Configure from a scanned setup QR code (home Wi-Fi mode) and connect. */
    fun provisionDirect(url: String, key: String) {
        setupError.value = null
        scope.launch {
            runCatching { connect(ServerConfig(mode = ConnectionMode.DIRECT, baseUrl = url, apiKey = key)) }
                .onFailure { e ->
                    // keep what the QR said so "Connect" can be tapped again, and say why it didn't work
                    prefill.value = mapOf("url" to url, "apiKey" to key)
                    setupError.value = "Scanned the code, but couldn't reach the grow brain at $url. Make sure this phone is on the " +
                        "home Wi-Fi, then tap Connect. (${ApiError.wrap(e).message})"
                }
        }
    }

    /** Why the last QR setup failed, for the first-launch screen. */
    val setupError = MutableStateFlow<String?>(null)

    suspend fun connect(candidate: ServerConfig): HealthResponse {
        val result = client.verify(candidate)
        store.saveConfig(result.config)
        client.update(result.config)
        _ui.update {
            it.copy(config = result.config, isConfigured = true, status = result.status, statusError = null, lastStatusAt = Instant.now(),
                serverVersion = result.health.version)
        }
        result.status.plants?.let { list -> _ui.update { it.copy(plantsSupported = true) }; applyPlants(list) }
        startPolling()
        scope.launch { refreshSettings() }
        return result.health
    }

    fun disconnect() {
        stopPolling()
        scope.launch { store.clearConfig() }
        client.update(ServerConfig())
        _ui.update {
            AppUi(configLoaded = true, config = ServerConfig(), isConfigured = false, myPlantId = it.myPlantId, unitsPref = it.unitsPref)
        }
        lastPlanAt.clear()
        lastHistoryAt = 0L
    }

    // MARK: Polling

    fun startPolling() {
        pollingWanted = true
        if (!value.isConfigured) return
        pollJob?.cancel()
        pollJob = scope.launch {
            while (isActive) {
                refreshStatus()
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    fun stopPolling() {
        pollingWanted = false
        pollJob?.cancel()
        pollJob = null
    }

    suspend fun refreshStatus() {
        if (!value.isConfigured) return
        _ui.update { it.copy(isRefreshingStatus = true) }
        try {
            val st = client.status()
            val previous = value.status
            _ui.update { it.copy(status = st, statusError = null, lastStatusAt = Instant.now(),
                cameraImage = if (st.camera == null) null else it.cameraImage, cameraError = if (st.camera == null) null else it.cameraError) }
            st.plants?.let { list -> _ui.update { it.copy(plantsSupported = true) }; applyPlants(list) }
            // The plan only changes with the grow (stage / start date); reload when those change,
            // when we don't have one yet, or every 10 minutes as a safety net.
            val sel = value.selectedPlantId
            val prevStart = previous?.plants?.firstOrNull { it.id == sel }?.startDate ?: previous?.grow?.startDate
            val newStart = value.selectedPlant?.startDate ?: st.grow?.startDate
            val growChanged = previous?.grow?.stage != st.grow?.stage || prevStart != newStart
            val stale = lastPlanAt[value.planKey]?.let { System.currentTimeMillis() - it > 600_000 } ?: true
            if (value.plan == null || growChanged || stale) loadPlan()
            if (System.currentTimeMillis() - lastHistoryAt > 300_000) loadHistory()
            // keep the tab badges honest: if the server's counts moved, reload the lists behind them
            if (value.tasksLoaded && st.openTasks != previous?.openTasks) loadTasks()
            if (value.requestsLoaded && st.openPhotoRequests != previous?.openPhotoRequests) loadPhotoRequests()
        } catch (e: Throwable) {
            _ui.update { it.copy(statusError = ApiError.wrap(e).message) }
        } finally {
            _ui.update { it.copy(isRefreshingStatus = false) }
        }
    }

    // MARK: History (24 h sparklines)

    suspend fun loadHistory(force: Boolean = false) {
        if (!value.isConfigured) return
        if (!force && System.currentTimeMillis() - lastHistoryAt < 60_000) return
        runCatching { client.history(24) }.getOrNull()?.let { h ->
            _ui.update { it.copy(history = (h.points ?: emptyList()).sortedBy { p -> p.t ?: "" }) }
            lastHistoryAt = System.currentTimeMillis()
        }
    }

    // MARK: Plants

    fun dismissPlantChoice() {
        _ui.update { it.copy(plantChoiceDismissed = true) }
        scope.launch { store.savePlantChoiceSkipped(true) }
    }

    suspend fun loadPlants() {
        if (!value.isConfigured) return
        try {
            val r = client.plants()
            _ui.update { it.copy(plantsSupported = true) }
            applyPlants(r.plants ?: emptyList())
        } catch (e: ApiError.Http) {
            if (e.status == 404) _ui.update { it.copy(plantsSupported = false) }
        } catch (_: Throwable) {
        }
    }

    private fun applyPlants(list: List<Plant>) {
        _ui.update { s ->
            val sorted = list.sortedBy { it.id }
            var sel = s.selectedPlantId
            if (sel == null || sorted.none { it.id == sel }) {
                sel = (s.myPlantId?.let { id -> sorted.firstOrNull { it.id == id } } ?: sorted.firstOrNull())?.id
            }
            s.copy(plants = sorted, selectedPlantId = sel)
        }
    }

    fun selectPlant(id: Int?) {
        if (id == value.selectedPlantId) return
        _ui.update { it.copy(selectedPlantId = id) }
        if (value.plan == null) scope.launch { loadPlan() }
    }

    fun setMyPlant(id: Int?) {
        _ui.update { it.copy(myPlantId = id) }
        scope.launch { store.saveMyPlantId(id) }
        if (id != null) selectPlant(id)
    }

    suspend fun createPlant(fields: JsonObject): Plant {
        val p = client.createPlant(fields)
        _ui.update { it.copy(plantsSupported = true) }
        applyPlants(value.plants.filter { it.id != p.id } + p)
        return p
    }

    suspend fun updatePlant(id: Int, fields: JsonObject): Plant {
        val p = client.updatePlant(id, fields)
        applyPlants(value.plants.map { if (it.id == p.id) p else it })
        _ui.update { it.copy(plans = it.plans - p.id) }
        if (value.selectedPlantId == p.id) loadPlan()
        return p
    }

    suspend fun deletePlant(id: Int) {
        client.deletePlant(id)
        _ui.update { it.copy(plans = it.plans - id) }
        if (value.myPlantId == id) setMyPlant(null)
        applyPlants(value.plants.filter { it.id != id })
        if (value.selectedPlantId == id) _ui.update { it.copy(selectedPlantId = it.plants.firstOrNull()?.id) }
    }

    // MARK: Plan (per selected plant)

    suspend fun loadPlan() {
        if (!value.isConfigured) return
        val key = value.planKey
        runCatching { client.plan(value.selectedPlantId) }.getOrNull()?.let { p ->
            _ui.update { it.copy(plans = it.plans + (key to p)) }
            lastPlanAt[key] = System.currentTimeMillis()
        }
    }

    // MARK: Settings

    /** GET /api/health, just to show the server version. */
    suspend fun loadHealth() {
        if (!value.isConfigured) return
        runCatching { client.health() }.getOrNull()?.let { h -> _ui.update { it.copy(serverVersion = h.version ?: it.serverVersion) } }
    }

    suspend fun refreshSettings() {
        if (!value.isConfigured) return
        runCatching { client.settings() }.getOrNull()?.let { s -> applySettings(s) }
    }

    fun applySettings(s: Settings) {
        _ui.update { it.copy(settings = s, unitsPref = s.units ?: it.unitsPref) }
        s.units?.let { u -> scope.launch { store.saveUnits(u) } }
    }

    suspend fun saveSettings(fields: JsonObject) {
        applySettings(client.updateSettings(fields))
    }

    // MARK: Brief

    suspend fun loadBrief() {
        if (!value.isConfigured) return
        runCatching { client.brief() }.onSuccess { b -> _ui.update { it.copy(brief = b) } }
    }

    suspend fun runBrief() {
        val b = client.runBrief()
        _ui.update { it.copy(brief = b) }
        refreshStatus()
    }

    suspend fun markBriefRead() {
        val b = value.brief ?: return
        if (b.read == true) return
        runCatching { client.markBriefRead(b.id) }
        _ui.update { it.copy(brief = it.brief?.copy(read = true), status = it.status?.copy(unreadBrief = false)) }
    }

    // MARK: Chat

    suspend fun loadChat() {
        if (!value.isConfigured) return
        runCatching { client.chatMessages(50) }.getOrNull()?.let { r ->
            _ui.update { it.copy(chatMessages = (r.messages ?: emptyList()).sortedBy { m -> m.id }) }
        }
    }

    suspend fun sendChat(text: String, plantId: Int?) {
        val tempId = -(System.currentTimeMillis() % 1_000_000_000L).toInt() - 1
        val nowIso = Instant.now().toString()
        val author = value.myPlant?.owner ?: value.plants.firstOrNull { it.id == plantId }?.owner
        _ui.update { it.copy(chatMessages = it.chatMessages + ChatMessage(tempId, "user", text, nowIso, author, plantId)) }
        try {
            val body = buildJsonObject {
                put("message", text)
                plantId?.let { put("plant_id", it) } ?: put("plant_id", JsonNull)
                value.myPlant?.owner?.takeIf { it.isNotBlank() }?.let { put("author", it) }
            }
            val reply = client.sendChat(body)
            _ui.update { it.copy(chatMessages = it.chatMessages + ChatMessage(reply.id ?: (tempId - 1), "assistant", reply.reply ?: "", Instant.now().toString())) }
            loadChat()
        } catch (e: Throwable) {
            _ui.update { it.copy(chatMessages = it.chatMessages.filter { m -> m.id != tempId }) }
            throw ApiError.wrap(e)
        }
    }

    suspend fun clearChat() {
        client.clearChat()
        _ui.update { it.copy(chatMessages = emptyList()) }
    }

    // MARK: Log

    suspend fun loadLog() {
        if (!value.isConfigured) return
        runCatching { client.logEntries(50) }.getOrNull()?.let { r ->
            _ui.update { it.copy(logEntries = (r.entries ?: emptyList()).sortedByDescending { e -> e.id }) }
        }
    }

    suspend fun submitLog(req: LogRequest): LogResponse {
        val r = client.submitLog(if (req.plantId == null) req.copy(plantId = value.selectedPlantId) else req)
        loadLog()
        refreshStatus()
        return r
    }

    // MARK: Photos

    suspend fun loadPhotoRequests() {
        if (!value.isConfigured) return
        runCatching { client.photoRequests("open") }.getOrNull()?.let { r ->
            _ui.update { it.copy(openPhotoRequests = (r.requests ?: emptyList()).sortedByDescending { x -> x.id }, requestsLoaded = true) }
        }
    }

    suspend fun loadPhotos() {
        if (!value.isConfigured) return
        runCatching { client.photos(30) }.getOrNull()?.let { r ->
            _ui.update { it.copy(photos = (r.photos ?: emptyList()).sortedByDescending { p -> p.id }) }
        }
    }

    suspend fun skipPhotoRequest(id: Int) {
        client.skipPhotoRequest(id)
        _ui.update { it.copy(openPhotoRequests = it.openPhotoRequests.filter { r -> r.id != id }) }
        refreshStatus()
    }

    suspend fun uploadPhoto(jpeg: ByteArray, requestId: Int?, note: String?, plantId: Int?): Photo {
        val photo = client.uploadPhoto(jpeg, requestId, note, plantId ?: value.selectedPlantId)
        if (requestId != null) _ui.update { it.copy(openPhotoRequests = it.openPhotoRequests.filter { r -> r.id != requestId }) }
        loadPhotos()
        loadPhotoRequests()
        refreshStatus()
        return photo
    }

    // MARK: Tasks

    suspend fun loadTasks(includeDone: Boolean = false) {
        if (!value.isConfigured) return
        runCatching { client.tasks("open") }.getOrNull()?.let { r ->
            _ui.update { it.copy(openTasks = sortTasks(r.tasks ?: emptyList()), tasksLoaded = true) }
        }
        if (includeDone) runCatching { client.tasks("done") }.getOrNull()?.let { r ->
            _ui.update { it.copy(doneTasks = (r.tasks ?: emptyList()).sortedByDescending { t -> t.id }) }
        }
    }

    private fun sortTasks(tasks: List<TaskItem>): List<TaskItem> =
        tasks.sortedWith(compareBy<TaskItem> { !it.isHigh }.thenBy { it.due ?: "9999" }.thenBy { it.id })

    suspend fun completeTask(task: TaskItem) {
        val updated = client.completeTask(task.id)
        _ui.update {
            val open = it.openTasks.filter { t -> t.id != task.id }
            it.copy(openTasks = open, doneTasks = listOf(updated) + it.doneTasks, status = it.status?.copy(openTasks = open.size))
        }
    }

    private var undoJob: Job? = null

    suspend fun completeWithUndo(task: TaskItem) {
        completeTask(task)
        _ui.update { it.copy(undoTask = task) }
        undoJob?.cancel()
        undoJob = scope.launch {
            delay(6_000)
            _ui.update { if (it.undoTask?.id == task.id) it.copy(undoTask = null) else it }
        }
    }

    suspend fun undoLastComplete() {
        val t = value.undoTask ?: return
        _ui.update { it.copy(undoTask = null) }
        undoJob?.cancel()
        runCatching { reopenTask(t) }
        refreshStatus()
    }

    suspend fun markHumidifierRefilled() {
        client.humidifierRefilled()
        refreshStatus()
    }

    suspend fun reopenTask(task: TaskItem) {
        val updated = client.reopenTask(task.id)
        _ui.update {
            val open = sortTasks(it.openTasks + updated)
            it.copy(openTasks = open, doneTasks = it.doneTasks.filter { t -> t.id != task.id }, status = it.status?.copy(openTasks = open.size))
        }
    }

    /** plantId null = a task for the whole tent (sent as an explicit JSON null). */
    suspend fun addTask(title: String, detail: String?, due: String?, plantId: Int?) {
        val body = buildJsonObject {
            put("title", title)
            if (detail != null) put("detail", detail)
            if (due != null) put("due", due)
            if (plantId != null) put("plant_id", plantId) else put("plant_id", JsonNull)
        }
        val t = client.createTask(body)
        _ui.update {
            val open = sortTasks(it.openTasks + t)
            it.copy(openTasks = open, status = it.status?.copy(openTasks = open.size))
        }
    }

    // MARK: Tent camera

    private val frameCache = LruCache<Int, ImageBitmap>(48)
    private val frameInFlight = mutableMapOf<Int, kotlinx.coroutines.Deferred<ImageBitmap?>>()

    private suspend fun decodeImage(bytes: ByteArray): ImageBitmap? = withContext(Dispatchers.Default) {
        runCatching { BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.asImageBitmap() }.getOrNull()
    }

    /** One live snapshot (GET /api/camera/snapshot?t=...). Errors become `cameraError` (503 detail passes through). */
    suspend fun refreshCameraSnapshot() {
        if (!value.isConfigured || !value.hasCamera) return
        try {
            val img = decodeImage(client.cameraSnapshot())
            if (img != null) _ui.update { it.copy(cameraImage = img, cameraImageAt = Instant.now(), cameraError = null) }
            else _ui.update { it.copy(cameraError = "The camera sent something that isn't an image.") }
        } catch (e: Throwable) {
            val msg = (e as? ApiError.Http)?.detail?.takeIf { it.isNotBlank() } ?: ApiError.wrap(e).message
            _ui.update { it.copy(cameraError = msg) }
        }
    }

    suspend fun cameraFrames(days: Int): List<CameraFrame> {
        if (!value.isConfigured) return emptyList()
        val r = runCatching { client.cameraFrames(days) }.getOrNull() ?: return emptyList()
        return (r.frames ?: emptyList()).sortedBy { it.id }
    }

    fun cachedFrame(id: Int): ImageBitmap? = frameCache.get(id)

    /** Decoded timelapse frame, cached; concurrent callers share one download. */
    suspend fun frame(id: Int): ImageBitmap? {
        frameCache.get(id)?.let { return it }
        val d = frameInFlight[id] ?: kotlinx.coroutines.CompletableDeferred<ImageBitmap?>().also { def ->
            frameInFlight[id] = def
            scope.launch {
                val img = runCatching { client.cameraFrameData(id) }.getOrNull()?.let { decodeImage(it) }
                if (img != null) frameCache.put(id, img)
                frameInFlight.remove(id)
                def.complete(img)
            }
        }
        return d.await()
    }

    /** "Look now": fresh snapshot analysed by the advisor for the selected plant. */
    suspend fun analyseCamera(note: String? = null): Photo {
        val photo = client.cameraAnalyse(value.selectedPlantId, note)
        loadPhotos()
        refreshStatus()
        return photo
    }

    suspend fun setCamera(entityId: String?): CameraResponse {
        val r = client.setCamera(entityId)
        _ui.update { it.copy(status = it.status?.copy(camera = r.camera), cameraImage = null, cameraImageAt = null, cameraError = null) }
        return r
    }

    // MARK: Devices / control

    /** minutes null = until changed back to auto (ignored for "auto"). */
    suspend fun setOverride(role: String, mode: String, minutes: Int?) {
        val mins = if (mode == "auto") null else minutes
        val updated = client.overrideDevice(role, mode, mins)
        _ui.update { s ->
            val devs = s.status?.devices?.map { if (it.role == role) updated else it }
            s.copy(status = s.status?.copy(devices = devs))
        }
    }

    suspend fun setStandby() {
        val r = client.setStandby()
        _ui.update { it.copy(status = it.status?.copy(standby = r.standby ?: true)) }
        refreshStatus()
    }

    suspend fun startTent() {
        val r = client.startTent()
        _ui.update { it.copy(status = it.status?.copy(standby = r.standby ?: false, controlPausedUntil = null)) }
        refreshStatus()
    }

    suspend fun resumeControl() {
        client.resumeControl()
        refreshStatus()
    }

    /** Fire-and-forget helper for UI callbacks. */
    fun launch(block: suspend () -> Unit): Job = scope.launch { block() }
}

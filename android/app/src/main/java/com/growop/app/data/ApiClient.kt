package com.growop.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.KSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Talks to the grow brain either directly (same Wi‑Fi) or through Home Assistant ingress.
 * Plain OkHttp: the ingress mode needs a per-request base URL, cookie and bearer header, which is
 * awkward to express with Retrofit.
 */
class ApiClient(initial: ServerConfig, private val onDiscovery: (slug: String, path: String) -> Unit = { _, _ -> }) {

    companion object {
        const val SHORT_TIMEOUT_S = 20L
        const val LONG_TIMEOUT_S = 90L
        val json: Json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
            isLenient = true
        }
        private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()
    }

    @Volatile
    var config: ServerConfig = initial
        private set

    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(SHORT_TIMEOUT_S, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .callTimeout(0, TimeUnit.SECONDS)
        .cookieJar(CookieJar.NO_COOKIES) // we manage the ingress cookie ourselves
        .retryOnConnectionFailure(true)
        .build()

    @Volatile
    private var ingress = HAIngress(http, json, initial.haAddonSlug, initial.haIngressPath)

    fun update(config: ServerConfig) {
        this.config = config
        ingress = HAIngress(http, json, config.haAddonSlug, config.haIngressPath)
    }

    // MARK: Request plumbing

    private class Spec(
        val method: String,
        val path: String,
        val query: List<Pair<String, String>> = emptyList(),
        val body: RequestBody? = null,
        val timeoutS: Long = SHORT_TIMEOUT_S,
        val auth: Boolean = true,
    )

    private fun build(spec: Spec, base: String, headers: Map<String, String>): Request {
        if (base.isEmpty()) throw ApiError.NotConfigured
        val parsed: HttpUrl = (base + spec.path).toHttpUrlOrNull() ?: throw ApiError.InvalidUrl(base)
        val url = parsed.newBuilder().apply { spec.query.forEach { (k, v) -> addQueryParameter(k, v) } }.build()
        val b = Request.Builder().url(url).header("Accept", "application/json")
        headers.forEach { (k, v) -> b.header(k, v) }
        when (spec.method) {
            "GET" -> b.get()
            "DELETE" -> if (spec.body != null) b.delete(spec.body) else b.delete()
            else -> b.method(spec.method, spec.body ?: ByteArray(0).toRequestBody(JSON_MEDIA))
        }
        return b.build()
    }

    /** Runs a request. Throws only on transport failures; returns the HTTP status and body. */
    private suspend fun execute(req: Request, timeoutS: Long): Pair<Int, ByteArray> = withContext(Dispatchers.IO) {
        val client = http.newBuilder().readTimeout(timeoutS, TimeUnit.SECONDS).callTimeout(timeoutS + 30, TimeUnit.SECONDS).build()
        try {
            client.newCall(req).execute().use { r -> r.code to (r.body?.bytes() ?: ByteArray(0)) }
        } catch (e: IOException) {
            throw ApiError.Network(e)
        } catch (e: ApiError) {
            throw e
        } catch (e: Exception) {
            throw ApiError.Other(e)
        }
    }

    private fun check(status: Int, data: ByteArray): ByteArray {
        if (status in 200..299) return data
        if (status == 401 || status == 403) throw ApiError.Unauthorized
        val text = runCatching { String(data, Charsets.UTF_8) }.getOrDefault("")
        val detail = runCatching { json.decodeFromString(ApiErrorBody.serializer(), text).detail }.getOrNull()
            ?: text.takeIf { it.length < 300 && !it.contains("<html", ignoreCase = true) && it.isNotBlank() }
        throw ApiError.Http(status, detail)
    }

    /** The one place that decides how a grow-brain request reaches the server. */
    private suspend fun perform(spec: Spec, cfgOverride: ServerConfig? = null, ingressOverride: HAIngress? = null): ByteArray {
        val cfg = cfgOverride ?: config
        return when (cfg.mode) {
            ConnectionMode.DIRECT -> {
                val headers = if (spec.auth) mapOf("X-API-Key" to cfg.trimmedApiKey) else emptyMap()
                val (status, data) = execute(build(spec, cfg.normalizedBaseUrl, headers), spec.timeoutS)
                check(status, data)
            }
            ConnectionMode.HOME_ASSISTANT -> performViaHA(spec, cfg, ingressOverride ?: ingress)
        }
    }

    /** Through HA ingress, with session renewal on 401 and path rediscovery on 404 (each retried once). */
    private suspend fun performViaHA(spec: Spec, cfg: ServerConfig, ing: HAIngress): ByteArray {
        suspend fun run(r: HAIngress.Resolved): Pair<Int, ByteArray> {
            val headers = mutableMapOf(
                "Authorization" to "Bearer ${cfg.trimmedHaToken}",
                "Cookie" to r.cookie,
            )
            if (spec.auth) headers["X-API-Key"] = cfg.trimmedApiKey
            return execute(build(spec, r.base, headers), spec.timeoutS)
        }

        var resolved = ing.resolve(cfg)
        var (status, data) = run(resolved)
        if (status == 401) {
            resolved = ing.resolve(cfg, forceNewSession = true)
            val again = run(resolved); status = again.first; data = again.second
        } else if (status == 404) {
            val previous = resolved.base
            resolved = ing.resolve(cfg, forceDiscovery = true)
            if (resolved.base != previous) {
                val again = run(resolved); status = again.first; data = again.second
            }
        }
        if (ing === ingress) {
            val s = ing.slug; val p = ing.ingressPath
            if (s != null && p != null && (config.haAddonSlug != s || config.haIngressPath != p)) {
                config = config.copy(haAddonSlug = s, haIngressPath = p)
                onDiscovery(s, p)
            }
        }
        return check(status, data)
    }

    private fun <T> decode(serializer: KSerializer<T>, data: ByteArray): T = try {
        json.decodeFromString(serializer, String(data, Charsets.UTF_8))
    } catch (e: Exception) {
        throw ApiError.Decoding(e)
    }

    private fun <B> encode(serializer: KSerializer<B>, body: B): RequestBody =
        json.encodeToString(serializer, body).toRequestBody(JSON_MEDIA)

    private fun encodeJson(obj: JsonElement): RequestBody = json.encodeToString(JsonElement.serializer(), obj).toRequestBody(JSON_MEDIA)

    private suspend fun <T> get(path: String, serializer: KSerializer<T>, query: List<Pair<String, String>> = emptyList(), timeoutS: Long = SHORT_TIMEOUT_S): T =
        decode(serializer, perform(Spec("GET", path, query, timeoutS = timeoutS)))

    private suspend fun <T, B> send(method: String, path: String, bodySer: KSerializer<B>, body: B, resSer: KSerializer<T>, timeoutS: Long = SHORT_TIMEOUT_S): T =
        decode(resSer, perform(Spec(method, path, body = encode(bodySer, body), timeoutS = timeoutS)))

    private suspend fun <T> sendJson(method: String, path: String, body: JsonElement, resSer: KSerializer<T>, timeoutS: Long = SHORT_TIMEOUT_S): T =
        decode(resSer, perform(Spec(method, path, body = encodeJson(body), timeoutS = timeoutS)))

    private suspend fun <T> send(method: String, path: String, resSer: KSerializer<T>, timeoutS: Long = SHORT_TIMEOUT_S): T =
        decode(resSer, perform(Spec(method, path, timeoutS = timeoutS)))

    private suspend fun sendIgnoringBody(method: String, path: String, body: RequestBody? = null, timeoutS: Long = SHORT_TIMEOUT_S) {
        perform(Spec(method, path, body = body, timeoutS = timeoutS))
    }

    // MARK: Connection test

    class VerifyResult(val config: ServerConfig, val health: HealthResponse, val status: StatusResponse)

    /** Runs the full connection chain for a candidate config without saving anything, reporting which step failed. */
    suspend fun verify(candidate: ServerConfig): VerifyResult {
        var cfg = candidate
        if (!cfg.isConfigured) throw ApiError.NotConfigured
        var tempIngress: HAIngress? = null
        if (cfg.mode == ConnectionMode.HOME_ASSISTANT) {
            val tok = cfg.trimmedHaToken
            if (tok.length < 100 || tok.count { it == '.' } != 2) {
                throw ApiError.Step("Checking the Home Assistant token", ApiError.HaTokenMalformed(tok.length))
            }
            val ing = HAIngress(http, json)
            tempIngress = ing
            // Steps 1–3 over the HA WebSocket: sign in, find the add-on, read its ingress path, open a session.
            try {
                ing.resolve(cfg, forceNewSession = true, forceDiscovery = true)
            } catch (e: Throwable) {
                val w = ApiError.wrap(e)
                throw if (w is ApiError.Step) w else ApiError.Step("Connecting to Home Assistant", w)
            }
            cfg = cfg.copy(haAddonSlug = ing.slug, haIngressPath = ing.ingressPath)
        }
        val health = try {
            decode(HealthResponse.serializer(), perform(Spec("GET", "/api/health", timeoutS = 15, auth = false), cfg, tempIngress))
        } catch (e: Throwable) {
            throw ApiError.Step(if (cfg.mode == ConnectionMode.HOME_ASSISTANT) "Reaching the grow brain through Home Assistant" else "Reaching the grow brain", ApiError.wrap(e))
        }
        val status = try {
            decode(StatusResponse.serializer(), perform(Spec("GET", "/api/status"), cfg, tempIngress))
        } catch (e: Throwable) {
            throw ApiError.Step("Checking the Grow Brain API key", ApiError.wrap(e))
        }
        return VerifyResult(cfg, health, status)
    }

    // MARK: Health / status

    suspend fun health(): HealthResponse = decode(HealthResponse.serializer(), perform(Spec("GET", "/api/health", timeoutS = 15, auth = false)))
    suspend fun status(): StatusResponse = get("/api/status", StatusResponse.serializer())

    // MARK: Devices

    suspend fun overrideDevice(role: String, mode: String, minutes: Int?): DeviceStatus =
        send("POST", "/api/devices/$role/override", DeviceOverrideRequest.serializer(), DeviceOverrideRequest(mode, minutes), DeviceStatus.serializer())

    // MARK: Grow

    suspend fun grow(): GrowProfile = get("/api/grow", GrowProfile.serializer())
    suspend fun updateGrow(fields: JsonObject): GrowProfile = sendJson("PUT", "/api/grow", fields, GrowProfile.serializer())
    suspend fun setStage(stage: String): GrowProfile =
        send("POST", "/api/grow/stage", StageChangeRequest.serializer(), StageChangeRequest(stage), GrowProfile.serializer())

    // MARK: Targets

    suspend fun targets(): Targets = get("/api/targets", Targets.serializer())
    suspend fun updateTargets(fields: JsonObject): Targets = sendJson("PUT", "/api/targets", fields, Targets.serializer())
    suspend fun resetTargets(): Targets = send("DELETE", "/api/targets", Targets.serializer())

    // MARK: History

    suspend fun history(hours: Int = 24): HistoryResponse = get("/api/history", HistoryResponse.serializer(), listOf("hours" to hours.toString()))

    // MARK: Log

    suspend fun submitLog(entry: LogRequest): LogResponse =
        send("POST", "/api/log", LogRequest.serializer(), entry, LogResponse.serializer(), LONG_TIMEOUT_S)
    suspend fun logEntries(limit: Int = 50): LogListResponse = get("/api/log", LogListResponse.serializer(), listOf("limit" to limit.toString()))

    // MARK: Photos

    suspend fun photoRequests(status: String = "open"): PhotoRequestsResponse =
        get("/api/photo-requests", PhotoRequestsResponse.serializer(), listOf("status" to status))
    suspend fun skipPhotoRequest(id: Int) = sendIgnoringBody("POST", "/api/photo-requests/$id/skip")

    suspend fun uploadPhoto(jpeg: ByteArray, requestId: Int?, note: String?, plantId: Int?): Photo {
        val b = MultipartBody.Builder().setType(MultipartBody.FORM)
        if (requestId != null) b.addFormDataPart("request_id", requestId.toString())
        if (plantId != null) b.addFormDataPart("plant_id", plantId.toString())
        if (!note.isNullOrEmpty()) b.addFormDataPart("note", note)
        b.addFormDataPart("image", "photo.jpg", jpeg.toRequestBody("image/jpeg".toMediaType()))
        return decode(Photo.serializer(), perform(Spec("POST", "/api/photos", body = b.build(), timeoutS = LONG_TIMEOUT_S)))
    }

    suspend fun photos(limit: Int = 30): PhotosResponse = get("/api/photos", PhotosResponse.serializer(), listOf("limit" to limit.toString()))
    suspend fun photoImageData(id: Int): ByteArray = perform(Spec("GET", "/api/photos/$id/image", timeoutS = 30))
    suspend fun photoThumbData(id: Int): ByteArray = perform(Spec("GET", "/api/photos/$id/thumb", timeoutS = 20))

    // MARK: Tasks

    suspend fun tasks(status: String = "open"): TasksResponse = get("/api/tasks", TasksResponse.serializer(), listOf("status" to status))
    suspend fun createTask(body: JsonObject): TaskItem = sendJson("POST", "/api/tasks", body, TaskItem.serializer())
    suspend fun completeTask(id: Int): TaskItem = send("POST", "/api/tasks/$id/complete", TaskItem.serializer())
    suspend fun reopenTask(id: Int): TaskItem = send("POST", "/api/tasks/$id/reopen", TaskItem.serializer())

    // MARK: Brief

    /** GET /api/brief -> Brief or JSON null. */
    suspend fun brief(): Brief? {
        val data = perform(Spec("GET", "/api/brief"))
        val trimmed = String(data, Charsets.UTF_8).trim()
        if (trimmed.isEmpty() || trimmed == "null") return null
        return decode(Brief.serializer(), data)
    }
    suspend fun runBrief(): Brief = send("POST", "/api/brief/run", Brief.serializer(), LONG_TIMEOUT_S)
    suspend fun markBriefRead(id: Int) = sendIgnoringBody("POST", "/api/brief/$id/read")

    // MARK: Chat

    suspend fun sendChat(body: JsonObject): ChatReply = sendJson("POST", "/api/chat", body, ChatReply.serializer(), LONG_TIMEOUT_S)
    suspend fun chatMessages(limit: Int = 50): ChatListResponse = get("/api/chat", ChatListResponse.serializer(), listOf("limit" to limit.toString()))
    suspend fun clearChat() = sendIgnoringBody("DELETE", "/api/chat")

    // MARK: Events

    suspend fun events(limit: Int = 50): EventsResponse = get("/api/events", EventsResponse.serializer(), listOf("limit" to limit.toString()))

    // MARK: Settings

    suspend fun settings(): Settings = get("/api/settings", Settings.serializer())
    suspend fun updateSettings(fields: JsonObject): Settings = sendJson("PUT", "/api/settings", fields, Settings.serializer())

    // MARK: Plants

    suspend fun plants(): PlantsResponse = get("/api/plants", PlantsResponse.serializer())
    suspend fun createPlant(fields: JsonObject): Plant = sendJson("POST", "/api/plants", fields, Plant.serializer())
    suspend fun updatePlant(id: Int, fields: JsonObject): Plant = sendJson("PUT", "/api/plants/$id", fields, Plant.serializer())
    suspend fun deletePlant(id: Int) = sendIgnoringBody("DELETE", "/api/plants/$id")

    // MARK: Plan

    suspend fun plan(plantId: Int?): GrowPlan =
        get("/api/plan", GrowPlan.serializer(), if (plantId != null) listOf("plant_id" to plantId.toString()) else emptyList())

    // MARK: Tent camera

    suspend fun camera(): CameraResponse = get("/api/camera", CameraResponse.serializer())
    suspend fun setCamera(entityId: String?): CameraResponse =
        sendJson("PUT", "/api/camera", buildJsonObject { if (entityId != null) put("entity_id", entityId) else put("entity_id", JsonNull) }, CameraResponse.serializer())
    /** Fresh JPEG; `t` busts any proxy cache. */
    suspend fun cameraSnapshot(): ByteArray =
        perform(Spec("GET", "/api/camera/snapshot", listOf("t" to System.currentTimeMillis().toString()), timeoutS = 10))
    suspend fun cameraFrames(days: Int): CameraFramesResponse =
        get("/api/camera/frames", CameraFramesResponse.serializer(), listOf("days" to days.toString()))
    suspend fun cameraFrameData(id: Int): ByteArray = perform(Spec("GET", "/api/camera/frames/$id", timeoutS = 20))
    suspend fun cameraAnalyse(plantId: Int?, note: String?): Photo =
        sendJson("POST", "/api/camera/analyse", buildJsonObject {
            if (plantId != null) put("plant_id", plantId) else put("plant_id", JsonNull)
            if (!note.isNullOrEmpty()) put("note", note)
        }, Photo.serializer(), LONG_TIMEOUT_S)

    // MARK: Control

    suspend fun pauseControl(minutes: Int) = sendIgnoringBody("POST", "/api/control/pause", encode(PauseRequest.serializer(), PauseRequest(minutes)))
    suspend fun resumeControl() = sendIgnoringBody("POST", "/api/control/resume")
    /** Whole-tent OFF: every device off and kept off until startTent(). */
    suspend fun setStandby(): StandbyResponse = send("POST", "/api/control/standby", StandbyResponse.serializer())
    /** Back to fully automatic (also clears pause and manual overrides on the backend). */
    suspend fun startTent(): StandbyResponse = send("POST", "/api/control/start", StandbyResponse.serializer())
}

package com.growop.app.data

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.channels.ClosedReceiveChannelException
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit

/**
 * Discovers the Grow Brain add-on's ingress path and keeps a fresh ingress session.
 *
 * Home Assistant's REST proxy (`/api/hassio/...`) only allows a short allow-list of paths and answers
 * 401 for `addons`, `addons/<slug>/info` and `ingress/session`, so this talks to the Supervisor the way
 * the HA frontend does: over the WebSocket API (`/api/websocket`, `supervisor/api` commands).
 * One instance per configured connection.
 */
class HAIngress(
    http: OkHttpClient,
    private val json: Json,
    @Volatile var slug: String? = null,
    @Volatile var ingressPath: String? = null,
) {
    data class Resolved(
        /** HA base + ingress path (no trailing slash). API paths are appended directly. */
        val base: String,
        /** Value for the `Cookie` header. */
        val cookie: String,
    )

    companion object {
        const val SESSION_MAX_AGE_MS = 10L * 60 * 1000
        private const val REPLY_TIMEOUT_MS = 20_000L
    }

    // Web sockets get their own client: no read/call timeout (we time out per reply ourselves).
    private val wsClient: OkHttpClient = http.newBuilder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .callTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(0, TimeUnit.MILLISECONDS)
        .build()

    private val lock = Mutex()
    private var sessionId: String? = null
    private var sessionCreatedAt = 0L

    suspend fun resolve(cfg: ServerConfig, forceNewSession: Boolean = false, forceDiscovery: Boolean = false): Resolved {
        val ha = cfg.normalizedHaUrl
        if (ha.isEmpty() || cfg.trimmedHaToken.isEmpty()) throw ApiError.NotConfigured
        lock.withLock {
            val needDiscovery = forceDiscovery || ingressPath == null || slug == null
            val sid = sessionId
            val needSession = forceNewSession || sid == null || System.currentTimeMillis() - sessionCreatedAt >= SESSION_MAX_AGE_MS
            if (needDiscovery || needSession) {
                val ws = SupervisorSocket(wsClient, json, cfg)
                try {
                    ws.connectAndAuthenticate()
                    if (needDiscovery) discover(ws)
                    if (needSession) {
                        sessionId = createSession(ws)
                        sessionCreatedAt = System.currentTimeMillis()
                    }
                } finally {
                    ws.close()
                }
            }
            var path = (ingressPath ?: "").trimEnd('/')
            if (!path.startsWith("/")) path = "/$path"
            return Resolved(base = ha + path, cookie = "ingress_session=${sessionId}")
        }
    }

    // Steps 1 + 2: find the add-on and read its ingress path.
    private suspend fun discover(ws: SupervisorSocket) {
        val list = step("Finding the Grow Brain add-on in Home Assistant") { ws.supervisor("/addons", "get") }
        val addons = (list as? JsonObject)?.get("addons")?.let { runCatching { it.jsonArray }.getOrNull() } ?: emptyList()
        val addon = addons.mapNotNull { it as? JsonObject }.firstOrNull { a ->
            val s = a["slug"]?.str() ?: return@firstOrNull false
            s == "grow_brain" || s.endsWith("_grow_brain")
        } ?: throw ApiError.HaAddonNotFound
        val foundSlug = addon["slug"]!!.str()!!
        val info = step("Reading the add-on's ingress address") { ws.supervisor("/addons/$foundSlug/info", "get") }
        val path = (info as? JsonObject)?.get("ingress_url")?.str()
        if (path.isNullOrEmpty()) {
            throw ApiError.HaError(0, "The Grow Brain add-on has no ingress URL. Is ingress enabled and the add-on running?")
        }
        slug = foundSlug
        ingressPath = path
    }

    // Step 3: open an ingress session.
    private suspend fun createSession(ws: SupervisorSocket): String {
        val d = try {
            ws.supervisor("/ingress/session", "post")
        } catch (e: ApiError) {
            when (e) {
                is ApiError.HaTokenRejected, is ApiError.HaNotAdmin, is ApiError.HaIngressSessionFailed, is ApiError.Network, is ApiError.HaWebSocketFailed -> throw e
                else -> throw ApiError.HaIngressSessionFailed(e.message)
            }
        }
        val sid = (d as? JsonObject)?.get("session")?.str()
        if (sid.isNullOrEmpty()) throw ApiError.HaIngressSessionFailed("No session id was returned.")
        return sid
    }

    /** Wraps generic transport/protocol errors with the step name; specific HA errors pass through unchanged. */
    private inline fun <T> step(name: String, block: () -> T): T = try {
        block()
    } catch (e: ApiError) {
        when (e) {
            is ApiError.HaTokenRejected, is ApiError.HaNotAdmin, is ApiError.HaAddonNotFound, is ApiError.Step -> throw e
            else -> throw ApiError.Step(name, e)
        }
    }

    private fun JsonElement.str(): String? = (this as? JsonPrimitive)?.contentOrNull
}

/**
 * A short-lived Home Assistant WebSocket session: authenticate, run `supervisor/api` commands, close.
 * Messages are pushed into a channel by OkHttp's listener thread and consumed with per-reply timeouts.
 */
private class SupervisorSocket(private val client: OkHttpClient, private val json: Json, private val cfg: ServerConfig) {
    private val incoming = Channel<JsonObject>(Channel.UNLIMITED)
    @Volatile private var failure: Throwable? = null
    private var socket: WebSocket? = null
    private var nextId = 1
    private val host: String = cfg.normalizedHaUrl.toHttpUrlOrNull()?.host ?: cfg.normalizedHaUrl

    private val listener = object : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            val obj = runCatching { json.parseToJsonElement(text).jsonObject }.getOrNull() ?: return
            incoming.trySend(obj)
        }
        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            val why = when {
                response != null && response.code == 401 -> "Home Assistant rejected the access token."
                response != null -> "Home Assistant replied ${response.code} to the WebSocket handshake at ${webSocket.request().url}. Is this address really Home Assistant?"
                else -> ApiError.describe(t)
            }
            failure = if (response?.code == 401) ApiError.HaTokenRejected else ApiError.HaWebSocketFailed(host, why)
            incoming.close()
        }
        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(code, reason) }
        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { incoming.close() }
    }

    suspend fun connectAndAuthenticate() {
        val base = cfg.normalizedHaUrl.toHttpUrlOrNull() ?: throw ApiError.InvalidUrl(cfg.normalizedHaUrl)
        val url = base.newBuilder().encodedPath("/api/websocket").build()
        socket = client.newWebSocket(Request.Builder().url(url).build(), listener)
        // Server → {"type":"auth_required"}; client → {"type":"auth","access_token":...}; server → auth_ok | auth_invalid
        val first = next("waiting for Home Assistant to ask for the token")
        when (first["type"]?.jsonPrimitive?.contentOrNull) {
            "auth_required" -> {}
            "auth_ok" -> return
            "auth_invalid" -> throw ApiError.HaTokenRejected
            else -> throw ApiError.HaWebSocketFailed(host, "Unexpected first message (${first["type"]}). Is this address really Home Assistant?")
        }
        send(buildJsonObject { put("type", "auth"); put("access_token", cfg.trimmedHaToken) })
        val reply = next("waiting for Home Assistant to accept the token")
        when (reply["type"]?.jsonPrimitive?.contentOrNull) {
            "auth_ok" -> {}
            "auth_invalid" -> throw ApiError.HaTokenRejected
            else -> throw ApiError.HaWebSocketFailed(host, "Unexpected reply while signing in (${reply["type"]}).")
        }
    }

    /**
     * Runs one `supervisor/api` command and returns the Supervisor's `data` (HA hands it back as `result`
     * directly; a wrapped `{result:"ok",data:{...}}` is unwrapped too).
     */
    suspend fun supervisor(endpoint: String, method: String): JsonElement? {
        val id = nextId++
        send(buildJsonObject { put("id", id); put("type", "supervisor/api"); put("endpoint", endpoint); put("method", method) })
        while (true) {
            val msg = next("waiting for the reply to $method $endpoint")
            if (msg["type"]?.jsonPrimitive?.contentOrNull != "result") continue
            if (msg["id"]?.jsonPrimitive?.intOrNull != id) continue
            val success = msg["success"]?.jsonPrimitive?.booleanOrNull ?: false
            if (!success) {
                val err = msg["error"] as? JsonObject
                val code = err?.get("code")?.jsonPrimitive?.contentOrNull ?: ""
                val message = err?.get("message")?.jsonPrimitive?.contentOrNull
                if (code == "unauthorized" || code == "not_admin") throw ApiError.HaNotAdmin
                throw ApiError.HaError(0, message ?: "Home Assistant refused the command ($code).")
            }
            val result = msg["result"]
            val wrapped = result as? JsonObject
            if (wrapped != null && wrapped.containsKey("data") && wrapped["result"]?.jsonPrimitive?.contentOrNull in listOf("ok", "error")) {
                if (wrapped["result"]?.jsonPrimitive?.contentOrNull == "error") {
                    throw ApiError.HaError(0, wrapped["message"]?.jsonPrimitive?.contentOrNull ?: "Supervisor error")
                }
                return wrapped["data"]
            }
            return result
        }
    }

    private fun send(obj: JsonObject) {
        val ok = socket?.send(json.encodeToString(JsonObject.serializer(), obj)) ?: false
        if (!ok) throw ApiError.HaWebSocketFailed(host, "The connection closed before the message could be sent.")
    }

    private suspend fun next(what: String): JsonObject {
        val msg = withTimeoutOrNull(20_000L) {
            try {
                incoming.receive()
            } catch (e: ClosedReceiveChannelException) {
                null
            }
        }
        if (msg != null) return msg
        failure?.let { throw it }
        if (incoming.isClosedForReceive) throw ApiError.HaWebSocketFailed(host, "Home Assistant closed the connection while $what.")
        throw ApiError.HaWebSocketFailed(host, "Home Assistant didn't reply within 20 seconds while $what.")
    }

    fun close() {
        runCatching { socket?.close(1000, null) }
        runCatching { socket?.cancel() }
        incoming.close()
    }
}

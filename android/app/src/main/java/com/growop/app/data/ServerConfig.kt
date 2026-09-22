package com.growop.app.data

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.first

/** How the app reaches the grow brain. */
enum class ConnectionMode(val title: String) {
    /** Plain HTTP to the add-on's own port on the home LAN. */
    DIRECT("Same Wi‑Fi"),
    /** Through Home Assistant's add-on ingress proxy (works remotely via Nabu Casa). */
    HOME_ASSISTANT("Through Home Assistant");

    companion object {
        fun from(s: String?): ConnectionMode = entries.firstOrNull { it.name == s } ?: DIRECT
    }
}

/** Where the grow brain lives. */
data class ServerConfig(
    val mode: ConnectionMode = ConnectionMode.DIRECT,
    /** Direct mode: the add-on's base URL, e.g. http://homeassistant.local:8099 */
    val baseUrl: String = "",
    /** Grow Brain API key (sent as X-API-Key in BOTH modes). */
    val apiKey: String = "",
    /** Home Assistant mode: HA base URL, e.g. https://xxxx.ui.nabu.casa */
    val haUrl: String = "",
    /** Home Assistant long-lived access token. */
    val haToken: String = "",
    /** Cached discovery results (refreshed automatically when stale). */
    val haAddonSlug: String? = null,
    val haIngressPath: String? = null,
) {
    companion object {
        const val DEFAULT_URL = "http://homeassistant.local:8099"

        /** Adds a scheme if missing and strips trailing slashes. */
        fun normalize(raw: String, defaultScheme: String): String {
            var s = raw.trim()
            if (s.isNotEmpty() && !s.lowercase().startsWith("http://") && !s.lowercase().startsWith("https://")) {
                s = "$defaultScheme://$s"
            }
            return s.trimEnd('/')
        }
    }

    val normalizedBaseUrl: String get() = normalize(baseUrl, "http")
    val normalizedHaUrl: String get() = normalize(haUrl, "https")
    val trimmedApiKey: String get() = apiKey.trim()
    val trimmedHaToken: String get() = haToken.trim()

    val isConfigured: Boolean
        get() {
            if (trimmedApiKey.isEmpty()) return false
            return when (mode) {
                ConnectionMode.DIRECT -> normalizedBaseUrl.isNotEmpty()
                ConnectionMode.HOME_ASSISTANT -> normalizedHaUrl.isNotEmpty() && trimmedHaToken.isNotEmpty()
            }
        }

    /** True when the user-entered fields differ (ignores cached discovery values). */
    fun differsInUserFields(other: ServerConfig): Boolean =
        mode != other.mode || baseUrl != other.baseUrl || apiKey != other.apiKey ||
            haUrl != other.haUrl || haToken != other.haToken
}

private val Context.growDataStore: DataStore<Preferences> by preferencesDataStore(name = "growop")

/** DataStore-backed persistence for the connection config and small per-phone preferences. */
class ConfigStore(private val context: Context) {
    private object Keys {
        val mode = stringPreferencesKey("server.mode")
        val url = stringPreferencesKey("server.url")
        val apiKey = stringPreferencesKey("server.apiKey")
        val haUrl = stringPreferencesKey("server.haUrl")
        val haToken = stringPreferencesKey("server.haToken")
        val haAddonSlug = stringPreferencesKey("server.haAddonSlug")
        val haIngressPath = stringPreferencesKey("server.haIngressPath")
        val myPlantId = intPreferencesKey("myPlantId")
        val units = stringPreferencesKey("units")
    }

    data class Loaded(val config: ServerConfig, val myPlantId: Int?, val units: String?)

    suspend fun load(): Loaded {
        val p = context.growDataStore.data.first()
        val cfg = ServerConfig(
            mode = ConnectionMode.from(p[Keys.mode]),
            baseUrl = p[Keys.url] ?: "",
            apiKey = p[Keys.apiKey] ?: "",
            haUrl = p[Keys.haUrl] ?: "",
            haToken = p[Keys.haToken] ?: "",
            haAddonSlug = p[Keys.haAddonSlug],
            haIngressPath = p[Keys.haIngressPath],
        )
        return Loaded(cfg, p[Keys.myPlantId], p[Keys.units])
    }

    suspend fun saveConfig(cfg: ServerConfig) {
        context.growDataStore.edit { p ->
            p[Keys.mode] = cfg.mode.name
            p[Keys.url] = cfg.baseUrl
            p[Keys.apiKey] = cfg.apiKey
            p[Keys.haUrl] = cfg.haUrl
            p[Keys.haToken] = cfg.haToken
            cfg.haAddonSlug?.let { p[Keys.haAddonSlug] = it } ?: p.remove(Keys.haAddonSlug)
            cfg.haIngressPath?.let { p[Keys.haIngressPath] = it } ?: p.remove(Keys.haIngressPath)
        }
    }

    suspend fun clearConfig() {
        context.growDataStore.edit { p ->
            listOf(Keys.mode, Keys.url, Keys.apiKey, Keys.haUrl, Keys.haToken, Keys.haAddonSlug, Keys.haIngressPath)
                .forEach { p.remove(it) }
        }
    }

    suspend fun saveMyPlantId(id: Int?) {
        context.growDataStore.edit { p -> if (id != null) p[Keys.myPlantId] = id else p.remove(Keys.myPlantId) }
    }

    suspend fun saveUnits(units: String) {
        context.growDataStore.edit { p -> p[Keys.units] = units }
    }
}

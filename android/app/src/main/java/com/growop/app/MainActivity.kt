package com.growop.app

import android.content.Intent
import android.content.pm.ApplicationInfo
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import com.growop.app.state.AppState
import com.growop.app.state.AppTab
import com.growop.app.ui.RootScreen
import com.growop.app.ui.theme.GrowOpTheme

class MainActivity : ComponentActivity() {
    private val appState: AppState get() = (application as GrowOpApp).container.appState

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        handleDeepLink(intent)
        handlePrefill(intent)
        setContent {
            GrowOpTheme {
                RootScreen(appState)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDeepLink(intent)
        handlePrefill(intent)
    }

    /** Debug builds only: `--es growop.prefill.url ... --es growop.prefill.apiKey ...` prefill the onboarding form. */
    private fun handlePrefill(intent: Intent?) {
        val extras = intent?.extras ?: return
        val debuggable = (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
        if (!debuggable) return
        val map = listOf("url", "apiKey", "haURL", "haToken")
            .mapNotNull { k -> extras.getString("growop.prefill.$k")?.let { k to it } }
            .toMap()
        if (map.isNotEmpty()) appState.prefill.value = map
    }

    override fun onStart() {
        super.onStart()
        appState.startPolling()
    }

    override fun onStop() {
        super.onStop()
        appState.stopPolling()
    }

    /** growop://advisor, growop://photos, growop://log, growop://tasks (used by push notifications). */
    private fun handleDeepLink(intent: Intent?) {
        val uri = intent?.data ?: return
        if (uri.scheme?.lowercase() != "growop") return
        val host = (uri.host ?: uri.path?.trim('/') ?: "").lowercase()
        if (host == "setup") {
            // growop://setup?mode=direct&url=http://…:8099&key=… from the dashboard's "Set up a phone" QR code
            val url = uri.getQueryParameter("url").orEmpty(); val key = uri.getQueryParameter("key").orEmpty()
            if (url.isNotBlank() && key.isNotBlank()) appState.provisionDirect(url, key)
            return
        }
        appState.pendingTab.value = when (host) {
            "advisor" -> AppTab.ADVISOR
            "photos" -> AppTab.PHOTOS
            "log" -> AppTab.LOG
            "tasks" -> AppTab.TASKS
            else -> AppTab.HOME
        }
    }
}

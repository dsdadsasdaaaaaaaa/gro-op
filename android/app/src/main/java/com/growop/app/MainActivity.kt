package com.growop.app

import android.content.Intent
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
        setContent {
            GrowOpTheme {
                RootScreen(appState)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDeepLink(intent)
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
        appState.pendingTab.value = when (host) {
            "advisor" -> AppTab.ADVISOR
            "photos" -> AppTab.PHOTOS
            "log" -> AppTab.LOG
            "tasks" -> AppTab.TASKS
            else -> AppTab.HOME
        }
    }
}

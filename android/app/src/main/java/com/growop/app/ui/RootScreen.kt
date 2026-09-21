package com.growop.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.EditNote
import androidx.compose.material.icons.filled.Psychology
import androidx.compose.material3.Badge
import androidx.compose.material3.BadgedBox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.state.AppState
import com.growop.app.state.AppTab
import com.growop.app.ui.advisor.AdvisorScreen
import com.growop.app.ui.home.HomeScreen
import com.growop.app.ui.log.LogScreen
import com.growop.app.ui.photos.PhotosScreen
import com.growop.app.ui.shared.FullScreenLoading
import com.growop.app.ui.shared.PlantChoiceScreen
import com.growop.app.ui.tasks.TasksScreen
import com.growop.app.ui.theme.GrowTheme

@Composable
fun RootScreen(app: AppState) {
    val ui by app.ui.collectAsStateWithLifecycle()
    when {
        !ui.configLoaded -> FullScreenLoading()
        !ui.isConfigured -> OnboardingScreen(app)
        else -> MainTabs(app)
    }
}

private data class TabSpec(val tab: AppTab, val label: String, val icon: ImageVector)

private val tabs = listOf(
    TabSpec(AppTab.HOME, "Home", Icons.Filled.Eco),
    TabSpec(AppTab.ADVISOR, "Advisor", Icons.Filled.Psychology),
    TabSpec(AppTab.LOG, "Log", Icons.Filled.EditNote),
    TabSpec(AppTab.PHOTOS, "Photos", Icons.Filled.CameraAlt),
    TabSpec(AppTab.TASKS, "Tasks", Icons.Filled.Checklist),
)

@Composable
fun MainTabs(app: AppState) {
    val ui by app.ui.collectAsStateWithLifecycle()
    val pending by app.pendingTab.collectAsStateWithLifecycle()
    var selected by rememberSaveable { mutableStateOf(AppTab.HOME) }
    val c = GrowTheme.colors

    LaunchedEffect(Unit) {
        app.startPolling()
        app.refreshSettings()
        app.loadPlants()
    }
    LaunchedEffect(pending) {
        pending?.let { selected = it; app.pendingTab.value = null }
    }

    // One-time "Which plant is yours?" once the backend reports plants and none is chosen yet.
    if (ui.showPlantChoice) {
        PlantChoiceScreen(ui, app) { }
        return
    }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        bottomBar = {
            NavigationBar(containerColor = c.card, tonalElevation = 0.dp) {
                tabs.forEach { spec ->
                    val badge: String? = when (spec.tab) {
                        AppTab.ADVISOR -> if (ui.status?.unreadBrief == true) "New" else null
                        AppTab.PHOTOS -> ui.needsYouPhotoCount.takeIf { it > 0 }?.toString()
                        AppTab.TASKS -> ui.needsYouTaskCount.takeIf { it > 0 }?.toString()
                        else -> null
                    }
                    NavigationBarItem(
                        selected = selected == spec.tab,
                        onClick = { selected = spec.tab },
                        icon = {
                            if (badge != null) {
                                BadgedBox(badge = { Badge(containerColor = c.alert) { Text(badge) } }) {
                                    Icon(spec.icon, contentDescription = spec.label)
                                }
                            } else Icon(spec.icon, contentDescription = spec.label)
                        },
                        label = { Text(spec.label, style = MaterialTheme.typography.labelMedium) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = c.brand, selectedTextColor = c.brand,
                            indicatorColor = c.brand.copy(alpha = 0.14f),
                            unselectedIconColor = c.textSecondary, unselectedTextColor = c.textSecondary,
                        ),
                    )
                }
            }
        },
    ) { inner ->
        Box(Modifier.fillMaxSize().background(c.bg).padding(inner)) {
            when (selected) {
                AppTab.HOME -> HomeScreen(app) { selected = it }
                AppTab.ADVISOR -> AdvisorScreen(app)
                AppTab.LOG -> LogScreen(app)
                AppTab.PHOTOS -> PhotosScreen(app)
                AppTab.TASKS -> TasksScreen(app)
            }
        }
    }
}

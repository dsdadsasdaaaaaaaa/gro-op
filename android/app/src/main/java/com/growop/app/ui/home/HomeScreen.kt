package com.growop.app.ui.home

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.SensorsOff
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Formatting
import com.growop.app.data.StatusResponse
import com.growop.app.state.AppState
import com.growop.app.state.AppTab
import com.growop.app.state.AppUi
import com.growop.app.ui.settings.SettingsScreen
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.InlineNotice
import com.growop.app.ui.shared.PlantSwitcher
import com.growop.app.ui.shared.WorkingView
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch

@Composable
fun HomeScreen(app: AppState, onSwitchTab: (AppTab) -> Unit) {
    var screen by rememberSaveable { mutableStateOf("home") }
    BackHandler(enabled = screen != "home") { screen = "home" }
    when (screen) {
        "plan" -> PlanScreen(app) { screen = "home" }
        "settings" -> SettingsScreen(app) { screen = "home" }
        "camera" -> CameraScreen(app) { screen = "home" }
        else -> HomeMain(app, onSwitchTab, onOpenPlan = { screen = "plan" }, onOpenSettings = { screen = "settings" }, onOpenCamera = { screen = "camera" })
    }
}

@Composable
private fun HomeMain(app: AppState, onSwitchTab: (AppTab) -> Unit, onOpenPlan: () -> Unit, onOpenSettings: () -> Unit, onOpenCamera: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    var confirmStandby by remember { mutableStateOf(false) }
    var confirmStart by remember { mutableStateOf(false) }
    var powerBusy by remember { mutableStateOf(false) }
    var selectedDevice by remember { mutableStateOf<String?>(null) }
    var alertTitle by remember { mutableStateOf("Something went wrong") }
    var alertMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        if (app.value.plantsSupported == null) app.loadPlants()
        if (app.value.plan == null) app.loadPlan()
        if (app.value.history.isEmpty()) app.loadHistory()
        app.loadTasks()
        app.loadPhotoRequests()
    }

    fun setStandby(on: Boolean) {
        scope.launch {
            powerBusy = true
            try { if (on) app.setStandby() else app.startTent() } catch (e: Throwable) {
                alertTitle = if (on) "Couldn't turn the tent off" else "Couldn't start the tent"
                alertMessage = ApiError.wrap(e).message
            } finally { powerBusy = false }
        }
    }

    PullToRefreshBox(
        isRefreshing = refreshing,
        onRefresh = { scope.launch { refreshing = true; app.refreshStatus(); app.loadHistory(force = true); refreshing = false } },
        modifier = Modifier.fillMaxSize().background(c.bg),
    ) {
        Column(
            Modifier.fillMaxSize().statusBarsPadding().verticalScroll(rememberScrollState()).padding(horizontal = GrowTheme.spacing).padding(bottom = 40.dp),
            verticalArrangement = Arrangement.spacedBy(GrowTheme.sectionSpacing),
        ) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                IconButton(onClick = onOpenSettings) { Icon(Icons.Filled.Settings, contentDescription = "Settings", tint = c.textSecondary) }
            }
            val st = ui.status
            when {
                st != null -> HomeContent(ui, st, app, powerBusy, onSwitchTab, onOpenPlan, onOpenCamera,
                    onPower = { if (st.standby == true) confirmStart = true else confirmStandby = true },
                    onStart = { confirmStart = true },
                    onDevice = { selectedDevice = it },
                    onResume = { scope.launch { try { app.resumeControl() } catch (e: Throwable) { alertMessage = ApiError.wrap(e).message } } })
                ui.statusError != null -> ConnectionProblem(ui.statusError!!, onRetry = { scope.launch { app.refreshStatus() } }, onSettings = onOpenSettings)
                else -> WorkingView("Loading your grow…", modifier = Modifier.padding(top = 80.dp))
            }
        }
    }

    if (confirmStandby) StandbyConfirmSheet(onConfirm = { setStandby(true) }, onDismiss = { confirmStandby = false })
    if (confirmStart) StartChecklistSheet(seedlings = ui.status?.grow?.stage == "seedling", onConfirm = { setStandby(false) }, onDismiss = { confirmStart = false })
    selectedDevice?.let { role -> DeviceSheet(app, role) { selectedDevice = null } }
    ErrorDialog(alertMessage, title = alertTitle) { alertMessage = null }
}

@Composable
private fun HomeContent(
    ui: AppUi, st: StatusResponse, app: AppState, powerBusy: Boolean,
    onSwitchTab: (AppTab) -> Unit, onOpenPlan: () -> Unit, onOpenCamera: () -> Unit,
    onPower: () -> Unit, onStart: () -> Unit, onDevice: (String) -> Unit, onResume: () -> Unit,
) {
    val c = GrowTheme.colors
    val standby = st.standby == true
    val plant = ui.selectedPlant
    val subtitle = buildList {
        if (standby) (plant?.dayTotal ?: st.grow?.dayTotal)?.let { add("Day $it") }
        val phase = ui.plan?.current?.displayTitle
        if (phase != null) add(phase) else st.grow?.stage?.takeIf { it.isNotEmpty() }?.let { add(Formatting.capitalize(it)) }
        if (plant != null) add(plant.displayName) else st.grow?.strain?.takeIf { it.isNotEmpty() }?.let { add(it) }
    }.joinToString(" · ")

    HomeHeader(day = plant?.dayTotal ?: st.grow?.dayTotal, subtitle = subtitle, standby = standby)
    PlantSwitcher(ui, app)

    // Notices
    val notices = buildList {
        ui.statusError?.let { add(Triple(Icons.Filled.WifiOff, "Showing the last update. $it", c.warn)) }
        if (st.haConnected == false) add(Triple(Icons.Filled.Warning, "Home Assistant isn't connected, so devices can't be controlled right now.", c.alert))
        if (st.sensor?.stale == true && !standby) add(Triple(Icons.Filled.SensorsOff, "Sensor not reporting. Readings are muted until it comes back.", c.warn))
        val paused = Formatting.parseISO(st.controlPausedUntil)
        if (paused != null && !standby) add(Triple(Icons.Filled.Pause, "Automation paused until ${Formatting.shortTime(paused)}.", c.warn))
        // Problems the brain has flagged (overheating, a plug offline, refill the tank, update available...)
        st.alerts.orEmpty()
            .filter { a -> val m = a.message.orEmpty(); m.isNotBlank() && !m.startsWith("Cannot reach Home Assistant") && !m.startsWith("Tent sensor is stale") }
            .forEach { a -> add(Triple(Icons.Filled.Warning, a.message.orEmpty(), if (a.level == "alert") c.alert else c.warn)) }
    }
    if (notices.isNotEmpty()) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { notices.forEach { (i, t, tint) -> InlineNotice(i, t, tint) } }
    }

    // One calm card in standby instead of "off" everywhere.
    if (standby) StandbyCard(busy = powerBusy, onStart = onStart) else TentPowerPill(running = true, busy = powerBusy, onClick = onPower)

    TodayCard(app, ui.plantTasks + ui.tentTasks) { onSwitchTab(AppTab.TASKS) }

    VitalsCard(sensor = st.sensor, targets = st.targets, usesF = ui.usesFahrenheit, history = ui.history, muted = standby)
    if (!standby) {
        AssessmentLine(assessment = st.assessment, standby = false)
        LightBar(
            onTime = st.targets?.lightOnTime, hours = st.targets?.lightHours, isOn = st.light?.isOn ?: false,
            nextChange = Formatting.parseISO(st.light?.nextChangeAt), schedule = st.light?.schedule, muted = false,
        )
    }
    st.camera?.let { cam -> CameraCard(app, cam, muted = standby, onClick = onOpenCamera) }
    GrowPlanCard(plan = ui.plan, growStartDate = plant?.startDate ?: st.grow?.startDate, onClick = onOpenPlan)
    DevicesGrid(devices = (st.devices ?: emptyList()).filter { it.isSwitch && it.entityId != null }, muted = standby) { onDevice(it.role) }
    val tank = st.humidifierTank
    if (tank != null && st.devices.orEmpty().any { it.role == "humidifier" && it.entityId != null }) TankCard(app, tank)
    NeedsYouRow(tasks = ui.needsYouTaskCount, photos = ui.needsYouPhotoCount, unreadBrief = st.unreadBrief ?: false, onTap = onSwitchTab)

    // Footer
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (!standby && Formatting.parseISO(st.controlPausedUntil) != null) {
            TextButton(onClick = onResume) { Text("Resume automation now", color = c.brand, style = MaterialTheme.typography.labelLarge) }
        }
        ui.lastStatusAt?.let { Text("Updated ${Formatting.shortTime(it)}", style = MaterialTheme.typography.bodySmall, color = c.textTertiary) }
    }
}

@Composable
private fun ConnectionProblem(error: String, onRetry: () -> Unit, onSettings: () -> Unit) {
    val c = GrowTheme.colors
    GrowCard(modifier = Modifier.padding(top = 40.dp)) {
        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(Modifier.size(84.dp).background(c.warn.copy(alpha = 0.12f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.WifiOff, contentDescription = null, tint = c.warn, modifier = Modifier.size(36.dp))
            }
            Text("Can't reach GrowOp at home", style = MaterialTheme.typography.titleLarge, color = c.text)
            Text(error, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary, textAlign = TextAlign.Center)
            BigButton("Try again", filled = false, onClick = onRetry)
            TextButton(onClick = onSettings) { Text("Connection settings", color = c.brand, style = MaterialTheme.typography.labelLarge) }
            Spacer(Modifier.height(0.dp))
        }
    }
}

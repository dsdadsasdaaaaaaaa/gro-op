package com.growop.app.ui.settings

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberTimePickerState
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.CameraCandidate
import com.growop.app.data.ConnectionMode
import com.growop.app.data.Formatting
import com.growop.app.data.GrowProfile
import com.growop.app.data.Settings
import com.growop.app.data.Targets
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.ConfirmDialog
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.LocalTime
import kotlin.math.roundToInt

// MARK: - Small form helpers shared by the settings screens

@Composable
fun SectionHeader(text: String) {
    Text(text.uppercase(), style = MaterialTheme.typography.labelMedium, color = GrowTheme.colors.textSecondary, modifier = Modifier.padding(start = 4.dp, top = 8.dp))
}

@Composable
fun Footnote(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = GrowTheme.colors.textSecondary, modifier = Modifier.padding(horizontal = 4.dp))
}

@Composable
fun LabeledField(label: String, value: String, onValue: (String) -> Unit, placeholder: String = "", numeric: Boolean = false, suffix: String? = null, minLines: Int = 1, maxLines: Int = 1) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
        Spacer(Modifier.height(4.dp))
        OutlinedTextField(
            value = value, onValueChange = onValue, placeholder = { Text(placeholder) },
            singleLine = maxLines == 1, minLines = minLines, maxLines = maxLines,
            keyboardOptions = if (numeric) KeyboardOptions(keyboardType = KeyboardType.Decimal) else KeyboardOptions.Default,
            suffix = suffix?.let { { Text(it, color = c.textSecondary) } },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
fun SwitchRow(label: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyLarge, color = GrowTheme.colors.text, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

/** A row that opens a dropdown of options. */
@Composable
fun PickerRow(label: String, valueLabel: String, options: List<Pair<String, String>>, enabled: Boolean = true, onSelect: (String) -> Unit) {
    val c = GrowTheme.colors
    var open by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(enabled = enabled) { open = true }.padding(vertical = 10.dp, horizontal = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(label, style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
            Text(valueLabel, style = MaterialTheme.typography.bodyLarge, color = c.brand)
            Spacer(Modifier.width(4.dp))
            Icon(Icons.Filled.ExpandMore, contentDescription = null, tint = c.textTertiary, modifier = Modifier.size(18.dp))
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            options.forEach { (key, text) ->
                DropdownMenuItem(text = { Text(text) }, onClick = { open = false; onSelect(key) })
            }
        }
    }
}

@Composable
fun ActionRow(text: String, loading: Boolean = false, enabled: Boolean = true, destructive: Boolean = false, onClick: () -> Unit) {
    val c = GrowTheme.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(enabled = enabled && !loading, onClick = onClick).padding(vertical = 12.dp, horizontal = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (loading) { CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.brand); Spacer(Modifier.width(10.dp)) }
        Text(text, style = MaterialTheme.typography.bodyLarge, color = if (!enabled) c.textTertiary else if (destructive) c.alert else c.brand)
    }
}

// MARK: - Settings screen

@Composable
fun SettingsScreen(app: AppState, onBack: () -> Unit) {
    var sub by rememberSaveable { mutableStateOf("main") }
    BackHandler(enabled = sub != "main") { sub = "main" }
    val ui by app.ui.collectAsStateWithLifecycle()
    when {
        sub == "addPlant" -> AddPlantScreen(app) { sub = "main" }
        sub.startsWith("plant:") -> {
            val id = sub.removePrefix("plant:").toIntOrNull()
            val plant = ui.plants.firstOrNull { it.id == id }
            if (plant != null) PlantEditScreen(app, plant) { sub = "main" } else sub = "main"
        }
        else -> SettingsMain(app, onBack, onEditPlant = { sub = "plant:$it" }, onAddPlant = { sub = "addPlant" })
    }
}

@Composable
private fun SettingsMain(app: AppState, onBack: () -> Unit, onEditPlant: (Int) -> Unit, onAddPlant: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()

    // Server (read-only; set up once on first launch)
    var testing by remember { mutableStateOf(false) }
    var testResult by remember { mutableStateOf<String?>(null) }
    var testOK by remember { mutableStateOf<Boolean?>(null) }

    // Grow / tent
    var grow by remember { mutableStateOf<GrowProfile?>(null) }
    var expectedFlowerDays by remember { mutableStateOf("") }
    var exhaustDucted by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf("") }
    var savingGrow by remember { mutableStateOf(false) }
    var stageSelection by remember { mutableStateOf("") }
    var pendingStage by remember { mutableStateOf<String?>(null) }
    var changingStage by remember { mutableStateOf(false) }

    // Targets
    var targets by remember { mutableStateOf<Targets?>(null) }
    var tMin by remember { mutableStateOf("") }
    var tMax by remember { mutableStateOf("") }
    var hMin by remember { mutableStateOf("") }
    var hMax by remember { mutableStateOf("") }
    var vMin by remember { mutableStateOf("") }
    var vMax by remember { mutableStateOf("") }
    var lightOn by remember { mutableStateOf("") }
    var lightHours by remember { mutableStateOf("") }
    var savingTargets by remember { mutableStateOf(false) }

    // Preferences
    var units by remember { mutableStateOf("c") }
    var briefTime by remember { mutableStateOf(LocalTime.of(8, 0)) }
    var showTimePicker by remember { mutableStateOf(false) }
    var notifyService by remember { mutableStateOf("") }
    var notifyOptions by remember { mutableStateOf<List<String>>(emptyList()) }
    var autoApply by remember { mutableStateOf(true) }
    var model by remember { mutableStateOf("") }
    var budget by remember { mutableStateOf("") }
    var advancedOpen by remember { mutableStateOf(false) }
    var savingPrefs by remember { mutableStateOf(false) }
    var confirmReset by remember { mutableStateOf(false) }
    var confirmSetupAgain by remember { mutableStateOf(false) }
    var showLightPicker by remember { mutableStateOf(false) }
    val context = androidx.compose.ui.platform.LocalContext.current
    val appVersion = remember { runCatching { context.packageManager.getPackageInfo(context.packageName, 0).versionName }.getOrNull() ?: "?" }

    var alertTitle by remember { mutableStateOf("Something went wrong") }
    var alertMessage by remember { mutableStateOf<String?>(null) }
    var loading by remember { mutableStateOf(true) }

    // Tent camera
    var cameraCandidates by remember { mutableStateOf<List<CameraCandidate>>(emptyList()) }
    var cameraEntity by remember { mutableStateOf("") }
    var cameraSupported by remember { mutableStateOf(true) }
    var cameraBusy by remember { mutableStateOf(false) }
    suspend fun loadCamera() {
        try {
            val r = app.client.camera()
            cameraSupported = true
            val cands = (r.candidates ?: emptyList()).toMutableList()
            cameraEntity = r.camera?.entityId ?: ""
            if (cameraEntity.isNotEmpty() && cands.none { it.entityId == cameraEntity }) cands.add(CameraCandidate(cameraEntity, r.camera?.name))
            cameraCandidates = cands
        } catch (e: ApiError.Http) {
            if (e.status == 404) cameraSupported = false
        } catch (_: Throwable) {}
    }

    fun applyGrow(g: GrowProfile) {
        grow = g
        expectedFlowerDays = g.expectedFlowerDays?.toString() ?: ""
        exhaustDucted = g.exhaustDucted ?: false
        notes = g.notes ?: ""
        stageSelection = g.stage ?: ""
    }
    fun fmt(d: Double?): String = d?.let { Formatting.number(it, 1) } ?: ""
    fun applyTargets(t: Targets) {
        targets = t
        val useF = app.value.usesFahrenheit
        tMin = fmt(if (useF) t.tempMinF ?: t.tempMinC?.let(Formatting::cToF) else t.tempMinC ?: t.tempMinF?.let(Formatting::fToC))
        tMax = fmt(if (useF) t.tempMaxF ?: t.tempMaxC?.let(Formatting::cToF) else t.tempMaxC ?: t.tempMaxF?.let(Formatting::fToC))
        hMin = fmt(t.humidityMin); hMax = fmt(t.humidityMax)
        vMin = fmt(t.vpdMin); vMax = fmt(t.vpdMax)
        lightOn = t.lightOnTime ?: ""
        lightHours = t.lightHours?.roundToInt()?.toString() ?: ""
    }
    fun applySettings(s: Settings) {
        units = s.units ?: "c"
        Formatting.parseHHmm(s.briefTime)?.let { briefTime = it }
        notifyService = s.notifyService ?: ""
        val opts = (s.notifyServicesAvailable ?: emptyList()).toMutableList()
        if (notifyService.isNotEmpty() && notifyService !in opts) opts.add(notifyService)
        notifyOptions = opts
        autoApply = s.autoApplyAdvisorTargets ?: true
        model = s.model ?: ""
        budget = s.advisorBudgetUsd?.let { Formatting.number(it, 0) } ?: ""
    }
    fun budgetValue(): Double? = budget.replace(',', '.').trim().toDoubleOrNull()
    /** Anything typed in the shared settings that hasn't been saved yet. */
    fun prefsChanged(): Boolean {
        val s = app.value.settings ?: return false
        return units != (s.units ?: "c") || Formatting.hhmm(briefTime) != (s.briefTime ?: "08:00") ||
            notifyService != (s.notifyService ?: "") || autoApply != (s.autoApplyAdvisorTargets ?: true) ||
            (model.isNotBlank() && model != (s.model ?: "")) || (budgetValue() != null && budgetValue() != s.advisorBudgetUsd)
    }
    suspend fun savePrefs() {
        savingPrefs = true
        try {
            val body = buildJsonObject {
                put("units", units)
                put("brief_time", Formatting.hhmm(briefTime))
                put("auto_apply_advisor_targets", autoApply)
                if (notifyService.isEmpty()) put("notify_service", JsonNull) else put("notify_service", notifyService)
                model.trim().takeIf { it.isNotEmpty() }?.let { put("model", it) }
                budgetValue()?.let { put("advisor_budget_usd", it) }
            }
            app.saveSettings(body)
            app.value.settings?.let { applySettings(it) }
            runCatching { app.client.targets() }.getOrNull()?.let { applyTargets(it) }
        } catch (e: Throwable) { alertTitle = "Couldn't save the settings"; alertMessage = ApiError.wrap(e).message } finally { savingPrefs = false }
    }
    suspend fun loadAll() {
        if (!app.value.isConfigured) { loading = false; return }
        loading = true
        coroutineScope {
            val g = async { runCatching { app.client.grow() }.getOrNull() }
            val t = async { runCatching { app.client.targets() }.getOrNull() }
            val s = async { runCatching { app.client.settings() }.getOrNull() }
            g.await()?.let { applyGrow(it) }
            t.await()?.let { applyTargets(it) }
            val st = s.await()
            if (st != null) { app.applySettings(st); applySettings(st) } else app.value.settings?.let { applySettings(it) }
        }
        app.loadPlants()
        loadCamera()
        loading = false
    }
    LaunchedEffect(Unit) { app.loadHealth(); loadAll() }


    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("Settings", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
                actions = { TextButton(onClick = { scope.launch { if (prefsChanged()) savePrefs(); onBack() } }) { Text("Done", style = MaterialTheme.typography.titleMedium, color = c.brand) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            // MARK: Server (read-only)
            SectionHeader("Server")
            GrowCard {
                val healthy = ui.status != null && ui.statusError == null
                val viaHa = ui.config.mode == ConnectionMode.HOME_ASSISTANT
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        if (healthy) Icons.Filled.CheckCircle else Icons.Filled.Error,
                        contentDescription = null,
                        tint = if (healthy) c.good else c.warn,
                        modifier = Modifier.size(28.dp),
                    )
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(if (viaHa) "Connected through Home Assistant" else "Connected on home Wi‑Fi",
                            style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold), color = c.text)
                        val secondary = buildList {
                            ui.serverVersion?.let { add("Grow Brain v$it") }
                            if (!healthy) add(ui.statusError?.let { "Last update failed" } ?: "Waiting for the first update")
                        }.joinToString(" · ")
                        if (secondary.isNotEmpty()) Text(secondary, style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                    }
                    TextButton(
                        enabled = !testing,
                        onClick = {
                            scope.launch {
                                testing = true; testResult = null; testOK = null
                                try {
                                    val r = app.client.verify(ui.config)
                                    val parts = mutableListOf(if (viaHa) "Connected through Home Assistant" else "Connected")
                                    r.health.version?.let { parts.add("v$it") }
                                    parts.add(if (r.health.haConnected == true) "Home Assistant OK" else "Home Assistant NOT connected")
                                    parts.add(if (r.health.advisorEnabled == true) "advisor on" else "advisor off")
                                    testResult = parts.joinToString(" · "); testOK = true
                                } catch (e: Throwable) { testResult = ApiError.wrap(e).message; testOK = false } finally { testing = false }
                            }
                        },
                    ) {
                        if (testing) { CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp, color = c.brand); Spacer(Modifier.width(6.dp)) }
                        Text(if (testing) "Testing…" else "Test connection", style = MaterialTheme.typography.labelMedium, color = c.brand)
                    }
                }
                testResult?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(it, style = MaterialTheme.typography.bodySmall, color = if (testOK == true) c.textSecondary else c.alert, modifier = Modifier.padding(horizontal = 4.dp))
                }
            }
            ActionRow("Set up this phone again…") { confirmSetupAgain = true }
            Footnote("GrowOp app $appVersion. Set up on first launch; \"Set up this phone again\" goes back to the setup screen.")

            if (loading) {
                Row(Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.brand); Spacer(Modifier.width(10.dp))
                    Text("Loading settings…", color = c.textSecondary)
                }
            } else {
                // MARK: Plants
                SectionHeader("Plants")
                GrowCard {
                    if (ui.plantsSupported == false) {
                        Text("This grow brain version doesn't support separate plants yet.", color = c.textSecondary)
                    } else {
                        if (ui.plants.isEmpty()) Text("No plants yet.", color = c.textSecondary)
                        ui.plants.forEachIndexed { i, p ->
                            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { onEditPlant(p.id) }.padding(vertical = 10.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.Eco, contentDescription = null, tint = if (p.id == ui.myPlantId) c.brand else c.textSecondary, modifier = Modifier.size(22.dp))
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(p.displayName, style = MaterialTheme.typography.bodyLarge, color = c.text)
                                    val meta = buildList { p.owner?.takeIf { it.isNotEmpty() }?.let { add(it) }; p.strain?.takeIf { it.isNotEmpty() }?.let { add(it) }; p.dayTotal?.let { add("day $it") } }.joinToString(" · ")
                                    if (meta.isNotEmpty()) Text(meta, style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                                }
                                if (p.id == ui.myPlantId) { LevelChip("Mine", c.brand); Spacer(Modifier.width(6.dp)) }
                                Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = c.textTertiary)
                            }
                            if (i != ui.plants.lastIndex) HorizontalDivider(color = c.track)
                        }
                        if (ui.plants.isNotEmpty()) {
                            HorizontalDivider(color = c.track)
                            PickerRow("Which plant is mine", ui.myPlant?.displayName ?: "Not set",
                                listOf("" to "Not set") + ui.plants.map { it.id.toString() to it.displayName }) { key -> app.setMyPlant(key.toIntOrNull()) }
                        }
                        ActionRow("Add plant", onClick = onAddPlant)
                    }
                }
                Footnote("One person per plant. The tent itself (devices, targets, light) is shared.")

                // MARK: Tent
                SectionHeader("Tent")
                GrowCard {
                    if (cameraSupported) {
                        val camLabel = if (cameraEntity.isEmpty()) "Off" else (cameraCandidates.firstOrNull { it.entityId == cameraEntity }?.displayName ?: cameraEntity)
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.weight(1f)) {
                                PickerRow("Tent camera", camLabel, listOf("" to "Off") + cameraCandidates.map { it.entityId to it.displayName }, enabled = !cameraBusy) { key ->
                                    if (key == cameraEntity) return@PickerRow
                                    cameraEntity = key
                                    scope.launch {
                                        cameraBusy = true
                                        try {
                                            val r = app.setCamera(key.ifEmpty { null })
                                            r.candidates?.let { cameraCandidates = it }
                                            cameraEntity = r.camera?.entityId ?: ""
                                        } catch (e: Throwable) { alertTitle = "Couldn't change the camera"; alertMessage = ApiError.wrap(e).message; loadCamera() } finally { cameraBusy = false }
                                    }
                                }
                            }
                            if (cameraBusy) CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = c.brand)
                        }
                        HorizontalDivider(color = c.track)
                    }
                    LabeledField("Expected flower days", expectedFlowerDays, { expectedFlowerDays = it }, placeholder = "65", numeric = true, suffix = "days")
                    SwitchRow("Exhaust is vented outside the tent", exhaustDucted) { exhaustDucted = it }
                    LabeledField("Tent notes", notes, { notes = it }, placeholder = "Anything about the tent", minLines = 2, maxLines = 5)
                    ActionRow("Save tent details", loading = savingGrow) {
                        scope.launch {
                            savingGrow = true
                            try {
                                val body = buildJsonObject {
                                    expectedFlowerDays.trim().toIntOrNull()?.let { put("expected_flower_days", it) }
                                    put("exhaust_ducted", exhaustDucted)
                                    put("notes", notes)
                                }
                                applyGrow(app.client.updateGrow(body)); app.refreshStatus()
                            } catch (e: Throwable) { alertTitle = "Couldn't save"; alertMessage = ApiError.wrap(e).message } finally { savingGrow = false }
                        }
                    }
                }

                // MARK: Stage
                SectionHeader("Change stage")
                GrowCard {
                    val stageOptions = GrowProfile.stages.map { it to Formatting.capitalize(it) } +
                        (if (stageSelection.isNotEmpty() && stageSelection !in GrowProfile.stages) listOf(stageSelection to Formatting.capitalize(stageSelection)) else emptyList())
                    PickerRow("Stage", if (stageSelection.isEmpty()) "—" else Formatting.capitalize(stageSelection), stageOptions, enabled = !changingStage) { new ->
                        val current = grow?.stage
                        if (!changingStage && current != null && new != current) pendingStage = new
                    }
                    if (changingStage) Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = c.brand); Spacer(Modifier.width(8.dp)); Text("Changing stage…", color = c.textSecondary) }
                    grow?.stageStarted?.takeIf { it.isNotEmpty() }?.let { Footnote("Current stage started ${Formatting.friendlyDay(it)}") }
                }
                Footnote("Changing to Flower switches the light to 12 hours a day by itself. Targets move to the new stage's defaults.")

                // MARK: Targets
                SectionHeader("Targets")
                GrowCard {
                    targets?.let { t ->
                        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                            Text("Currently from", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                            Text(when (t.source) { "stage_default" -> "Stage defaults"; "advisor" -> "Advisor"; "manual" -> "You (manual)"; else -> t.source ?: "—" }, color = c.textSecondary)
                        }
                        t.note?.takeIf { it.isNotEmpty() }?.let { Footnote(it) }
                    }
                    RangeRow("Temperature", ui.tempUnitLabel, tMin, { tMin = it }, tMax, { tMax = it })
                    RangeRow("Humidity", "%", hMin, { hMin = it }, hMax, { hMax = it })
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { showLightPicker = true }.padding(vertical = 10.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Lights on at", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                        Text(lightOn.ifEmpty { "06:00" }, style = MaterialTheme.typography.bodyLarge, color = c.brand)
                    }
                    LabeledField("Light hours per day", lightHours, { lightHours = it }, placeholder = "18", numeric = true, suffix = "h")
                    ActionRow("Save targets", loading = savingTargets) {
                        scope.launch {
                            savingTargets = true
                            try {
                                val useF = app.value.usesFahrenheit
                                fun num(s: String): Double? = s.replace(',', '.').trim().toDoubleOrNull()
                                val body = buildJsonObject {
                                    num(tMin)?.let { put("temp_min_c", if (useF) (Formatting.fToC(it) * 10).roundToInt() / 10.0 else it) }
                                    num(tMax)?.let { put("temp_max_c", if (useF) (Formatting.fToC(it) * 10).roundToInt() / 10.0 else it) }
                                    num(hMin)?.let { put("humidity_min", it) }
                                    num(hMax)?.let { put("humidity_max", it) }
                                    lightOn.trim().takeIf { it.isNotEmpty() }?.let { put("light_on_time", it) }
                                    lightHours.trim().toIntOrNull()?.let { put("light_hours", it) }
                                }
                                applyTargets(app.client.updateTargets(body)); app.refreshStatus()
                            } catch (e: Throwable) { alertTitle = "Couldn't save targets"; alertMessage = ApiError.wrap(e).message } finally { savingTargets = false }
                        }
                    }
                    ActionRow("Reset to stage defaults", destructive = true, enabled = !savingTargets) { confirmReset = true }
                }
                Footnote("The daytime ranges the automation keeps the tent in; at night it may be a few degrees cooler. Air dryness (VPD) follows from these.")

                // MARK: Tent settings (shared)
                SectionHeader("Tent settings (shared)")
                GrowCard {
                    Text("Temperature units", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
                    Spacer(Modifier.height(6.dp))
                    val unitOpts = listOf("c" to "°C", "f" to "°F")
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        unitOpts.forEachIndexed { i, (k, label) ->
                            SegmentedButton(selected = units == k, onClick = { units = k }, shape = SegmentedButtonDefaults.itemShape(i, unitOpts.size),
                                colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                                icon = {}) { Text(label) }
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { showTimePicker = true }.padding(vertical = 10.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Daily brief time", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                        Text(Formatting.hhmm(briefTime), style = MaterialTheme.typography.bodyLarge, color = c.brand)
                    }
                    SwitchRow("Let the advisor fine-tune temperature and humidity", autoApply) { autoApply = it }
                    LabeledField("Monthly advisor budget", budget, { budget = it }, placeholder = "40", numeric = true, suffix = "US$")
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { advancedOpen = !advancedOpen }.padding(vertical = 10.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Advanced (tent setup)", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                        Text(if (advancedOpen) "Hide" else "Show", style = MaterialTheme.typography.labelLarge, color = c.brand)
                    }
                    if (advancedOpen) {
                        PickerRow("Extra phone for every alert", if (notifyService.isEmpty()) "Nobody extra" else Formatting.phoneName(notifyService),
                            listOf("" to "Nobody extra") + notifyOptions.map { it to Formatting.phoneName(it) }) { notifyService = it }
                        val models = (ui.settings?.modelsAvailable ?: emptyList()).ifEmpty { listOfNotNull(model.ifEmpty { null }) }
                        if (models.isNotEmpty()) PickerRow("Advisor model", model.ifEmpty { "—" }, models.map { it to it }) { model = it }
                    }
                    ActionRow("Save", loading = savingPrefs) { scope.launch { savePrefs() } }
                    ui.settings?.let { s ->
                        Column(Modifier.padding(horizontal = 4.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            s.timezone?.let { Text("Timezone: $it", style = MaterialTheme.typography.bodySmall, color = c.textSecondary) }
                            if (s.safetyTempMinC != null && s.safetyTempMaxC != null) Text("Safety limits: ${Formatting.number(s.safetyTempMinC)}–${Formatting.number(s.safetyTempMaxC)}°C", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                            s.advisorMonthUsd?.let { Text("Advisor spend this month: $" + String.format(java.util.Locale.US, "%.2f", it) + " USD", style = MaterialTheme.typography.bodySmall, color = c.textSecondary) }
                        }
                    }
                }
                Footnote("These apply to the whole tent, for both of you. Each plant's own phone is set under Plants.")
            }
            Spacer(Modifier.height(32.dp))
        }
    }

    // Dialogs
    pendingStage?.let { s ->
        ConfirmDialog("Change stage to ${Formatting.capitalize(s)}?",
            "Temperature and humidity go to the new stage's settings, today is recorded as its start, and the advisor is told." + when (s) {
                "flower" -> " The light switches to 12 hours on and 12 off by itself: never turn it on during the dark hours."
                "veg" -> " The light stays on 18 hours a day."
                "drying" -> " The light stays off from now on."
                "curing" -> " Lights, humidifier and exhaust go idle."
                else -> ""
            },
            "Change stage",
            onConfirm = {
                scope.launch {
                    changingStage = true
                    try {
                        applyGrow(app.client.setStage(s))
                        runCatching { app.client.targets() }.getOrNull()?.let { applyTargets(it) }
                        app.refreshStatus()
                    } catch (e: Throwable) { alertTitle = "Couldn't change stage"; alertMessage = ApiError.wrap(e).message } finally { changingStage = false }
                }
            },
            onDismiss = { pendingStage = null })
    }
    if (confirmReset) ConfirmDialog("Reset targets to the stage defaults?", "Your own changes and the advisor's tweaks for this stage are dropped.", "Reset", destructive = true,
        onConfirm = {
            scope.launch {
                savingTargets = true
                try { applyTargets(app.client.resetTargets()); app.refreshStatus() } catch (e: Throwable) { alertTitle = "Couldn't reset targets"; alertMessage = ApiError.wrap(e).message } finally { savingTargets = false }
            }
        },
        onDismiss = { confirmReset = false })
    if (confirmSetupAgain) ConfirmDialog("Set this phone up again?", "GrowOp forgets how to reach the tent on this phone. Scan the setup QR code again afterwards.", "Set up again", destructive = true,
        onConfirm = { app.disconnect(); onBack() },
        onDismiss = { confirmSetupAgain = false })
    if (showLightPicker) {
        val start = Formatting.parseHHmm(lightOn) ?: LocalTime.of(6, 0)
        val lp = rememberTimePickerState(initialHour = start.hour, initialMinute = start.minute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { showLightPicker = false },
            containerColor = c.card,
            title = { Text("Lights on at") },
            text = { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { TimePicker(state = lp) } },
            confirmButton = { TextButton(onClick = { lightOn = Formatting.hhmm(LocalTime.of(lp.hour, lp.minute)); showLightPicker = false }) { Text("OK") } },
            dismissButton = { TextButton(onClick = { showLightPicker = false }) { Text("Cancel") } },
        )
    }
    if (showTimePicker) {
        val tp = rememberTimePickerState(initialHour = briefTime.hour, initialMinute = briefTime.minute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { showTimePicker = false },
            containerColor = c.card,
            title = { Text("Daily brief time") },
            text = { Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) { TimePicker(state = tp) } },
            confirmButton = { TextButton(onClick = { briefTime = LocalTime.of(tp.hour, tp.minute); showTimePicker = false }) { Text("OK") } },
            dismissButton = { TextButton(onClick = { showTimePicker = false }) { Text("Cancel") } },
        )
    }
    ErrorDialog(alertMessage, title = alertTitle) { alertMessage = null }
}

@Composable
private fun RangeRow(title: String, unit: String, min: String, onMin: (String) -> Unit, max: String, onMax: (String) -> Unit) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text("$title ($unit)", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(value = min, onValueChange = onMin, placeholder = { Text("min") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
            Text("–", color = c.textSecondary, textAlign = TextAlign.Center)
            OutlinedTextField(value = max, onValueChange = onMax, placeholder = { Text("max") }, singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f))
        }
    }
}

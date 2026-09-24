package com.growop.app.ui.log

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.foundation.clickable
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.ArrowCircleUp
import androidx.compose.material.icons.filled.Spa
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.Height
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.WaterDrop
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Formatting
import com.growop.app.data.LogEntry
import com.growop.app.data.LogRequest
import com.growop.app.data.LogResponse
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.CreatedItemsView
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelColor
import com.growop.app.ui.shared.NumberedList
import com.growop.app.ui.shared.PlantSwitcher
import com.growop.app.ui.shared.SectionTitle
import com.growop.app.ui.shared.WorkingView
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch

enum class LogKind(val key: String, val title: String, val icon: ImageVector) {
    WATER("water", "Watered", Icons.Filled.WaterDrop),
    PLANTED("planted", "Planted", Icons.Filled.Spa),
    TRANSPLANT("transplant", "Moved to big pot", Icons.Filled.ArrowCircleUp),
    HEIGHT("height", "Height", Icons.Filled.Height),
    NOTE("note", "Note", Icons.Filled.ChatBubble),
    PH("ph", "pH", Icons.Filled.Science),
    FEED("feed", "Fed", Icons.Filled.Restaurant),
    EC("ec", "EC / PPM", Icons.Filled.Bolt);

    val hasContext: Boolean get() = this == PH || this == EC

    companion object {
        fun from(kind: String?): LogKind? = entries.firstOrNull { it.key == kind } ?: if (kind == "ppm") EC else null
    }
}

@Composable
fun LogKind.color(): Color = when (this) {
    LogKind.PH -> GrowTheme.colors.night
    LogKind.EC -> GrowTheme.colors.warn
    LogKind.WATER -> GrowTheme.colors.brand
    LogKind.FEED -> GrowTheme.colors.good
    LogKind.HEIGHT, LogKind.PLANTED, LogKind.TRANSPLANT -> GrowTheme.colors.leaf
    LogKind.NOTE -> GrowTheme.colors.textSecondary
}

val contexts: List<Pair<String, String>> = listOf("water_in" to "Water going in", "runoff" to "Runoff")
fun contextLabel(c: String): String = contexts.firstOrNull { it.first == c }?.second ?: Formatting.capitalize(c)

@Composable
fun LogScreen(app: AppState) {
    var entryKind by remember { mutableStateOf<LogKind?>(null) }
    BackHandler(enabled = entryKind != null) { entryKind = null }
    val k = entryKind
    if (k != null) LogEntryScreen(app, k) { entryKind = null } else LogMain(app) { entryKind = it }
}

@Composable
private fun LogMain(app: AppState, onPick: (LogKind) -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { app.loadLog() }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(title = { Text("Log", style = MaterialTheme.typography.headlineMedium) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text))
        },
    ) { inner ->
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.loadLog(); refreshing = false } }, modifier = Modifier.fillMaxSize().padding(inner)) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(20.dp)) {
                PlantSwitcher(ui, app)
                Text("Log what you did or measured. It saves instantly and the advisor reads it in the morning brief, or ask it right away.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                LogKind.entries.chunked(2).forEach { row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        row.forEach { kind ->
                            val color = kind.color()
                            GrowCard(modifier = Modifier.weight(1f), padding = 16.dp, onClick = { onPick(kind) }) {
                                Box(Modifier.fillMaxWidth().heightIn(min = 96.dp)) {
                                    Box(Modifier.align(Alignment.TopEnd).size(44.dp).background(color.copy(alpha = 0.14f), CircleShape))
                                    Column(Modifier.align(Alignment.BottomStart), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                        Icon(kind.icon, contentDescription = null, tint = color, modifier = Modifier.size(34.dp))
                                        Text(kind.title, style = MaterialTheme.typography.titleMedium, color = c.text)
                                    }
                                }
                            }
                        }
                    }
                }
                GrowCard {
                    SectionTitle("Recent entries")
                    Spacer(Modifier.height(10.dp))
                    val entries = ui.logEntriesForSelected
                    if (entries.isEmpty()) Text("Nothing logged yet.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    entries.forEachIndexed { i, e ->
                        LogEntryRow(e)
                        if (i != entries.lastIndex) HorizontalDivider(color = c.track)
                    }
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
fun LogEntryRow(entry: LogEntry) {
    val c = GrowTheme.colors
    val kind = LogKind.from(entry.kind)
    var expanded by remember { mutableStateOf(false) }
    val headline = buildString {
        var s = Formatting.capitalize(entry.kind ?: "entry")
        when (entry.kind) {
            "ph" -> s = "pH"; "ec" -> s = "EC"; "ppm" -> s = "PPM"; "water" -> s = "Watered"
            "planted" -> s = "Planted"; "transplant" -> s = "Moved to big pot"; "feed" -> s = "Fed"
        }
        if (entry.context == "task") s = entry.note ?: s   // "Done: Water the cups"
        append(s)
        entry.value?.let { v ->
            append(" ").append(Formatting.number(v, 2))
            val u = entry.unit
            if (!u.isNullOrEmpty() && u.lowercase() != "ph") append(" ").append(u)
        }
        entry.context?.takeIf { it.isNotEmpty() && it != "task" }?.let { append(" · ").append(contextLabel(it)) }
    }
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.Top) {
        Icon(kind?.icon ?: Icons.Filled.ChatBubble, contentDescription = null, tint = kind?.color() ?: c.textSecondary, modifier = Modifier.size(22.dp))
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(headline, style = MaterialTheme.typography.titleSmall, color = c.text, modifier = Modifier.weight(1f))
                Text(Formatting.relative(entry.createdAt), style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            }
            if (!entry.note.isNullOrEmpty() && entry.context != "task") Text(entry.note, style = MaterialTheme.typography.bodySmall, color = c.textSecondary, maxLines = 2)
            val advice = entry.adviceSummary
            if (!advice.isNullOrEmpty()) {
                Text(advice, style = MaterialTheme.typography.bodySmall, color = c.text, maxLines = if (expanded) Int.MAX_VALUE else 3)
                val steps = entry.adviceSteps.orEmpty()
                if (expanded) steps.forEachIndexed { i, st -> Text("${i + 1}. $st", style = MaterialTheme.typography.bodySmall, color = c.textSecondary) }
                if (steps.isNotEmpty() || advice.length > 140) {
                    Text(if (expanded) "Less" else "More", style = MaterialTheme.typography.labelMedium, color = c.brand,
                        modifier = Modifier.clip(androidx.compose.foundation.shape.RoundedCornerShape(6.dp)).clickable { expanded = !expanded }.padding(vertical = 4.dp, horizontal = 2.dp))
                }
            }
        }
    }
}

// MARK: - Entry screen

@Composable
fun LogEntryScreen(app: AppState, kind: LogKind, onClose: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var valueText by remember { mutableStateOf("") }
    var context by remember { mutableStateOf("water_in") }
    var ecUnit by remember { mutableStateOf("EC") }
    var heightUnit by remember { mutableStateOf("cm") }
    var note by remember { mutableStateOf("") }
    var submitting by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<LogResponse?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val focus = remember { FocusRequester() }
    val color = kind.color()

    val parsedValue: Double? = valueText.replace(',', '.').trim().toDoubleOrNull()
    val canSubmit = when (kind) {
        LogKind.PH, LogKind.EC, LogKind.HEIGHT -> parsedValue != null
        LogKind.NOTE -> note.isNotBlank()
        LogKind.WATER, LogKind.FEED, LogKind.PLANTED, LogKind.TRANSPLANT -> true
    }
    val title = if (result == null) (ui.selectedPlant?.let { "Log ${kind.title} · ${it.shortName}" } ?: "Log ${kind.title}") else "Advice"

    fun submit(advise: Boolean) {
        val trimmedNote = note.trim()
        var req = when (kind) {
            LogKind.PH -> LogRequest("ph", parsedValue, "pH", context)
            LogKind.EC -> LogRequest(if (ecUnit == "EC") "ec" else "ppm", parsedValue, if (ecUnit == "EC") "mS/cm" else "ppm", context)
            LogKind.WATER -> LogRequest("water", parsedValue, if (parsedValue == null) null else "L")
            LogKind.FEED -> LogRequest("feed", parsedValue, if (parsedValue == null) null else "L")
            LogKind.HEIGHT -> LogRequest("height", parsedValue, heightUnit)
            LogKind.NOTE -> LogRequest("note")
            LogKind.PLANTED -> LogRequest("planted")
            LogKind.TRANSPLANT -> LogRequest("transplant")
        }
        if (trimmedNote.isNotEmpty()) req = req.copy(note = trimmedNote)
        req = req.copy(advise = advise)
        // The app's scope: leaving the screen while the advisor thinks must not lose the entry.
        app.launch {
            if (advise) submitting = true
            try {
                val r = app.submitLog(req)
                if (advise) result = r else onClose()
            } catch (e: Throwable) { error = ApiError.wrap(e).message } finally { submitting = false }
        }
    }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text(title, style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { if (result == null && !submitting) IconButton(onClick = onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Cancel") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            when {
                submitting -> WorkingView("Asking the advisor…", "This usually takes 10–40 seconds.", Modifier.padding(top = 60.dp))
                result != null -> AdviceResultView(result!!, onDone = onClose)
                else -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    val numberField: @Composable (String, String) -> Unit = { placeholder, suffix ->
                        OutlinedTextField(
                            value = valueText, onValueChange = { valueText = it }, placeholder = { Text(placeholder) },
                            suffix = { Text(suffix, color = c.textSecondary) }, singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            textStyle = MaterialTheme.typography.headlineSmall.copy(fontSize = 24.sp),
                            modifier = Modifier.fillMaxWidth().focusRequester(focus),
                        )
                    }
                    val unitToggle: @Composable (List<Pair<String, String>>, String, (String) -> Unit) -> Unit = { opts, sel, onSel ->
                        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                            opts.forEachIndexed { i, (k, label) ->
                                SegmentedButton(selected = sel == k, onClick = { onSel(k) }, shape = SegmentedButtonDefaults.itemShape(i, opts.size),
                                    colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                                    icon = {}) { Text(label) }
                            }
                        }
                    }
                    when (kind) {
                        LogKind.PH -> GrowCard {
                            Text("pH reading", style = MaterialTheme.typography.titleMedium, color = c.text); Spacer(Modifier.height(10.dp))
                            numberField("e.g. 6.3", "pH"); Spacer(Modifier.height(12.dp))
                            ContextPicker(context) { context = it }
                        }
                        LogKind.EC -> GrowCard {
                            Text("Nutrient strength", style = MaterialTheme.typography.titleMedium, color = c.text); Spacer(Modifier.height(10.dp))
                            unitToggle(listOf("EC" to "EC (mS/cm)", "PPM" to "PPM"), ecUnit) { ecUnit = it }; Spacer(Modifier.height(10.dp))
                            numberField(if (ecUnit == "EC") "e.g. 1.4" else "e.g. 700", if (ecUnit == "EC") "mS/cm" else "ppm"); Spacer(Modifier.height(12.dp))
                            ContextPicker(context) { context = it }
                        }
                        LogKind.WATER -> GrowCard {
                            Text("How much water? (optional)", style = MaterialTheme.typography.titleMedium, color = c.text); Spacer(Modifier.height(10.dp))
                            numberField("e.g. 0.05 for a cup, 1 for a pot", "litres")
                        }
                        LogKind.PLANTED -> GrowCard {
                            Text("Log it the day the seed goes into its cup. The plan and the advisor count the seedling days from here.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                        LogKind.TRANSPLANT -> GrowCard {
                            Text("Log it the day the plant goes into its 11 L pot. GrowOp then reminds you to switch the stage to Veg.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                        LogKind.FEED -> GrowCard {
                            Text("How much feed solution? (optional)", style = MaterialTheme.typography.titleMedium, color = c.text); Spacer(Modifier.height(10.dp))
                            numberField("e.g. 1.5", "litres")
                        }
                        LogKind.HEIGHT -> GrowCard {
                            Text("Plant height", style = MaterialTheme.typography.titleMedium, color = c.text); Spacer(Modifier.height(10.dp))
                            unitToggle(listOf("cm" to "cm", "in" to "inches"), heightUnit) { heightUnit = it }; Spacer(Modifier.height(10.dp))
                            numberField("e.g. 35", heightUnit)
                        }
                        LogKind.NOTE -> {}
                    }
                    GrowCard {
                        Text(if (kind == LogKind.NOTE) "What did you notice or do?" else "Note (optional)", style = MaterialTheme.typography.titleMedium, color = c.text)
                        Spacer(Modifier.height(10.dp))
                        OutlinedTextField(
                            value = note, onValueChange = { note = it }, minLines = 3, maxLines = 6,
                            placeholder = { Text(if (kind == LogKind.NOTE) "e.g. Lower leaves look a bit yellow…" else "Anything else the advisor should know") },
                            modifier = Modifier.fillMaxWidth().then(if (kind == LogKind.NOTE) Modifier.focusRequester(focus) else Modifier),
                        )
                    }
                    BigButton("Save", color = color, enabled = canSubmit) { submit(advise = false) }
                    BigButton("Save & ask the advisor (≈ \$0.05)", color = c.night, filled = false, enabled = canSubmit, icon = Icons.Filled.AutoAwesome) { submit(advise = true) }
                    Text("Save is instant and free. Asking takes 10–40 seconds and costs a few cents.", style = MaterialTheme.typography.bodySmall,
                        color = c.textSecondary, modifier = Modifier.fillMaxWidth(), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }
    LaunchedEffect(Unit) { runCatching { focus.requestFocus() } }
    ErrorDialog(error, title = "Couldn't save that") { error = null }
}

@Composable
private fun ContextPicker(selected: String, onSelect: (String) -> Unit) {
    val c = GrowTheme.colors
    Text("Measured", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
    Spacer(Modifier.height(6.dp))
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        contexts.forEachIndexed { i, (k, label) ->
            SegmentedButton(selected = selected == k, onClick = { onSelect(k) }, shape = SegmentedButtonDefaults.itemShape(i, contexts.size),
                colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                icon = {}) { Text(label, style = MaterialTheme.typography.labelMedium, maxLines = 1) }
        }
    }
}

// MARK: - Advice result

@Composable
fun AdviceResultView(result: LogResponse, onDone: () -> Unit) {
    val c = GrowTheme.colors
    val advice = result.advice
    val urgency = advice?.urgency ?: "info"
    val color = LevelColor.infoColor(urgency)
    val title = when (urgency) { "urgent" -> "Act now"; "attention" -> "Worth a look"; else -> "Advisor says" }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
        Column(Modifier.fillMaxWidth().clip(androidx.compose.foundation.shape.RoundedCornerShape(GrowTheme.radius)).background(color).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(LevelColor.icon(urgency), contentDescription = null, tint = Color.White, modifier = Modifier.size(26.dp))
                Spacer(Modifier.width(10.dp))
                Text(title, style = MaterialTheme.typography.titleLarge, color = Color.White)
            }
            Text(advice?.summary?.takeIf { it.isNotEmpty() } ?: "Logged. No specific advice this time.", style = MaterialTheme.typography.bodyLarge, color = Color.White.copy(alpha = 0.95f))
        }
        val steps = advice?.steps
        if (!steps.isNullOrEmpty()) {
            GrowCard {
                Text("Next steps", style = MaterialTheme.typography.titleMedium, color = c.text)
                Spacer(Modifier.height(12.dp))
                NumberedList(steps, color = color)
            }
        }
        CreatedItemsView(advice?.tasks, advice?.photoRequests)
        BigButton("Done", onClick = onDone)
        Spacer(Modifier.height(24.dp))
    }
}

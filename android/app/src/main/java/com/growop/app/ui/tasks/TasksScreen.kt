package com.growop.app.ui.tasks

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AddCircle
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Verified
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
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
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Formatting
import com.growop.app.data.TaskItem
import com.growop.app.state.AppState
import com.growop.app.ui.shared.EmptyStateView
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.shared.PlantSwitcher
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

@Composable
fun TasksScreen(app: AppState) {
    var adding by remember { mutableStateOf(false) }
    BackHandler(enabled = adding) { adding = false }
    if (adding) AddTaskScreen(app) { adding = false } else TasksMain(app) { adding = true }
}

@Composable
private fun TasksMain(app: AppState, onAdd: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var showDone by remember { mutableStateOf(false) }
    var refreshing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { app.loadTasks(includeDone = showDone) }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("Tasks", style = MaterialTheme.typography.headlineMedium) },
                actions = { IconButton(onClick = onAdd) { Icon(Icons.Filled.AddCircle, contentDescription = "Add task", tint = c.brand, modifier = Modifier.size(30.dp)) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text),
            )
        },
    ) { inner ->
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.loadTasks(includeDone = showDone); refreshing = false } }, modifier = Modifier.fillMaxSize().padding(inner)) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
                PlantSwitcher(ui, app)
                val plantTasks = ui.plantTasks
                val tentTasks = ui.tentTasks
                if (plantTasks.isEmpty() && tentTasks.isEmpty()) {
                    GrowCard { EmptyStateView(Icons.Filled.Verified, "Nothing to do", "The advisor adds tasks here when something needs doing. You can add your own with +.") }
                } else {
                    if (plantTasks.isNotEmpty()) TaskGroup(ui.selectedPlant?.displayName ?: "To do", Icons.Filled.Eco, plantTasks) { t ->
                        try { app.completeWithUndo(t) } catch (e: Throwable) { error = ApiError.wrap(e).message }
                    }
                    if (tentTasks.isNotEmpty()) TaskGroup("Tent", Icons.Filled.Home, tentTasks) { t ->
                        try { app.completeWithUndo(t) } catch (e: Throwable) { error = ApiError.wrap(e).message }
                    }
                }
                Row(
                    Modifier.clip(RoundedCornerShape(8.dp)).clickable { showDone = !showDone; if (showDone) scope.launch { app.loadTasks(includeDone = true) } }.padding(vertical = 6.dp, horizontal = 4.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(if (showDone) "Hide done" else "Show done", style = MaterialTheme.typography.labelLarge, color = c.textSecondary)
                    Spacer(Modifier.width(6.dp))
                    Icon(Icons.Filled.ExpandMore, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(18.dp).rotate(if (showDone) 180f else 0f))
                }
                if (showDone) {
                    val done = ui.doneTasksForSelected
                    if (done.isEmpty()) Text("No completed tasks yet.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        done.forEach { t -> TaskRow(t) { try { app.reopenTask(t) } catch (e: Throwable) { error = ApiError.wrap(e).message } } }
                    }
                }
                Spacer(Modifier.height(72.dp))   // room for the "Done · Undo" bar
            }
        }
    }
    ErrorDialog(error) { error = null }
}

@Composable
private fun TaskGroup(title: String, icon: ImageVector, tasks: List<TaskItem>, onToggle: suspend (TaskItem) -> Unit) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = c.text, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(title, style = MaterialTheme.typography.titleMedium, color = c.text)
        }
        tasks.forEach { t -> TaskRow(t) { onToggle(t) } }
    }
}

@Composable
fun TaskRow(task: TaskItem, onToggle: suspend () -> Unit) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var justTapped by remember { mutableStateOf(false) }
    val dueDate = Formatting.parseDay(task.due)
    val today = LocalDate.now()
    val overdue = dueDate != null && !task.isDone && dueDate.isBefore(today)
    val dueColor = when {
        dueDate == null || task.isDone -> c.textSecondary
        overdue -> c.alert
        dueDate == today -> c.warn
        else -> c.textSecondary
    }
    val dueText = when {
        task.due.isNullOrEmpty() -> ""
        dueDate == null -> task.due
        dueDate == today -> "Today"
        dueDate == today.plusDays(1) -> "Tomorrow"
        overdue -> "Overdue since ${Formatting.abbrevDate(dueDate)}"
        else -> Formatting.abbrevDate(dueDate)
    }
    val checked = task.isDone || justTapped
    Box(Modifier.fillMaxWidth().alpha(if (task.isDone) 0.7f else 1f)) {
        GrowCard(padding = 12.dp) {
            Row(verticalAlignment = Alignment.Top) {
                // Only this circle ticks the task off, so scrolling past can't do it by accident.
                Box(
                    Modifier.size(48.dp).clip(CircleShape).clickable(enabled = !busy, onClickLabel = if (task.isDone) "Mark not done" else "Mark done") {
                        justTapped = true
                        scope.launch { busy = true; onToggle(); busy = false; justTapped = false }
                    },
                    contentAlignment = Alignment.Center,
                ) {
                    if (busy) CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp, color = c.brand)
                    else Icon(if (checked) Icons.Filled.CheckCircle else Icons.Outlined.Circle,
                        contentDescription = if (task.isDone) "Mark not done: ${task.title ?: "task"}" else "Mark done: ${task.title ?: "task"}",
                        modifier = Modifier.size(32.dp),
                        tint = if (checked) c.brand else if (task.isHigh) c.alert else c.textSecondary.copy(alpha = 0.5f))
                }
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f).padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(task.title ?: "Task", style = MaterialTheme.typography.bodyLarge.copy(fontWeight = if (task.isHigh && !task.isDone) FontWeight.SemiBold else FontWeight.Normal),
                        color = if (task.isDone) c.textSecondary else c.text, textDecoration = if (task.isDone) TextDecoration.LineThrough else null)
                    if (!task.detail.isNullOrEmpty()) Text(task.detail, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (dueText.isNotEmpty()) LevelChip(dueText, dueColor)
                        if (task.isHigh && !task.isDone) LevelChip("Important", c.alert)
                        if (task.createdBy == "advisor") {
                            Icon(Icons.Filled.AutoAwesome, contentDescription = null, tint = c.night, modifier = Modifier.size(14.dp))
                            Text("Advisor", style = MaterialTheme.typography.bodySmall, color = c.night)
                        } else if (task.createdBy == "system") {
                            Icon(Icons.Filled.Eco, contentDescription = null, tint = c.brand, modifier = Modifier.size(14.dp))
                            Text("GrowOp", style = MaterialTheme.typography.bodySmall, color = c.brand)
                        }
                    }
                }
            }
        }
        if (task.isHigh && !task.isDone) {
            Box(Modifier.align(Alignment.CenterStart).padding(start = 6.dp, top = 14.dp, bottom = 14.dp).width(4.dp).height(40.dp).background(c.alert, RoundedCornerShape(2.dp)))
        }
    }
}

@Composable
fun AddTaskScreen(app: AppState, onClose: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var title by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var hasDue by remember { mutableStateOf(false) }
    var due by remember { mutableStateOf(LocalDate.now()) }
    var showPicker by remember { mutableStateOf(false) }
    var forTent by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("New task", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Cancel") } },
                actions = {
                    TextButton(enabled = !saving && title.isNotBlank(), onClick = {
                        scope.launch {
                            saving = true
                            try {
                                app.addTask(title.trim(), detail.trim().ifEmpty { null }, if (hasDue) Formatting.dayString(due) else null, if (forTent) null else app.value.selectedPlantId)
                                onClose()
                            } catch (e: Throwable) { error = ApiError.wrap(e).message } finally { saving = false }
                        }
                    }) { Text(if (saving) "Saving…" else "Add", style = MaterialTheme.typography.titleMedium) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
            GrowCard {
                Text("Task", style = MaterialTheme.typography.titleMedium, color = c.text)
                Spacer(Modifier.height(10.dp))
                OutlinedTextField(value = title, onValueChange = { title = it }, placeholder = { Text("What needs doing?") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = detail, onValueChange = { detail = it }, placeholder = { Text("Details (optional)") }, minLines = 2, maxLines = 5, modifier = Modifier.fillMaxWidth())
            }
            if (ui.plants.isNotEmpty()) {
                GrowCard {
                    Text("For", style = MaterialTheme.typography.titleMedium, color = c.text)
                    Spacer(Modifier.height(10.dp))
                    val opts = listOf(false to (ui.selectedPlant?.displayName ?: "My plant"), true to "The tent")
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        opts.forEachIndexed { i, (v, label) ->
                            SegmentedButton(selected = forTent == v, onClick = { forTent = v }, shape = SegmentedButtonDefaults.itemShape(i, opts.size),
                                colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                                icon = {}) { Text(label, maxLines = 1) }
                        }
                    }
                }
            }
            GrowCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Has a due date", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                    Switch(checked = hasDue, onCheckedChange = { hasDue = it })
                }
                if (hasDue) {
                    Spacer(Modifier.height(8.dp))
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable { showPicker = true }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Due", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
                        Text(Formatting.abbrevDate(due), style = MaterialTheme.typography.bodyLarge, color = c.brand)
                    }
                }
            }
        }
    }
    if (showPicker) {
        val state = rememberDatePickerState(initialSelectedDateMillis = due.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
        DatePickerDialog(
            onDismissRequest = { showPicker = false },
            confirmButton = { TextButton(onClick = { state.selectedDateMillis?.let { due = Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate() }; showPicker = false }) { Text("OK") } },
            dismissButton = { TextButton(onClick = { showPicker = false }) { Text("Cancel") } },
        ) { DatePicker(state = state) }
    }
    ErrorDialog(error) { error = null }
}

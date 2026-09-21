package com.growop.app.ui.settings

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Formatting
import com.growop.app.data.GrowProfile
import com.growop.app.data.Plant
import com.growop.app.state.AppState
import com.growop.app.ui.shared.ConfirmDialog
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset

@Composable
private fun DateRow(label: String, date: LocalDate, onPick: () -> Unit) {
    val c = GrowTheme.colors
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(onClick = onPick).padding(vertical = 10.dp, horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
        Text(Formatting.abbrevDate(date), style = MaterialTheme.typography.bodyLarge, color = c.brand)
    }
}

@Composable
private fun DatePickerFor(date: LocalDate, onDismiss: () -> Unit, onPicked: (LocalDate) -> Unit) {
    val state = rememberDatePickerState(initialSelectedDateMillis = date.atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli())
    DatePickerDialog(
        onDismissRequest = onDismiss,
        confirmButton = { TextButton(onClick = { state.selectedDateMillis?.let { onPicked(Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate()) }; onDismiss() }) { Text("OK") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel") } },
    ) { DatePicker(state = state) }
}

// MARK: - Edit one plant

@Composable
fun PlantEditScreen(app: AppState, plant: Plant, onBack: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf(plant.name ?: "") }
    var owner by remember { mutableStateOf(plant.owner ?: "") }
    var strain by remember { mutableStateOf(plant.strain ?: "") }
    var breeder by remember { mutableStateOf(plant.breeder ?: "") }
    var seedType by remember { mutableStateOf(plant.seedType ?: "") }
    var medium by remember { mutableStateOf(plant.medium ?: "soil") }
    var potSize by remember { mutableStateOf(plant.potSizeL?.let { Formatting.number(it, 1) } ?: "") }
    var hasStartDate by remember { mutableStateOf(Formatting.parseDay(plant.startDate) != null) }
    var startDate by remember { mutableStateOf(Formatting.parseDay(plant.startDate) ?: LocalDate.now()) }
    var showDate by remember { mutableStateOf(false) }
    var notes by remember { mutableStateOf(plant.notes ?: "") }
    var notifyService by remember { mutableStateOf(plant.notifyService ?: "") }
    var saving by remember { mutableStateOf(false) }
    var confirmDelete by remember { mutableStateOf(false) }
    var alertTitle by remember { mutableStateOf("Something went wrong") }
    var alertMessage by remember { mutableStateOf<String?>(null) }

    val notifyOptions = (ui.settings?.notifyServicesAvailable ?: emptyList()).toMutableList().apply { if (notifyService.isNotEmpty() && notifyService !in this) add(notifyService) }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text(plant.displayName, style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            SectionHeader("Plant")
            GrowCard {
                LabeledField("Name", name, { name = it }, placeholder = "e.g. Dad's plant")
                LabeledField("Who looks after it", owner, { owner = it }, placeholder = "e.g. Dad")
            }
            SectionHeader("Genetics")
            GrowCard {
                LabeledField("Strain", strain, { strain = it })
                LabeledField("Breeder", breeder, { breeder = it })
                LabeledField("Seed type", seedType, { seedType = it }, placeholder = "e.g. feminized photoperiod")
            }
            SectionHeader("Growing")
            GrowCard {
                PickerRow("Medium", Formatting.capitalize(medium), GrowProfile.mediums.map { it to Formatting.capitalize(it) }) { medium = it }
                LabeledField("Pot size", potSize, { potSize = it }, placeholder = "11", numeric = true, suffix = "L")
                SwitchRow("Start date known", hasStartDate) { hasStartDate = it }
                if (hasStartDate) DateRow("Start date", startDate) { showDate = true }
                LabeledField("Notes", notes, { notes = it }, minLines = 2, maxLines = 5)
            }
            SectionHeader("Notifications")
            GrowCard {
                PickerRow("Notifications", if (notifyService.isEmpty()) "Tent default" else notifyService.removePrefix("notify."),
                    listOf("" to "Tent default") + notifyOptions.map { it to it.removePrefix("notify.") }) { notifyService = it }
            }
            Footnote("Where alerts about this plant go. \"Tent default\" uses the phone chosen in Preferences.")
            GrowCard {
                ActionRow("Save plant", loading = saving, enabled = name.isNotBlank()) {
                    scope.launch {
                        saving = true
                        try {
                            val body = buildJsonObject {
                                put("name", name.trim()); put("owner", owner.trim())
                                put("strain", strain); put("breeder", breeder); put("seed_type", seedType)
                                put("medium", medium); put("notes", notes)
                                if (hasStartDate) put("start_date", Formatting.dayString(startDate)) else put("start_date", JsonNull)
                                if (notifyService.isEmpty()) put("notify_service", JsonNull) else put("notify_service", notifyService)
                                val ps = potSize.replace(',', '.').trim().toDoubleOrNull()
                                if (ps != null) put("pot_size_l", ps) else put("pot_size_l", JsonNull)
                            }
                            app.updatePlant(plant.id, body); app.refreshStatus(); onBack()
                        } catch (e: Throwable) { alertTitle = "Couldn't save"; alertMessage = ApiError.wrap(e).message } finally { saving = false }
                    }
                }
                ActionRow("Remove plant", destructive = true, enabled = !saving) { confirmDelete = true }
            }
            Spacer(Modifier.height(32.dp))
        }
    }
    if (showDate) DatePickerFor(startDate, onDismiss = { showDate = false }) { startDate = it }
    if (confirmDelete) ConfirmDialog("Remove ${plant.displayName}?", "Its history is kept, but it disappears from the app.", "Remove plant", destructive = true,
        onConfirm = {
            scope.launch {
                try { app.deletePlant(plant.id); app.refreshStatus(); onBack() } catch (e: Throwable) { alertTitle = "Couldn't remove the plant"; alertMessage = ApiError.wrap(e).message }
            }
        }, onDismiss = { confirmDelete = false })
    ErrorDialog(alertMessage, title = alertTitle) { alertMessage = null }
}

// MARK: - Add a plant

@Composable
fun AddPlantScreen(app: AppState, onBack: () -> Unit) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    var name by remember { mutableStateOf("") }
    var owner by remember { mutableStateOf("") }
    var strain by remember { mutableStateOf("") }
    var hasStartDate by remember { mutableStateOf(true) }
    var startDate by remember { mutableStateOf(LocalDate.now()) }
    var showDate by remember { mutableStateOf(false) }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("New plant", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Cancel") } },
                actions = {
                    TextButton(enabled = !saving && name.isNotBlank(), onClick = {
                        scope.launch {
                            saving = true
                            try {
                                val body = buildJsonObject {
                                    put("name", name.trim())
                                    owner.trim().takeIf { it.isNotEmpty() }?.let { put("owner", it) }
                                    strain.trim().takeIf { it.isNotEmpty() }?.let { put("strain", it) }
                                    if (hasStartDate) put("start_date", Formatting.dayString(startDate))
                                }
                                app.createPlant(body); app.refreshStatus(); onBack()
                            } catch (e: Throwable) { error = ApiError.wrap(e).message } finally { saving = false }
                        }
                    }) { Text(if (saving) "Adding…" else "Add", style = MaterialTheme.typography.titleMedium) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            SectionHeader("Plant")
            GrowCard {
                LabeledField("Name", name, { name = it }, placeholder = "e.g. Dad's plant")
                LabeledField("Who looks after it", owner, { owner = it }, placeholder = "e.g. Dad")
                LabeledField("Strain (optional)", strain, { strain = it })
            }
            GrowCard {
                SwitchRow("Start date known", hasStartDate) { hasStartDate = it }
                if (hasStartDate) DateRow("Start date", startDate) { showDate = true }
            }
            Footnote("The day it was germinated or planted. You can change everything else later.")
            Spacer(Modifier.height(32.dp))
        }
    }
    if (showDate) DatePickerFor(startDate, onDismiss = { showDate = false }) { startDate = it }
    ErrorDialog(error, title = "Couldn't add the plant") { error = null }
}

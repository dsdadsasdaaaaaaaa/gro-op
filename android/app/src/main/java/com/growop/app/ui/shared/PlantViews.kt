package com.growop.app.ui.shared

import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.outlined.Circle
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.growop.app.data.ApiError
import com.growop.app.state.AppState
import com.growop.app.state.AppUi
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// MARK: - Segmented plant switcher (Home, Log, Photos, Tasks)

@Composable
fun PlantSwitcher(ui: AppUi, app: AppState, modifier: Modifier = Modifier) {
    if (ui.plants.size < 2) return
    val c = GrowTheme.colors
    SingleChoiceSegmentedButtonRow(modifier.fillMaxWidth()) {
        ui.plants.forEachIndexed { i, p ->
            SegmentedButton(
                selected = p.id == (ui.selectedPlantId ?: ui.plants.first().id),
                onClick = { app.selectPlant(p.id) },
                shape = SegmentedButtonDefaults.itemShape(index = i, count = ui.plants.size),
                colors = SegmentedButtonDefaults.colors(
                    activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand,
                    inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary,
                    activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track,
                ),
                icon = {},
            ) {
                Text(p.shortName, style = MaterialTheme.typography.labelLarge)
            }
        }
    }
}

// MARK: - "Which plant is yours?"

@Composable
fun PlantChoiceScreen(ui: AppUi, app: AppState, onDone: () -> Unit) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    var selection by remember { mutableStateOf<Int?>(null) }
    var newName by remember { mutableStateOf("") }
    var newOwner by remember { mutableStateOf("") }
    var saving by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val canAddAnother = ui.plants.size < 2

    LaunchedEffect(Unit) {
        if (ui.plants.isEmpty()) app.loadPlants()
        selection = app.value.myPlantId   // nothing pre-picked: on a new phone, "yours" must be a choice
    }
    // Back means "not now", not "close the app".
    BackHandler { app.dismissPlantChoice(); onDone() }

    Column(
        Modifier.fillMaxSize().background(c.bg).statusBarsPadding().navigationBarsPadding().verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing),
        verticalArrangement = Arrangement.spacedBy(GrowTheme.sectionSpacing),
    ) {
        Column(Modifier.fillMaxWidth().padding(top = 12.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(84.dp).background(c.brand.copy(alpha = 0.12f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Eco, contentDescription = null, tint = c.brand, modifier = Modifier.size(40.dp))
            }
            Text("Which plant is yours?", style = MaterialTheme.typography.headlineMedium, color = c.text, textAlign = TextAlign.Center)
            Text("The tent is shared. Each of you looks after one plant, and the app opens on yours.",
                style = MaterialTheme.typography.bodyMedium, color = c.textSecondary, textAlign = TextAlign.Center)
        }

        if (ui.plants.isEmpty()) {
            Text("No plants yet — add yours below.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ui.plants.forEach { p ->
                    val sel = selection == p.id
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(GrowTheme.radius)).background(c.card)
                            .border(2.dp, if (sel) c.brand else Color.Transparent, RoundedCornerShape(GrowTheme.radius))
                            .clickable { selection = p.id }.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Icon(if (sel) Icons.Filled.CheckCircle else Icons.Outlined.Circle, contentDescription = null,
                            tint = if (sel) c.brand else c.textTertiary, modifier = Modifier.size(28.dp))
                        Spacer(Modifier.width(12.dp))
                        Column(Modifier.weight(1f)) {
                            Text(p.displayName, style = MaterialTheme.typography.titleMedium, color = c.text)
                            if (!p.owner.isNullOrBlank()) Text("Looked after by ${p.owner}", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                        p.dayTotal?.let { Text("Day $it", style = MaterialTheme.typography.labelLarge, color = c.textSecondary) }
                    }
                }
            }
        }

        if (canAddAnother) {
            GrowCard {
                Text(if (ui.plants.isEmpty()) "Add your plant" else "Add the second plant", style = MaterialTheme.typography.titleMedium, color = c.text)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(value = newName, onValueChange = { newName = it }, label = { Text("Plant name (e.g. Dad's plant)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(value = newOwner, onValueChange = { newOwner = it }, label = { Text("Who looks after it (e.g. Dad)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Spacer(Modifier.height(12.dp))
                BigButton("Add plant", filled = false, loading = saving, enabled = newName.isNotBlank()) {
                    scope.launch {
                        saving = true
                        try {
                            val fields = buildJsonObject {
                                put("name", newName.trim())
                                if (newOwner.isNotBlank()) put("owner", newOwner.trim())
                            }
                            val p = app.createPlant(fields)
                            newName = ""; newOwner = ""
                            if (selection == null) selection = p.id
                        } catch (e: Throwable) {
                            error = ApiError.wrap(e).message
                        } finally { saving = false }
                    }
                }
            }
        }

        BigButton("This one is mine", enabled = selection != null) {
            selection?.let { app.setMyPlant(it) }
            app.dismissPlantChoice()
            onDone()
        }
        TextButton(onClick = { app.dismissPlantChoice(); onDone() }, modifier = Modifier.fillMaxWidth()) {
            Text("Skip for now", color = c.textSecondary, style = MaterialTheme.typography.labelLarge)
        }
        Spacer(Modifier.height(24.dp))
    }
    ErrorDialog(error, title = "Couldn't add the plant") { error = null }
}

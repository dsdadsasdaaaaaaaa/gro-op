package com.growop.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.ConnectionMode
import com.growop.app.data.ServerConfig
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch

@Composable
fun ConnectionModeToggle(mode: ConnectionMode, onChange: (ConnectionMode) -> Unit, modifier: Modifier = Modifier) {
    val c = GrowTheme.colors
    val modes = ConnectionMode.entries
    SingleChoiceSegmentedButtonRow(modifier.fillMaxWidth()) {
        modes.forEachIndexed { i, m ->
            SegmentedButton(
                selected = mode == m,
                onClick = { onChange(m) },
                shape = SegmentedButtonDefaults.itemShape(index = i, count = modes.size),
                colors = SegmentedButtonDefaults.colors(
                    activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand,
                    inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary,
                    activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track,
                ),
                icon = {},
            ) { Text(m.title, style = MaterialTheme.typography.labelMedium, maxLines = 1) }
        }
    }
}

/** The connection form shared by onboarding and Settings. */
@Composable
fun ServerFields(
    mode: ConnectionMode,
    url: String, onUrl: (String) -> Unit,
    haUrl: String, onHaUrl: (String) -> Unit,
    haToken: String, onHaToken: (String) -> Unit,
    apiKey: String, onApiKey: (String) -> Unit,
) {
    val c = GrowTheme.colors
    val urlKeyboard = KeyboardOptions(keyboardType = KeyboardType.Uri, capitalization = KeyboardCapitalization.None, autoCorrect = false)
    val plainKeyboard = KeyboardOptions(keyboardType = KeyboardType.Password, capitalization = KeyboardCapitalization.None, autoCorrect = false)
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (mode == ConnectionMode.DIRECT) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Server address", style = MaterialTheme.typography.titleSmall, color = c.text)
                OutlinedTextField(value = url, onValueChange = onUrl, placeholder = { Text(ServerConfig.DEFAULT_URL) },
                    singleLine = true, keyboardOptions = urlKeyboard, modifier = Modifier.fillMaxWidth())
            }
        } else {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Home Assistant URL", style = MaterialTheme.typography.titleSmall, color = c.text)
                OutlinedTextField(value = haUrl, onValueChange = onHaUrl, placeholder = { Text("https://….ui.nabu.casa") },
                    singleLine = true, keyboardOptions = urlKeyboard, modifier = Modifier.fillMaxWidth())
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("Home Assistant access token", style = MaterialTheme.typography.titleSmall, color = c.text)
                OutlinedTextField(value = haToken, onValueChange = onHaToken, placeholder = { Text("Paste the token here") },
                    singleLine = true, keyboardOptions = plainKeyboard, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                Text("Home Assistant → your profile (bottom left) → Security → Create token", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("Grow Brain API key", style = MaterialTheme.typography.titleSmall, color = c.text)
            OutlinedTextField(value = apiKey, onValueChange = onApiKey, placeholder = { Text("Paste the key here") },
                singleLine = true, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii, capitalization = KeyboardCapitalization.None, autoCorrect = false),
                modifier = Modifier.fillMaxWidth())
        }
    }
}

@Composable
fun OnboardingScreen(app: AppState) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    val saved = app.value.config
    var mode by remember { mutableStateOf(saved.mode) }
    var url by remember { mutableStateOf(saved.baseUrl.ifEmpty { ServerConfig.DEFAULT_URL }) }
    var haUrl by remember { mutableStateOf(saved.haUrl) }
    var haToken by remember { mutableStateOf(saved.haToken) }
    var apiKey by remember { mutableStateOf(saved.apiKey) }
    var connecting by remember { mutableStateOf(false) }
    var errorText by remember { mutableStateOf<String?>(null) }
    val prefill by app.prefill.collectAsStateWithLifecycle()
    LaunchedEffect(prefill) {
        if (prefill.isEmpty()) return@LaunchedEffect
        prefill["url"]?.let { url = it }
        prefill["apiKey"]?.let { apiKey = it }
        prefill["haURL"]?.let { haUrl = it; mode = ConnectionMode.HOME_ASSISTANT }
        prefill["haToken"]?.let { haToken = it }
        if (prefill["haURL"] == null) mode = ConnectionMode.DIRECT
    }

    val candidate = ServerConfig(mode = mode, baseUrl = url, apiKey = apiKey, haUrl = haUrl, haToken = haToken)

    Column(
        Modifier.fillMaxSize().background(c.bg).statusBarsPadding().navigationBarsPadding().verticalScroll(rememberScrollState()).imePadding()
            .padding(horizontal = GrowTheme.spacing),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(24.dp),
    ) {
        Spacer(Modifier.height(24.dp))
        Icon(Icons.Filled.Eco, contentDescription = null, tint = c.brand, modifier = Modifier.size(84.dp))
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Connect to your grow brain", style = MaterialTheme.typography.headlineLarge, color = c.text, textAlign = TextAlign.Center)
            Text(
                if (mode == ConnectionMode.DIRECT)
                    "Enter the address of the grow brain on your home network and the API key it was set up with. You only need to do this once."
                else "Connect through Home Assistant so the app works even when you're away from home.",
                style = MaterialTheme.typography.bodyMedium, color = c.textSecondary, textAlign = TextAlign.Center,
            )
        }
        ConnectionModeToggle(mode, onChange = { mode = it; errorText = null })
        ServerFields(mode, url, { url = it }, haUrl, { haUrl = it }, haToken, { haToken = it }, apiKey, { apiKey = it })
        errorText?.let { msg ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                Icon(Icons.Filled.Warning, contentDescription = null, tint = c.alert, modifier = Modifier.size(20.dp))
                Spacer(Modifier.width(8.dp))
                Text(msg, style = MaterialTheme.typography.bodyMedium, color = c.alert)
            }
        }
        BigButton(if (connecting) "Connecting…" else "Connect", loading = connecting, enabled = candidate.isConfigured) {
            scope.launch {
                connecting = true; errorText = null
                try { app.connect(candidate) } catch (e: Throwable) { errorText = ApiError.wrap(e).message } finally { connecting = false }
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

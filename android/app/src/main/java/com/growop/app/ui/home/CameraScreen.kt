package com.growop.app.ui.home

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.DarkMode
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.VideocamOff
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
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
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import coil3.compose.AsyncImage
import com.growop.app.PhotoImage
import com.growop.app.data.ApiError
import com.growop.app.data.CameraFrame
import com.growop.app.data.CameraInfo
import com.growop.app.data.Formatting
import com.growop.app.data.Photo
import com.growop.app.state.AppState
import com.growop.app.ui.photos.PhotoAnalysisView
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.EmptyStateView
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.WorkingView
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs
import kotlin.math.roundToInt

private val clockFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm:ss", Locale.US)
private val frameFmt: DateTimeFormatter = DateTimeFormatter.ofPattern("EEE MMM d, HH:mm", Locale.getDefault())

/** Polls the live snapshot every [periodMs] while this composable is visible and the app is started. */
@Composable
private fun SnapshotPoller(app: AppState, periodMs: Long) {
    val owner = LocalLifecycleOwner.current
    LaunchedEffect(owner, periodMs) {
        owner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (isActive) {
                app.refreshCameraSnapshot()
                delay(periodMs)
            }
        }
    }
}

// MARK: - Live image (shared by the Home card and CameraScreen)

@Composable
fun CameraImageView(image: ImageBitmap?, error: String?, at: Instant?, modifier: Modifier = Modifier, showLive: Boolean = true, muted: Boolean = false) {
    val c = GrowTheme.colors
    Box(modifier.background(c.night), contentAlignment = Alignment.Center) {
        if (image != null) {
            Image(image, contentDescription = "Live tent camera", contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize().graphicsLayer { alpha = if (muted) 0.55f else 1f })
        } else {
            Column(Modifier.padding(16.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Icon(if (error == null) Icons.Filled.Videocam else Icons.Filled.VideocamOff, contentDescription = null, tint = Color.White.copy(alpha = 0.8f), modifier = Modifier.size(32.dp))
                Text(error ?: "Waiting for the camera…", style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.8f), textAlign = TextAlign.Center, maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
        }
        if (image != null && showLive) {
            Row(
                Modifier.align(Alignment.BottomStart).padding(8.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.45f)).padding(horizontal = 8.dp, vertical = 5.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Box(Modifier.size(6.dp).background(if (error == null) c.alert else c.warn, CircleShape))
                Spacer(Modifier.width(6.dp))
                Text(
                    if (error == null) "live · ${at?.atZone(ZoneId.systemDefault())?.format(clockFmt) ?: ""}" else "reconnecting…",
                    style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace), color = Color.White,
                )
            }
        }
    }
}

// MARK: - Home card

@Composable
fun CameraCard(app: AppState, camera: CameraInfo, muted: Boolean, onClick: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val error = ui.cameraError ?: if (camera.available == false) (camera.error ?: "Camera unavailable") else null
    SnapshotPoller(app, 3000)
    GrowCard(padding = 16.dp, onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Videocam, contentDescription = null, tint = c.text, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text("Tent camera", style = MaterialTheme.typography.titleMedium, color = c.text)
            Spacer(Modifier.weight(1f))
            Text(camera.displayName, style = MaterialTheme.typography.bodySmall, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(end = 4.dp))
            Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = c.textTertiary)
        }
        Spacer(Modifier.height(10.dp))
        CameraImageView(ui.cameraImage, error, ui.cameraImageAt, Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(14.dp)), muted = muted)
    }
}

// MARK: - Full camera screen

private sealed class LookState {
    object Idle : LookState()
    object Running : LookState()
    class Done(val photo: Photo) : LookState()
    class Failed(val message: String) : LookState()
}

@Composable
fun CameraScreen(app: AppState, onBack: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var mode by remember { mutableStateOf("live") }
    var look by remember { mutableStateOf<LookState>(LookState.Idle) }
    val cam = ui.status?.camera

    fun runLook() {
        look = LookState.Running
        scope.launch {
            look = try { LookState.Done(app.analyseCamera()) } catch (e: Throwable) { LookState.Failed(ApiError.wrap(e).message) }
        }
    }

    val done = look as? LookState.Done
    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text(if (done != null) "What the advisor saw" else (cam?.displayName ?: "Tent camera"), style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                navigationIcon = { IconButton(onClick = { if (done != null) look = LookState.Idle else onBack() }) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
            if (done != null) {
                Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(14.dp)).background(c.night), contentAlignment = Alignment.Center) {
                    AsyncImage(model = PhotoImage(done.photo.id, thumb = false), contentDescription = null, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxSize())
                }
                PhotoAnalysisView(done.photo.analysis)
                BigButton("Done") { look = LookState.Idle }
                Spacer(Modifier.height(24.dp))
            } else {
                val modes = listOf("live" to "Live", "timelapse" to "Timelapse")
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    modes.forEachIndexed { i, (k, label) ->
                        SegmentedButton(selected = mode == k, onClick = { mode = k }, shape = SegmentedButtonDefaults.itemShape(i, modes.size),
                            colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                            icon = {}) { Text(label, style = MaterialTheme.typography.labelLarge) }
                    }
                }
                if (mode == "live") LiveSection(app, cam, onLook = { runLook() }) else TimelapseView(app)
                Spacer(Modifier.height(24.dp))
            }
        }
    }

    when (val l = look) {
        is LookState.Running -> Dialog(onDismissRequest = {}, properties = DialogProperties(dismissOnBackPress = false, dismissOnClickOutside = false)) {
            Box(Modifier.clip(RoundedCornerShape(GrowTheme.radius)).background(c.card)) {
                WorkingView("The advisor is looking at the tent…", "Taking a fresh snapshot and checking ${ui.selectedPlant?.displayName ?: "the tent"}. This can take up to a minute.")
            }
        }
        is LookState.Failed -> AlertDialog(
            onDismissRequest = { look = LookState.Idle },
            containerColor = c.card,
            icon = { Icon(Icons.Filled.VideocamOff, contentDescription = null, tint = c.warn) },
            title = { Text("Couldn't look right now") },
            text = { Text(l.message) },
            confirmButton = { TextButton(onClick = { runLook() }) { Text("Try again", color = c.brand) } },
            dismissButton = { TextButton(onClick = { look = LookState.Idle }) { Text("Close", color = c.textSecondary) } },
        )
        else -> {}
    }
}

@Composable
private fun LiveSection(app: AppState, cam: CameraInfo?, onLook: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    var zoom by remember { mutableStateOf(1f) }
    val img = ui.cameraImage
    val aspect = if (img != null && img.height > 0) img.width.toFloat() / img.height else 16f / 9f
    SnapshotPoller(app, 1000)
    Column(verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
        Box(
            Modifier.fillMaxWidth().aspectRatio(aspect).clip(RoundedCornerShape(16.dp))
                .pointerInput(Unit) { detectTransformGestures { _, _, z, _ -> zoom = (zoom * z).coerceIn(1f, 4f) } }
                .pointerInput(Unit) { detectTapGestures(onDoubleTap = { zoom = 1f }) },
        ) {
            CameraImageView(img, ui.cameraError, ui.cameraImageAt, Modifier.fillMaxSize().graphicsLayer { scaleX = zoom; scaleY = zoom })
        }
        if (zoom > 1f) Text("Double-tap to reset zoom", style = MaterialTheme.typography.bodySmall, color = c.textTertiary, modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
        BigButton("Ask the advisor to look now", icon = Icons.Filled.AutoAwesome, onClick = onLook)
        ui.selectedPlant?.let { Text("It takes a fresh snapshot and checks ${it.displayName}.", style = MaterialTheme.typography.bodySmall, color = c.textSecondary) }
        if (cam != null) {
            val offline = cam.available == false
            GrowCard(padding = 16.dp) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(if (offline) Icons.Filled.Warning else Icons.Filled.CheckCircle, contentDescription = null, tint = if (offline) c.warn else c.good, modifier = Modifier.size(20.dp))
                    Spacer(Modifier.width(8.dp))
                    Text(if (offline) "Camera unavailable" else "Camera online", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.Medium), color = c.text)
                }
                cam.frameCount?.let { n ->
                    Spacer(Modifier.height(4.dp))
                    Text("$n timelapse frames saved" + (cam.lastFrameAt?.let { " · last ${Formatting.relative(it)}" } ?: ""), style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                }
                if (!cam.error.isNullOrEmpty()) { Spacer(Modifier.height(4.dp)); Text(cam.error, style = MaterialTheme.typography.bodySmall, color = c.warn) }
            }
        }
    }
}

// MARK: - Timelapse

@Composable
private fun TimelapseView(app: AppState) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    var days by remember { mutableStateOf(1) }
    var frames by remember { mutableStateOf<List<CameraFrame>>(emptyList()) }
    var index by remember { mutableStateOf(0) }
    var image by remember { mutableStateOf<ImageBitmap?>(null) }
    var loading by remember { mutableStateOf(false) }
    var playing by remember { mutableStateOf(false) }
    var playJob by remember { mutableStateOf<Job?>(null) }
    var prefetchJob by remember { mutableStateOf<Job?>(null) }

    val currentIndex = if (frames.isEmpty()) 0 else index.coerceIn(0, frames.size - 1)
    val current = frames.getOrNull(currentIndex)

    fun stopPlaying() { playJob?.cancel(); playJob = null; playing = false }
    fun prefetchAround(center: Int) {
        prefetchJob?.cancel()
        val ids = frames.withIndex().filter { abs(it.index - center) <= 12 }.sortedBy { abs(it.index - center) }.map { it.value.id }
        prefetchJob = scope.launch { for (id in ids) { if (!isActive) return@launch; app.frame(id) } }
    }
    suspend fun showCurrent() {
        val f = current ?: run { image = null; return }
        app.cachedFrame(f.id)?.let { image = it; return }
        val id = f.id
        val img = app.frame(id)
        if (frames.getOrNull(currentIndex)?.id == id && img != null) image = img
    }

    LaunchedEffect(days) {
        stopPlaying(); prefetchJob?.cancel()
        loading = true; image = null
        frames = app.cameraFrames(days)
        index = (frames.size - 1).coerceAtLeast(0)
        loading = false
        showCurrent()
        prefetchAround(currentIndex)
    }
    LaunchedEffect(currentIndex, frames.size) { if (!playing) showCurrent() }

    fun togglePlay() {
        if (playing) { stopPlaying(); return }
        if (frames.size < 2) return
        playing = true
        if (currentIndex >= frames.size - 1) index = 0
        playJob = scope.launch {
            while (isActive) {
                val next = currentIndex + 1
                if (next >= frames.size) break
                val img = app.frame(frames[next].id)
                if (!isActive) break
                index = next
                if (img != null) image = img
                delay(165)   // ~6 fps
            }
            playing = false
        }
    }

    GrowCard(padding = 16.dp) {
        val ranges = listOf(1 to "Last 24 h", 7 to "7 days")
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            ranges.forEachIndexed { i, (d, label) ->
                SegmentedButton(selected = days == d, onClick = { days = d }, shape = SegmentedButtonDefaults.itemShape(i, ranges.size),
                    colors = SegmentedButtonDefaults.colors(activeContainerColor = c.brand.copy(alpha = 0.16f), activeContentColor = c.brand, inactiveContainerColor = c.card, inactiveContentColor = c.textSecondary, activeBorderColor = c.brand.copy(alpha = 0.3f), inactiveBorderColor = c.track),
                    icon = {}) { Text(label, style = MaterialTheme.typography.labelLarge) }
            }
        }
        Spacer(Modifier.height(14.dp))
        Box(Modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(16.dp)).background(c.night), contentAlignment = Alignment.Center) {
            val img = image
            when {
                img != null -> Image(img, contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
                loading || frames.isNotEmpty() -> CircularProgressIndicator(color = Color.White, modifier = Modifier.size(32.dp), strokeWidth = 3.dp)
                else -> Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Icon(Icons.Filled.Videocam, contentDescription = null, tint = Color.White.copy(alpha = 0.8f), modifier = Modifier.size(32.dp))
                    Text("No frames yet", style = MaterialTheme.typography.bodySmall, color = Color.White.copy(alpha = 0.85f))
                    Text("The camera saves a frame every half hour.", style = MaterialTheme.typography.labelSmall, color = Color.White.copy(alpha = 0.7f))
                }
            }
            current?.let { f ->
                Row(
                    Modifier.align(Alignment.BottomStart).padding(10.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.45f)).padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(if (f.lightsOn == true) Icons.Filled.WbSunny else Icons.Filled.DarkMode, contentDescription = null, tint = if (f.lightsOn == true) c.sun else Color.White.copy(alpha = 0.85f), modifier = Modifier.size(14.dp))
                    Spacer(Modifier.width(6.dp))
                    val label = Formatting.parseISO(f.t)?.atZone(ZoneId.systemDefault())?.format(frameFmt) ?: (f.t ?: "")
                    Text(label, style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.SemiBold, fontFamily = FontFamily.Monospace), color = Color.White)
                }
            }
        }
        Spacer(Modifier.height(12.dp))
        val enabled = frames.size >= 2
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            IconButton(onClick = { togglePlay() }, enabled = enabled, modifier = Modifier.size(48.dp).background(if (enabled) c.brand else c.brand.copy(alpha = 0.35f), CircleShape)) {
                Icon(if (playing) Icons.Filled.Pause else Icons.Filled.PlayArrow, contentDescription = if (playing) "Pause" else "Play", tint = Color.White)
            }
            // Range is always valid (0..max(n-1,1)) so an empty timelapse can't produce a 0-length range.
            val maxIdx = (frames.size - 1).coerceAtLeast(1)
            Slider(
                value = currentIndex.toFloat(), onValueChange = { stopPlaying(); index = it.roundToInt().coerceIn(0, maxIdx) },
                valueRange = 0f..maxIdx.toFloat(), steps = (frames.size - 2).coerceAtLeast(0), enabled = enabled,
                colors = SliderDefaults.colors(thumbColor = c.brand, activeTrackColor = c.brand, inactiveTrackColor = c.track, activeTickColor = Color.Transparent, inactiveTickColor = Color.Transparent),
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(if (frames.isEmpty()) "" else "Frame ${currentIndex + 1} of ${frames.size}", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            Spacer(Modifier.weight(1f))
            val first = frames.firstOrNull()?.t; val last = frames.lastOrNull()?.t
            if (first != null && last != null) Text("${Formatting.shortDateTime(first)} → ${Formatting.shortDateTime(last)}", style = MaterialTheme.typography.labelSmall, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

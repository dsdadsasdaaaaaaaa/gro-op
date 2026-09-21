package com.growop.app.ui.photos

import android.content.ActivityNotFoundException
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.heightIn
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
import androidx.compose.material.icons.automirrored.filled.HelpOutline
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil3.compose.AsyncImage
import com.growop.app.PhotoImage
import com.growop.app.data.ApiError
import com.growop.app.data.Formatting
import com.growop.app.data.ImageUtils
import com.growop.app.data.Photo
import com.growop.app.data.PhotoAnalysis
import com.growop.app.data.PhotoRequest
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.CreatedItemsView
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.shared.LevelColor
import com.growop.app.ui.shared.NumberedList
import com.growop.app.ui.shared.PlantSwitcher
import com.growop.app.ui.shared.SectionTitle
import com.growop.app.ui.shared.WorkingView
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/** A picked image waiting to be sent, optionally answering a request. */
class PendingPhoto(val jpeg: ByteArray, val preview: ImageBitmap, val request: PhotoRequest?)

@Composable
fun PhotosScreen(app: AppState) {
    var pending by remember { mutableStateOf<PendingPhoto?>(null) }
    var detailId by remember { mutableStateOf<Int?>(null) }
    BackHandler(enabled = pending != null || detailId != null) { pending = null; detailId = null }
    val p = pending
    val d = detailId
    when {
        p != null -> PhotoSubmitScreen(app, p) { pending = null }
        d != null -> PhotoDetailScreen(app, d) { detailId = null }
        else -> PhotosMain(app, onPending = { pending = it }, onOpen = { detailId = it })
    }
}

@Composable
private fun PhotosMain(app: AppState, onPending: (PendingPhoto) -> Unit, onOpen: (Int) -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var refreshing by remember { mutableStateOf(false) }
    var alertTitle by remember { mutableStateOf("Something went wrong") }
    var alertMessage by remember { mutableStateOf<String?>(null) }
    var skipping by remember { mutableStateOf<Int?>(null) }
    var preparing by remember { mutableStateOf(false) }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }
    var target by remember { mutableStateOf<PhotoRequest?>(null) }

    LaunchedEffect(Unit) { app.loadPhotoRequests(); app.loadPhotos() }

    fun loadPicked(uri: Uri, request: PhotoRequest?) {
        scope.launch {
            preparing = true
            val bytes = withContext(Dispatchers.IO) { runCatching { ImageUtils.prepareForUpload(context, uri) }.getOrNull() }
            val bmp = bytes?.let { withContext(Dispatchers.IO) { ImageUtils.decode(it) } }
            preparing = false
            if (bytes == null || bmp == null) { alertMessage = "Couldn't load that photo." } else onPending(PendingPhoto(bytes, bmp.asImageBitmap(), request))
        }
    }

    val takePicture = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok ->
        val uri = cameraUri
        if (ok && uri != null) loadPicked(uri, target)
        target = null
    }
    val pickMedia = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri != null) loadPicked(uri, target)
        target = null
    }

    fun startCamera(request: PhotoRequest?) {
        val dir = File(context.cacheDir, "camera").apply { mkdirs() }
        val file = File(dir, "capture_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        cameraUri = uri; target = request
        try { takePicture.launch(uri) } catch (e: ActivityNotFoundException) {
            alertTitle = "No camera"; alertMessage = "This phone has no camera app available. Use \"Choose\" to pick a photo instead."
        }
    }
    fun startLibrary(request: PhotoRequest?) {
        target = request
        pickMedia.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
    }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = { TopAppBar(title = { Text("Photos", style = MaterialTheme.typography.headlineMedium) }, colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text)) },
    ) { inner ->
        PullToRefreshBox(isRefreshing = refreshing, onRefresh = { scope.launch { refreshing = true; app.loadPhotoRequests(); app.loadPhotos(); refreshing = false } }, modifier = Modifier.fillMaxSize().padding(inner)) {
            Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                PlantSwitcher(ui, app)
                val requests = ui.openRequestsForSelected
                if (requests.isNotEmpty()) {
                    SectionTitle("The advisor wants to see")
                    requests.forEach { r ->
                        PhotoRequestCard(r, onTake = { startCamera(r) }, onChoose = { startLibrary(r) }, busy = skipping == r.id, onSkip = {
                            scope.launch { skipping = r.id; try { app.skipPhotoRequest(r.id) } catch (e: Throwable) { alertMessage = ApiError.wrap(e).message } finally { skipping = null } }
                        })
                    }
                }
                GrowCard {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.CameraAlt, contentDescription = null, tint = c.text, modifier = Modifier.size(22.dp))
                        Spacer(Modifier.width(8.dp))
                        Text("Send a photo", style = MaterialTheme.typography.titleLarge, color = c.text)
                    }
                    Spacer(Modifier.height(6.dp))
                    Text("Any photo of your plants — the advisor will check it over.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        BigButton("Take photo", modifier = Modifier.weight(1f), icon = Icons.Filled.CameraAlt) { startCamera(null) }
                        BigButton("Choose", modifier = Modifier.weight(1f), filled = false, icon = Icons.Filled.PhotoLibrary) { startLibrary(null) }
                    }
                }
                if (preparing) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = c.brand)
                        Spacer(Modifier.width(8.dp))
                        Text("Preparing photo…", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    }
                }
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    SectionTitle("Past photos")
                    val photos = ui.photosForSelected
                    if (photos.isEmpty()) Text("No photos yet.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    photos.chunked(3).forEach { row ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            row.forEach { p -> PhotoGridCell(p, Modifier.weight(1f)) { onOpen(p.id) } }
                            repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                        }
                    }
                }
                Spacer(Modifier.height(24.dp))
            }
        }
    }
    ErrorDialog(alertMessage, title = alertTitle) { alertMessage = null }
}

// MARK: - Request card

@Composable
fun PhotoRequestCard(request: PhotoRequest, onTake: () -> Unit, onChoose: () -> Unit, onSkip: () -> Unit, busy: Boolean) {
    val c = GrowTheme.colors
    GrowCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(30.dp).background(c.night.copy(alpha = 0.14f), CircleShape), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.CameraAlt, contentDescription = null, tint = c.night, modifier = Modifier.size(16.dp))
            }
            Spacer(Modifier.width(10.dp))
            Text(request.title ?: "Photo request", style = MaterialTheme.typography.titleLarge, color = c.text, modifier = Modifier.weight(1f))
            Text(Formatting.relative(request.createdAt), style = MaterialTheme.typography.bodySmall, color = c.textTertiary)
        }
        if (!request.instructions.isNullOrEmpty()) {
            Spacer(Modifier.height(10.dp))
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.brand.copy(alpha = 0.08f)).padding(14.dp), verticalAlignment = Alignment.Top) {
                Box(Modifier.width(4.dp).height(44.dp).background(c.brand, RoundedCornerShape(2.dp)))
                Spacer(Modifier.width(12.dp))
                Text(request.instructions, style = MaterialTheme.typography.bodyLarge, color = c.text)
            }
        }
        if (!request.reason.isNullOrEmpty()) {
            Spacer(Modifier.height(10.dp))
            Row(verticalAlignment = Alignment.Top) {
                Icon(Icons.AutoMirrored.Filled.HelpOutline, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text(request.reason, style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            BigButton("Take photo", modifier = Modifier.weight(1f), icon = Icons.Filled.CameraAlt, onClick = onTake)
            BigButton("Choose", modifier = Modifier.weight(1f), filled = false, icon = Icons.Filled.PhotoLibrary, onClick = onChoose)
        }
        TextButton(onClick = onSkip, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
            if (busy) { CircularProgressIndicator(Modifier.size(14.dp), strokeWidth = 2.dp, color = c.textSecondary); Spacer(Modifier.width(8.dp)) }
            Text("Skip this one", color = c.textSecondary, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

// MARK: - Grid cell

@Composable
private fun scoreColor(s: Double): Color = when {
    s >= 8 -> GrowTheme.colors.good
    s >= 5 -> GrowTheme.colors.warn
    else -> GrowTheme.colors.alert
}

@Composable
fun PhotoGridCell(photo: Photo, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = GrowTheme.colors
    Box(modifier.aspectRatio(1f).clip(RoundedCornerShape(14.dp)).background(c.track).clickable(onClick = onClick)) {
        AsyncImage(model = PhotoImage(photo.id, thumb = true), contentDescription = null, contentScale = ContentScale.Crop, modifier = Modifier.fillMaxSize())
        photo.analysis?.healthScore?.let { score ->
            Text(
                "${Formatting.number(score)}/10",
                style = MaterialTheme.typography.labelSmall.copy(fontWeight = FontWeight.Bold, fontSize = 11.sp), color = Color.White,
                modifier = Modifier.align(Alignment.BottomStart).padding(6.dp).clip(CircleShape).background(scoreColor(score)).padding(horizontal = 7.dp, vertical = 3.dp),
            )
        }
    }
}

// MARK: - Submit screen

@Composable
fun PhotoSubmitScreen(app: AppState, pending: PendingPhoto, onClose: () -> Unit) {
    val c = GrowTheme.colors
    val scope = rememberCoroutineScope()
    var note by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<Photo?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text(if (result == null) "Send photo" else "Analysis", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { if (result == null && !sending) IconButton(onClick = onClose) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Cancel") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Box(Modifier.fillMaxSize().padding(inner)) {
            when {
                sending -> WorkingView("Analyzing your photo…", "The advisor is looking closely. This can take up to a minute.", Modifier.padding(top = 60.dp))
                result != null -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Image(pending.preview, contentDescription = null, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxWidth().heightIn(max = 220.dp).clip(RoundedCornerShape(14.dp)))
                    PhotoAnalysisView(result!!.analysis)
                    BigButton("Done", onClick = onClose)
                    Spacer(Modifier.height(24.dp))
                }
                else -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).imePadding().padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Image(pending.preview, contentDescription = null, contentScale = ContentScale.Fit, modifier = Modifier.fillMaxWidth().heightIn(max = 320.dp).clip(RoundedCornerShape(14.dp)))
                    pending.request?.let { r ->
                        GrowCard {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Filled.CameraAlt, contentDescription = null, tint = c.text, modifier = Modifier.size(18.dp))
                                Spacer(Modifier.width(8.dp))
                                Text(r.title ?: "Photo request", style = MaterialTheme.typography.titleMedium, color = c.text)
                            }
                            if (!r.instructions.isNullOrEmpty()) { Spacer(Modifier.height(6.dp)); Text(r.instructions, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary) }
                        }
                    }
                    GrowCard {
                        Text("Note (optional)", style = MaterialTheme.typography.titleSmall, color = c.text)
                        Spacer(Modifier.height(6.dp))
                        OutlinedTextField(value = note, onValueChange = { note = it }, placeholder = { Text("Anything the advisor should know about this photo") }, minLines = 2, maxLines = 5, modifier = Modifier.fillMaxWidth())
                    }
                    BigButton("Send for analysis", icon = Icons.AutoMirrored.Filled.Send) {
                        scope.launch {
                            sending = true
                            try {
                                result = app.uploadPhoto(pending.jpeg, pending.request?.id, note.trim().ifEmpty { null }, pending.request?.plantId ?: app.value.selectedPlantId)
                            } catch (e: Throwable) { error = ApiError.wrap(e).message } finally { sending = false }
                        }
                    }
                    Spacer(Modifier.height(24.dp))
                }
            }
        }
    }
    ErrorDialog(error, title = "Couldn't send the photo") { error = null }
}

// MARK: - Analysis

@Composable
fun PhotoAnalysisView(analysis: PhotoAnalysis?) {
    val c = GrowTheme.colors
    if (analysis == null) {
        GrowCard { Text("No analysis available for this photo.", color = c.textSecondary) }
        return
    }
    GrowCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            analysis.healthScore?.let { s ->
                val sc = scoreColor(s)
                Column(Modifier.size(74.dp).background(sc.copy(alpha = 0.15f), CircleShape), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(Formatting.number(s), style = MaterialTheme.typography.displaySmall.copy(fontSize = 32.sp, lineHeight = 34.sp), color = sc)
                    Text("out of 10", style = MaterialTheme.typography.labelSmall, color = sc)
                }
                Spacer(Modifier.width(14.dp))
            }
            Text(analysis.summary ?: "No summary.", style = MaterialTheme.typography.bodyLarge, color = c.text, modifier = Modifier.weight(1f))
        }
    }
    val findings = analysis.findings
    if (!findings.isNullOrEmpty()) {
        GrowCard {
            Text("What the advisor saw", style = MaterialTheme.typography.titleSmall, color = c.text)
            Spacer(Modifier.height(10.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                findings.forEach { f ->
                    Row(verticalAlignment = Alignment.Top) {
                        Icon(LevelColor.icon(f.severity), contentDescription = null, tint = LevelColor.infoColor(f.severity), modifier = Modifier.size(20.dp))
                        Spacer(Modifier.width(10.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text(f.title ?: "", style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.Medium), color = c.text)
                                f.severity?.let { LevelChip(Formatting.capitalize(it), LevelColor.infoColor(it)) }
                            }
                            if (!f.detail.isNullOrEmpty()) Text(f.detail, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                    }
                }
            }
        }
    }
    val actions = analysis.actions
    if (!actions.isNullOrEmpty()) {
        GrowCard {
            Text("What to do", style = MaterialTheme.typography.titleSmall, color = c.text)
            Spacer(Modifier.height(8.dp))
            NumberedList(actions, color = c.brand)
        }
    }
    CreatedItemsView(analysis.tasks, analysis.photoRequests)
}

// MARK: - Detail

@Composable
fun PhotoDetailScreen(app: AppState, photoId: Int, onBack: () -> Unit) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val photo = ui.photos.firstOrNull { it.id == photoId }
    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("Photo", style = MaterialTheme.typography.titleLarge) },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text, navigationIconContentColor = c.text),
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).verticalScroll(rememberScrollState()).padding(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (photo == null) {
                Text("Photo not found", color = c.textSecondary)
            } else {
                Box(Modifier.fillMaxWidth().heightIn(min = 200.dp).clip(RoundedCornerShape(14.dp)).background(c.track), contentAlignment = Alignment.Center) {
                    AsyncImage(model = PhotoImage(photo.id, thumb = false), contentDescription = null, contentScale = ContentScale.FillWidth, modifier = Modifier.fillMaxWidth())
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(Formatting.shortDateTime(photo.createdAt), style = MaterialTheme.typography.bodySmall, color = c.textSecondary, modifier = Modifier.weight(1f))
                    if (photo.requestId != null) LevelChip("Requested by advisor", c.night)
                }
                if (!photo.note.isNullOrEmpty()) Text("Your note: ${photo.note}", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                PhotoAnalysisView(photo.analysis)
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

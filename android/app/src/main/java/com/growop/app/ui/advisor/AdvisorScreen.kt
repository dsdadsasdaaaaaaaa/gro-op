package com.growop.app.ui.advisor

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Eco
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Tune
import androidx.compose.material.icons.filled.Videocam
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
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
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.growop.app.data.ApiError
import com.growop.app.data.Brief
import com.growop.app.data.ChatMessage
import com.growop.app.data.Formatting
import com.growop.app.data.display
import com.growop.app.state.AppState
import com.growop.app.ui.shared.BigButton
import com.growop.app.ui.shared.BulletList
import com.growop.app.ui.shared.ConfirmDialog
import com.growop.app.ui.shared.CreatedItemsView
import com.growop.app.ui.shared.ErrorDialog
import com.growop.app.ui.shared.GrowCard
import com.growop.app.ui.shared.LevelChip
import com.growop.app.ui.shared.NumberedList
import com.growop.app.ui.theme.GrowTheme
import kotlinx.coroutines.launch

@Composable
fun AdvisorScreen(app: AppState) {
    val c = GrowTheme.colors
    val ui by app.ui.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()
    var draft by remember { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
    var runningBrief by remember { mutableStateOf(false) }
    var alertTitle by remember { mutableStateOf("Something went wrong") }
    var alertMessage by remember { mutableStateOf<String?>(null) }
    var confirmClear by remember { mutableStateOf(false) }
    var menuOpen by remember { mutableStateOf(false) }
    var aboutMenuOpen by remember { mutableStateOf(false) }
    // null = the whole tent. Until the person picks, a question is about the plant they're looking at.
    var aboutChosen by rememberSaveable { mutableStateOf(false) }
    var aboutPlantId by rememberSaveable { mutableStateOf<Int?>(null) }
    val currentAbout: Int? = if (aboutChosen) aboutPlantId else ui.selectedPlantId
    val aboutName = ui.plants.firstOrNull { it.id == currentAbout }?.displayName ?: "the whole tent"
    // Only jump to the end after this person sends something, so opening the tab shows the brief first.
    var followBottom by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val me = ui.myPlant?.owner
    fun isMine(m: ChatMessage): Boolean {
        if (!m.isUser) return false
        val author = m.author
        if (author.isNullOrBlank() || me.isNullOrBlank()) return true
        return author.equals(me, ignoreCase = true)
    }

    LaunchedEffect(Unit) {
        app.loadBrief(); app.loadChat(); app.markBriefRead()
    }
    LaunchedEffect(ui.brief?.id) { app.markBriefRead() }
    LaunchedEffect(ui.chatMessages.size, sending) {
        if (!followBottom) return@LaunchedEffect
        val count = listState.layoutInfo.totalItemsCount
        if (count > 0) listState.animateScrollToItem(count - 1)
    }

    fun send() {
        val text = draft.trim()
        if (text.isEmpty()) return
        draft = ""
        followBottom = true
        val about = currentAbout
        // The app's scope, not this screen's: leaving the tab mid-answer must not throw the answer away.
        app.launch {
            sending = true
            try { app.sendChat(text, about) } catch (e: Throwable) {
                draft = text; alertTitle = "Message not sent"; alertMessage = ApiError.wrap(e).message
            } finally { sending = false }
        }
    }

    Scaffold(
        containerColor = c.bg,
        contentWindowInsets = WindowInsets(0, 0, 0, 0),
        topBar = {
            TopAppBar(
                title = { Text("Advisor", style = MaterialTheme.typography.headlineMedium) },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = c.bg, titleContentColor = c.text),
                actions = {
                    IconButton(onClick = { menuOpen = true }) { Icon(Icons.Filled.MoreVert, contentDescription = "More", tint = c.textSecondary) }
                    DropdownMenu(expanded = menuOpen, onDismissRequest = { menuOpen = false }) {
                        DropdownMenuItem(text = { Text("Refresh") }, leadingIcon = { Icon(Icons.Filled.Refresh, null) },
                            onClick = { menuOpen = false; scope.launch { app.loadChat(); app.loadBrief() } })
                        DropdownMenuItem(text = { Text("Clear chat", color = c.alert) }, leadingIcon = { Icon(Icons.Filled.Delete, null, tint = c.alert) },
                            onClick = { menuOpen = false; confirmClear = true })
                    }
                },
            )
        },
    ) { inner ->
        Column(Modifier.fillMaxSize().padding(inner).imePadding()) {
            LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = listState, contentPadding = PaddingValues(GrowTheme.spacing), verticalArrangement = Arrangement.spacedBy(GrowTheme.spacing)) {
                item {
                    val b = ui.brief
                    if (b != null) BriefCard(b) else GrowCard {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.AutoAwesome, contentDescription = null, tint = c.night, modifier = Modifier.size(20.dp))
                            Spacer(Modifier.width(10.dp))
                            Text("No daily brief yet", style = MaterialTheme.typography.titleMedium, color = c.text)
                        }
                        Spacer(Modifier.height(6.dp))
                        Text("The advisor writes a short report each morning. You can ask for one now.", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    }
                }
                item {
                    BigButton(if (runningBrief) "Writing your brief… (up to a minute)" else "Write a brief now (≈ \$0.10)", filled = false, loading = runningBrief, icon = Icons.Filled.AutoAwesome) {
                        app.launch {
                            runningBrief = true
                            try { app.runBrief(); app.markBriefRead() } catch (e: Throwable) { alertTitle = "Couldn't run the brief"; alertMessage = ApiError.wrap(e).message } finally { runningBrief = false }
                        }
                    }
                }
                item {
                    Text("Ask the advisor", style = MaterialTheme.typography.titleMedium, color = c.text, modifier = Modifier.padding(top = 8.dp))
                    if (ui.chatMessages.isEmpty() && !sending) {
                        Spacer(Modifier.height(6.dp))
                        Text("Anything about your plant — watering, feeding, what a leaf looks like, when to flip to flower…", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                    }
                }
                items(ui.chatMessages, key = { it.id }) { m -> ChatBubble(m, mine = isMine(m)) }
                if (sending) {
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            LeafGlyph()
                            Spacer(Modifier.width(10.dp))
                            CircularProgressIndicator(Modifier.size(16.dp), strokeWidth = 2.dp, color = c.brand)
                            Spacer(Modifier.width(8.dp))
                            Text("Thinking…", style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                    }
                }
                item { Spacer(Modifier.height(4.dp)) }
            }
            // Input bar
            Column(Modifier.fillMaxWidth().background(c.bg).padding(horizontal = GrowTheme.spacing, vertical = 10.dp)) {
                if (ui.plants.isNotEmpty()) {
                    Box {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.clip(RoundedCornerShape(8.dp)).clickable { aboutMenuOpen = true }.padding(horizontal = 6.dp, vertical = 8.dp),
                        ) {
                            Icon(if (currentAbout == null) Icons.Filled.Home else Icons.Filled.Eco, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(14.dp))
                            Spacer(Modifier.width(4.dp))
                            Text("About: $aboutName", style = MaterialTheme.typography.labelMedium, color = c.textSecondary)
                            Icon(Icons.Filled.ExpandMore, contentDescription = "Change", tint = c.textSecondary, modifier = Modifier.size(16.dp))
                        }
                        DropdownMenu(expanded = aboutMenuOpen, onDismissRequest = { aboutMenuOpen = false }) {
                            DropdownMenuItem(text = { Text("The whole tent") }, leadingIcon = { Icon(Icons.Filled.Home, null) },
                                onClick = { aboutPlantId = null; aboutChosen = true; aboutMenuOpen = false })
                            ui.plants.forEach { p ->
                                DropdownMenuItem(text = { Text(p.displayName) }, leadingIcon = { Icon(Icons.Filled.Eco, null) },
                                    onClick = { aboutPlantId = p.id; aboutChosen = true; aboutMenuOpen = false })
                            }
                        }
                    }
                }
                Row(verticalAlignment = Alignment.Bottom) {
                    OutlinedTextField(
                        value = draft, onValueChange = { draft = it },
                        placeholder = { Text("Ask the advisor…") },
                        enabled = !sending, maxLines = 5,
                        shape = RoundedCornerShape(22.dp),
                        colors = OutlinedTextFieldDefaults.colors(focusedContainerColor = c.card, unfocusedContainerColor = c.card, focusedBorderColor = c.brand.copy(alpha = 0.5f), unfocusedBorderColor = c.track),
                        modifier = Modifier.weight(1f),
                    )
                    Spacer(Modifier.width(10.dp))
                    val canSend = !sending && draft.isNotBlank()
                    Box(
                        Modifier.padding(bottom = 6.dp).size(44.dp).background(if (canSend) c.brand else c.textSecondary.copy(alpha = 0.3f), CircleShape).clickable(enabled = canSend) { send() },
                        contentAlignment = Alignment.Center,
                    ) { Icon(Icons.Filled.ArrowUpward, contentDescription = "Send", tint = Color.White) }
                }
            }
        }
    }

    if (confirmClear) ConfirmDialog("Clear the chat for both of you?", "Everyone who uses the tent shares this chat.", "Clear it", destructive = true,
        onConfirm = { scope.launch { try { app.clearChat() } catch (e: Throwable) { alertMessage = ApiError.wrap(e).message } } },
        onDismiss = { confirmClear = false })
    ErrorDialog(alertMessage, title = alertTitle) { alertMessage = null }
}

// MARK: - Brief card

@Composable
fun BriefCard(brief: Brief) {
    val c = GrowTheme.colors
    var showConcerns by remember { mutableStateOf(true) }
    var showActions by remember { mutableStateOf(true) }
    var showTargets by remember { mutableStateOf(false) }
    GrowCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.AutoAwesome, contentDescription = null, tint = c.night, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(6.dp))
            Text("Daily brief", style = MaterialTheme.typography.titleSmall, color = c.night)
            Spacer(Modifier.weight(1f))
            Text(Formatting.shortDateTime(brief.createdAt), style = MaterialTheme.typography.bodySmall, color = c.textTertiary)
        }
        if (!brief.headline.isNullOrEmpty()) {
            Spacer(Modifier.height(12.dp))
            Text(brief.headline, style = MaterialTheme.typography.headlineMedium, color = c.text)
        }
        Formatting.parseISO(brief.cameraFrameAt)?.let { t ->
            Spacer(Modifier.height(6.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Videocam, contentDescription = null, tint = c.textSecondary, modifier = Modifier.size(14.dp))
                Spacer(Modifier.width(6.dp))
                Text("Included the tent camera frame from ${Formatting.shortDateTime(brief.cameraFrameAt)}", style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
            }
        }
        if (!brief.summary.isNullOrEmpty()) {
            Spacer(Modifier.height(8.dp))
            Text(brief.summary, style = MaterialTheme.typography.bodyLarge, color = c.textSecondary)
        }
        val per = brief.perPlant
        if (!per.isNullOrEmpty()) {
            Spacer(Modifier.height(12.dp))
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                per.forEach { pp ->
                    Row(verticalAlignment = Alignment.Top) {
                        LeafGlyph()
                        Spacer(Modifier.width(10.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(pp.name ?: "Plant", style = MaterialTheme.typography.labelMedium, color = c.brand)
                            if (!pp.headline.isNullOrEmpty()) Text(pp.headline, style = MaterialTheme.typography.titleSmall, color = c.text)
                            if (!pp.summary.isNullOrEmpty()) Text(pp.summary, style = MaterialTheme.typography.bodyMedium, color = c.textSecondary)
                        }
                    }
                }
            }
        }
        val concerns = brief.concerns
        if (!concerns.isNullOrEmpty()) {
            CollapsibleSection("Concerns", Icons.Filled.Warning, c.warn, concerns.size, showConcerns, { showConcerns = !showConcerns }) {
                BulletList(concerns, color = c.warn, icon = Icons.Filled.Warning)
            }
        }
        val actions = brief.actions
        if (!actions.isNullOrEmpty()) {
            CollapsibleSection("Do today", Icons.Filled.CheckCircle, c.brand, actions.size, showActions, { showActions = !showActions }) {
                NumberedList(actions, color = c.brand)
            }
        }
        val tc = brief.targetChanges
        if (!tc.isNullOrEmpty()) {
            CollapsibleSection("Targets changed", Icons.Filled.Tune, c.night, tc.size, showTargets, { showTargets = !showTargets }) {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    tc.forEach { ch ->
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(Formatting.capitalize(ch.field ?: ""), style = MaterialTheme.typography.bodyMedium.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.Medium), color = c.text)
                                Text("${ch.from.display()} → ${ch.to.display()}", style = MaterialTheme.typography.bodyMedium, color = c.night)
                            }
                            if (!ch.reason.isNullOrEmpty()) Text(ch.reason, style = MaterialTheme.typography.bodySmall, color = c.textSecondary)
                        }
                    }
                }
            }
        }
        if (!brief.tasks.isNullOrEmpty() || !brief.photoRequests.isNullOrEmpty()) {
            Spacer(Modifier.height(12.dp))
            CreatedItemsView(brief.tasks, brief.photoRequests)
        }
    }
}

@Composable
fun CollapsibleSection(title: String, icon: ImageVector, tint: Color, count: Int, isOpen: Boolean, onToggle: () -> Unit, content: @Composable () -> Unit) {
    val c = GrowTheme.colors
    Column(Modifier.fillMaxWidth().padding(top = 14.dp)) {
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(onClick = onToggle).padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(18.dp))
            Spacer(Modifier.width(8.dp))
            Text(title, style = MaterialTheme.typography.titleSmall, color = c.text)
            Spacer(Modifier.width(8.dp))
            LevelChip("$count", tint)
            Spacer(Modifier.weight(1f))
            Icon(Icons.Filled.ExpandMore, contentDescription = null, tint = c.textTertiary, modifier = Modifier.size(20.dp).rotate(if (isOpen) 180f else 0f))
        }
        if (isOpen) {
            Spacer(Modifier.height(10.dp))
            content()
        }
    }
}

// MARK: - Chat bubble

@Composable
fun LeafGlyph() {
    val c = GrowTheme.colors
    Box(Modifier.size(28.dp).background(c.brand.copy(alpha = 0.14f), CircleShape), contentAlignment = Alignment.Center) {
        Icon(Icons.Filled.Eco, contentDescription = null, tint = c.brand, modifier = Modifier.size(15.dp))
    }
}

/** This person's own messages sit on the right; the advisor's and the other grower's on the left. */
@Composable
fun ChatBubble(message: ChatMessage, mine: Boolean = true) {
    val c = GrowTheme.colors
    val user = message.isUser && mine
    val other = message.isUser && !mine
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Bottom, horizontalArrangement = if (user) Arrangement.End else Arrangement.Start) {
        if (!message.isUser) { LeafGlyph(); Spacer(Modifier.width(8.dp)) }
        Column(horizontalAlignment = if (user) Alignment.End else Alignment.Start, modifier = Modifier.widthIn(max = 320.dp)) {
            if (other && !message.author.isNullOrBlank()) {
                Text(message.author, style = MaterialTheme.typography.labelMedium, color = c.textSecondary, modifier = Modifier.padding(start = 6.dp, bottom = 2.dp))
            }
            Box(
                Modifier.clip(RoundedCornerShape(18.dp)).background(if (user) c.brand else if (other) c.night.copy(alpha = 0.12f) else c.card)
                    .border(if (user || other) 0.dp else 1.dp, if (user || other) Color.Transparent else c.track, RoundedCornerShape(18.dp))
                    .padding(horizontal = 14.dp, vertical = 10.dp),
            ) {
                SelectionContainer {
                    Text(message.content ?: "", style = MaterialTheme.typography.bodyLarge, color = if (user) Color.White else c.text)
                }
            }
            Spacer(Modifier.height(4.dp))
            Text(Formatting.relative(message.createdAt), style = MaterialTheme.typography.labelSmall, color = c.textTertiary)
        }
    }
}

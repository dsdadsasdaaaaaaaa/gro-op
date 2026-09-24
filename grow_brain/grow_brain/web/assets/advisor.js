// Advisor: latest brief + chat.
import { api } from './api.js';
import { icon } from './icons.js';
import { h, replaceChildren, fmtDateTime, fmtTime, parseISO, spinner, notice, toast, errText, confirmDialog, select } from './util.js';

export function createAdvisor(ctx) {
  let root = null, refs = {}, brief = null, messages = [], sending = false, stickToBottom = false;

  function fieldLabel(f) { return ({ temp_min_c: 'Lowest temperature', temp_max_c: 'Highest temperature', humidity_min: 'Lowest humidity', humidity_max: 'Highest humidity', vpd_min: 'Air dryness low', vpd_max: 'Air dryness high' })[f] || f; }

  function renderBrief() {
    if (!brief) { replaceChildren(refs.brief, h('div', { class: 'empty' }, 'No brief yet. The advisor writes one every morning — or run one now.')); return; }
    const b = brief;
    replaceChildren(refs.brief,
      h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('span', { class: 'tiny faint' }, fmtDateTime(b.created_at)), b.camera_frame_at ? h('span', { class: 'chip night' }, icon('camera'), `camera frame from ${fmtTime(parseISO(b.camera_frame_at))}`) : null),
      h('h3', null, b.headline),
      h('p', null, b.summary),
      b.concerns?.length ? h('div', { class: 'sec' }, h('h4', null, 'Concerns'), h('ul', { class: 'clean' }, b.concerns.map((c) => h('li', null, c)))) : null,
      b.actions?.length ? h('div', { class: 'sec' }, h('h4', null, 'Today'), h('ul', { class: 'clean' }, b.actions.map((c) => h('li', null, c)))) : null,
      b.target_changes?.length ? h('div', { class: 'sec' }, h('h4', null, 'Target changes'), h('ul', { class: 'clean' }, b.target_changes.map((c) => h('li', null, h('b', null, fieldLabel(c.field)), c.from != null ? ` ${c.from} → ${c.to}` : ` → ${c.to}`, c.reason ? h('span', { class: 'muted' }, ` — ${c.reason}`) : null, c.applied === false ? h('span', { class: 'chip warn', style: { marginLeft: '6px' } }, 'not applied') : null)))) : null,
      b.per_plant?.length ? h('div', { class: 'sec' }, h('h4', null, 'Per plant'), h('div', { class: 'per-plant' }, b.per_plant.map((p) => h('div', null, h('b', null, p.name || `Plant ${p.plant_id}`), h('div', { class: 'small', style: { marginTop: '2px' } }, h('b', { class: 'muted' }, p.headline), ' ', p.summary))))) : null,
      b.photo_requests?.length || b.tasks?.length ? h('div', { class: 'sec row' }, b.photo_requests?.length ? h('a', { class: 'pill', href: '#/journal?filter=todo' }, icon('camera'), `${b.photo_requests.length} photo request${b.photo_requests.length > 1 ? 's' : ''}`) : null, b.tasks?.length ? h('a', { class: 'pill', href: '#/journal?filter=todo' }, icon('list'), `${b.tasks.length} task${b.tasks.length > 1 ? 's' : ''}`) : null) : null);
  }

  async function loadBrief() {
    try {
      brief = await api.get('/api/brief');
      if (root) renderBrief();
      if (brief && brief.read === false) { try { await api.post(`/api/brief/${brief.id}/read`); ctx.refreshStatus(); } catch { /* ignore */ } }
    } catch (e) { if (root) replaceChildren(refs.brief, notice(errText(e), 'alert')); }
  }

  async function runBrief() {
    refs.runBtn.disabled = true; replaceChildren(refs.runBtn, spinner(), 'Writing the brief… up to a minute');
    try { brief = await api.post('/api/brief/run'); renderBrief(); toast('Brief ready', 'ok'); ctx.refreshStatus(); }
    catch (e) { toast(errText(e), 'error'); }
    refs.runBtn.disabled = false; replaceChildren(refs.runBtn, icon('sparkles'), 'Write a brief now (≈ $0.10)');
  }

  function renderMessages() {
    replaceChildren(refs.msgs, messages.length ? messages.map((m) => h('div', { class: `msg ${m.role}` },
      m.role === 'user' && m.author ? h('div', { class: 'who' }, m.author) : null, m.content, h('time', { datetime: m.created_at }, fmtDateTime(m.created_at))))
      : h('div', { class: 'empty' }, 'Ask anything about the grow: feeding, training, what a leaf symptom means.'));
    if (sending) refs.msgs.append(h('div', { class: 'msg assistant row' }, spinner(), 'Thinking…'));
    if (stickToBottom) refs.msgs.scrollTop = refs.msgs.scrollHeight;
  }

  async function loadChat() {
    try { const r = await api.get('/api/chat?limit=50'); messages = (r.messages || []).slice().sort((a, b) => a.id - b.id); if (root) renderMessages(); }
    catch (e) { if (root) replaceChildren(refs.msgs, notice(errText(e), 'alert')); }
  }

  async function send() {
    const text = refs.input.value.trim();
    if (!text || sending) return;
    sending = true; stickToBottom = true; refs.input.value = ''; refs.sendBtn.disabled = true;
    messages.push({ id: Date.now(), role: 'user', content: text, created_at: new Date().toISOString() });
    renderMessages();
    try {
      const pid = refs.plantSel.value ? Number(refs.plantSel.value) : null;
      const plant = (ctx.getStatus()?.plants || []).find((p) => p.id === pid);
      if (plant?.owner) messages[messages.length - 1].author = plant.owner;
      const r = await api.post('/api/chat', { message: text, plant_id: pid });
      messages.push({ id: r.id, role: 'assistant', content: r.reply, created_at: new Date().toISOString() });
    } catch (e) { toast(errText(e), 'error'); }
    sending = false; refs.sendBtn.disabled = false; renderMessages(); refs.input.focus(); ctx.refreshStatus();
  }

  async function clearChat() {
    if (!(await confirmDialog({ title: 'Clear the chat for both of you?', message: 'There is one shared conversation. The advisor forgets it for everyone; logs, photos and tasks stay.', confirmText: 'Clear it', danger: true }))) return;
    try { await api.del('/api/chat'); messages = []; renderMessages(); toast('Chat cleared'); } catch (e) { toast(errText(e), 'error'); }
  }

  function plantOptions() { const ps = ctx.getStatus()?.plants || []; return [{ value: '', label: 'Whole tent' }, ...ps.map((p) => ({ value: p.id, label: p.name }))]; }

  function mount(el) {
    root = el; refs = {};
    refs.brief = h('div', { class: 'brief' }, h('div', { class: 'row muted small' }, spinner(), 'Loading…'));
    refs.runBtn = h('button', { class: 'btn ghost', onclick: runBrief }, icon('sparkles'), 'Write a brief now (≈ $0.10)');
    refs.msgs = h('div', { class: 'msgs', role: 'log', 'aria-live': 'polite' });
    refs.plantSel = select(plantOptions(), '', { 'aria-label': 'Which plant this is about' });
    refs.input = h('textarea', { class: 'input', placeholder: 'Message the advisor…', rows: 1, 'aria-label': 'Message', onkeydown: (e) => { if ((e.key === 'Enter' || e.keyCode === 13) && !e.shiftKey) { e.preventDefault(); send(); } } });
    refs.sendBtn = h('button', { class: 'btn icon', 'aria-label': 'Send', onclick: send }, icon('send'));
    const adv = ctx.getSettings();
    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'Advisor'), h('div', { class: 'date' }, adv && adv.advisor_enabled === false ? 'The advisor is off — add an Anthropic API key to the add-on to turn it on.' : 'The advisor watches the tent, the camera and your journal.')), refs.runBtn),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, icon('sparkles'), 'Latest brief')), refs.brief),
      h('div', { class: 'card chat' },
        h('div', { class: 'card-head' }, h('h2', null, 'Chat'), h('button', { class: 'btn sm quiet', onclick: clearChat }, icon('trash'), 'Clear')),
        refs.msgs,
        h('div', { class: 'composer' }, refs.plantSel, refs.input, refs.sendBtn)));
    loadBrief(); loadChat();
  }
  function onStatus() { if (root) { const v = refs.plantSel.value; replaceChildren(refs.plantSel, plantOptions().map((o) => h('option', { value: o.value, selected: String(o.value) === v }, o.label))); } }
  function unmount() { root = null; }
  return { mount, unmount, onStatus, onSettings() {}, title: 'Advisor' };
}

// Journal: per-plant timeline of log entries, photos, photo requests, tasks and briefs.
import { api } from './api.js';
import { icon, LOG_ICON } from './icons.js';
import {
  h, replaceChildren, num, capitalize, plantLabel, dayKey, fmtTime, fmtDateTime, parseISO, spinner, notice, toast, errText,
  openModal, field, input, select, todayISO, dueText, LOG_LABEL, CONTEXT_LABEL, confirmDialog,
} from './util.js';
import { renderAnalysis } from './overview.js';

const KINDS = ['water', 'planted', 'transplant', 'height', 'note', 'observation', 'ph', 'feed', 'defoliation', 'training', 'ec', 'ppm', 'other'];
const FILTERS = [{ value: 'todo', label: 'To do' }, { value: 'all', label: 'Everything' }, { value: 'log', label: 'Logs' }, { value: 'photo', label: 'Photos' }, { value: 'request', label: 'Photo requests' }, { value: 'task', label: 'Tasks' }, { value: 'brief', label: 'Briefs' }];
const VALUE_HINT = { water: 'e.g. 0.05 (L) for a cup', height: 'e.g. 12 (cm)', ph: 'e.g. 6.4', feed: 'e.g. 0.5 (L)', ec: 'e.g. 1.2', ppm: 'e.g. 600' };
const UNIT_FOR = { water: 'L', feed: 'L', height: 'cm', ph: 'pH', ec: 'mS/cm', ppm: 'ppm' };

export function createJournal(ctx) {
  let root = null, refs = {}, tab = null, filter = 'all', data = null, thumbUrls = [];

  function plants() { return ctx.getStatus()?.plants || []; }

  async function load() {
    if (!root) return;
    refs.loading.classList.remove('hidden');
    const [log, photos, reqs, tasks, brief] = await Promise.allSettled([
      api.get('/api/log?limit=200'), api.get('/api/photos?limit=100'), api.get('/api/photo-requests?status=all'), api.get('/api/tasks?status=all'), api.get('/api/brief'),
    ]);
    if (!root) return;
    const val = (r, k) => (r.status === 'fulfilled' ? (k ? r.value?.[k] : r.value) || [] : []);
    data = { log: val(log, 'entries'), photos: val(photos, 'photos'), reqs: val(reqs, 'requests'), tasks: val(tasks, 'tasks'), brief: brief.status === 'fulfilled' ? brief.value : null };
    refs.loading.classList.add('hidden');
    render();
  }

  function items(which = tab) {
    const out = [];
    const forTab = (pid) => (which === 'tent' ? pid == null : pid === which);
    for (const e of data.log) if (forTab(e.plant_id)) out.push({ type: 'log', at: e.created_at, d: e });
    for (const p of data.photos) if (forTab(p.plant_id)) out.push({ type: 'photo', at: p.created_at, d: p });
    for (const r of data.reqs) if (forTab(r.plant_id)) out.push({ type: 'request', at: r.created_at, d: r });
    for (const t of data.tasks) if (forTab(t.plant_id)) out.push({ type: 'task', at: t.created_at, d: t });
    const b = data.brief;
    if (b) {
      if (which === 'tent') out.push({ type: 'brief', at: b.created_at, d: b });
      else { const pb = (b.per_plant || []).find((x) => x.plant_id === which); if (pb) out.push({ type: 'brief', at: b.created_at, d: { ...b, headline: pb.headline, summary: pb.summary, plantOnly: true } }); }
    }
    return out.filter((i) => filter === 'all' || i.type === filter).sort((a, b) => (parseISO(b.at)?.getTime() || 0) - (parseISO(a.at)?.getTime() || 0));
  }

  function column(p) {
    const list = items(p.id);
    const lastPhoto = data.photos.filter((x) => x.plant_id === p.id && x.analysis && x.analysis.health_score > 0).sort((a, b) => (parseISO(b.created_at)?.getTime() || 0) - (parseISO(a.created_at)?.getTime() || 0))[0];
    const openTasks = data.tasks.filter((t) => t.plant_id === p.id && t.status === 'open').length;
    const lastWater = data.log.filter((e) => e.plant_id === p.id && e.kind === 'water')[0];
    const stats = h('div', { class: 'muted small' }, `Day ${p.day_total ?? '–'} · health ${lastPhoto ? lastPhoto.analysis.health_score + '/10' : '–'} · ${openTasks} open task${openTasks === 1 ? '' : 's'} · last watered ${lastWater ? dayKey(lastWater.created_at) : 'never logged'}`);
    const nodes = []; let lastDay = null;
    for (const it of list.slice(0, 60)) { const dk = dayKey(it.at); if (dk !== lastDay) { nodes.push(h('div', { class: 'tl-day' }, dk)); lastDay = dk; } nodes.push(renderItem(it)); }
    return h('div', { class: 'compare-col' }, h('h3', null, plantLabel(p)), stats, h('div', { class: 'timeline' }, nodes.length ? nodes : h('div', { class: 'empty' }, 'Nothing yet.')));
  }

  function renderTodo() {
    const ps = plants();
    const groups = [...ps.map((p) => ({ key: p.id, title: plantLabel(p) + ' plant' })), { key: null, title: 'The tent' }];
    const today = todayISO();
    const rank = (t) => (!t.due ? 2 : t.due <= today ? 0 : 1);
    const cols = groups.map((g) => {
      const tasks = data.tasks.filter((t) => t.status === 'open' && (t.plant_id ?? null) === g.key)
        .sort((a, b) => rank(a) - rank(b) || String(a.due || '').localeCompare(String(b.due || '')) || (b.priority === 'high') - (a.priority === 'high'));
      const reqs = data.reqs.filter((r) => r.status === 'open' && (r.plant_id ?? null) === g.key);
      const list = [...reqs.map((r) => ({ type: 'request', at: r.created_at, d: r })), ...tasks.map((t) => ({ type: 'task', at: t.created_at, d: t }))];
      return h('div', { class: 'compare-col' }, h('h3', null, g.title), list.length ? h('div', { class: 'timeline' }, list.map(renderItem)) : h('div', { class: 'empty' }, 'Nothing to do.'));
    });
    replaceChildren(refs.timeline, h('div', { class: 'compare' }, ...cols));
  }

  function render() {
    if (!data) return;
    refs.tabs.classList.toggle('hidden', filter === 'todo');
    if (filter === 'todo') { for (const u of thumbUrls) URL.revokeObjectURL(u); thumbUrls = []; renderTodo(); return; }
    if (tab === 'compare') {
      for (const u of thumbUrls) URL.revokeObjectURL(u); thumbUrls = [];
      replaceChildren(refs.timeline, h('div', { class: 'compare' }, ...plants().map(column)));
      return;
    }
    const list = items();
    for (const u of thumbUrls) URL.revokeObjectURL(u); thumbUrls = [];
    if (!list.length) { replaceChildren(refs.timeline, h('div', { class: 'empty' }, 'Nothing here yet.')); return; }
    const nodes = []; let lastDay = null;
    for (const it of list) {
      const dk = dayKey(it.at);
      if (dk !== lastDay) { nodes.push(h('div', { class: 'tl-day' }, dk)); lastDay = dk; }
      nodes.push(renderItem(it));
    }
    replaceChildren(refs.timeline, nodes);
  }

  function renderItem(it) {
    const d = it.d; const time = h('time', { datetime: it.at, title: fmtDateTime(it.at) }, fmtTime(parseISO(it.at)));
    if (it.type === 'log') {
      const val = d.value != null ? `${num(d.value, Number.isInteger(d.value) ? 0 : 2).replace(/\.?0+$/, '')}${d.unit ? ' ' + d.unit : ''}` : '';
      const title = [LOG_LABEL[d.kind] || capitalize(d.kind), val, d.context ? (CONTEXT_LABEL[d.context] || d.context.replace(/_/g, ' ')) : null].filter(Boolean).join(' · ');
      return h('div', { class: 'card tight tl-item log' },
        h('div', { class: 'tl-head' }, icon(LOG_ICON[d.kind] || 'note'), h('span', { class: 't' }, title), time),
        (d.note || d.advice_summary) ? h('div', { class: 'tl-body' }, d.note ? h('div', null, d.note) : null,
          d.advice_summary ? h('div', { class: 'adv' }, icon('sparkles'), ' ', d.advice_summary,
            d.advice_steps?.length ? h('ul', { class: 'clean small', style: { marginTop: '4px' } }, d.advice_steps.map((x) => h('li', null, x))) : null) : null) : null);
    }
    if (it.type === 'photo') {
      const img = h('img', { class: 'thumb', alt: 'Photo thumbnail', loading: 'lazy' });
      api.blobUrl(`/api/photos/${d.id}/thumb`).then((u) => { thumbUrls.push(u); img.src = u; }).catch(() => {});
      const a = d.analysis || {};
      return h('div', { class: 'card tight tl-item photo' },
        h('div', { class: 'tl-head' }, icon(d.source === 'camera' ? 'camera' : 'image'), h('span', { class: 't' }, d.source === 'camera' ? 'Tent camera' : 'Photo', a.health_score != null ? h('span', { class: `chip ${a.health_score >= 7 ? 'good' : a.health_score >= 4 ? 'warn' : 'alert'}`, style: { marginLeft: '8px' } }, `health ${a.health_score}/10`) : null), time),
        h('div', { class: 'tl-body tl-photo' }, h('button', { class: 'thumb', type: 'button', 'aria-label': 'Open photo', onclick: () => openPhoto(d) }, img), h('div', null, a.summary ? h('div', null, a.summary) : h('div', { class: 'muted' }, 'No analysis'), d.note && d.source !== 'camera' ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, d.note) : null)));
    }
    if (it.type === 'request') {
      const open = d.status === 'open';
      return h('div', { class: `card tight tl-item request ${open ? 'open-req' : ''}` },
        h('div', { class: 'tl-head' }, icon('camera'), h('span', { class: 't' }, d.title), h('span', { class: `chip ${open ? 'warn' : d.status === 'done' ? 'good' : ''}` }, open ? 'Photo wanted' : d.status), time),
        h('div', { class: 'tl-body' }, open ? h('div', null, d.instructions) : null, d.reason ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, d.reason) : null,
          open ? h('div', { class: 'row', style: { marginTop: '10px' } }, h('span', { class: 'small muted' }, 'Take it with the phone app.'), h('button', { class: 'btn sm quiet', onclick: async () => {
            const ok = await confirmDialog({ title: 'Skip this photo?', message: 'The advisor won\'t get this picture. It will ask again if it still needs it.', confirmText: 'Skip it', cancelText: 'Keep it' });
            if (!ok) return;
            try { await api.post(`/api/photo-requests/${d.id}/skip`); toast('Skipped'); load(); ctx.refreshStatus(); } catch (e) { toast(errText(e), 'error'); } } }, 'Skip')) : null));
    }
    if (it.type === 'task') {
      const done = d.status === 'done';
      const cb = h('input', { type: 'checkbox', checked: done, 'aria-label': `${d.title} ${done ? 'done' : 'open'}`, onchange: async () => {
        try { await api.post(`/api/tasks/${d.id}/${cb.checked ? 'complete' : 'reopen'}`); load(); ctx.refreshStatus(); } catch (e) { toast(errText(e), 'error'); cb.checked = !cb.checked; }
      } });
      return h('div', { class: `card tight tl-item task ${done ? 'done' : ''}` },
        h('div', { class: 'task-line' }, cb, h('div', { style: { flex: 1, minWidth: 0 } },
          h('div', { class: 'tl-head' }, h('span', { class: 't' }, d.title), d.priority === 'high' && !done ? h('span', { class: 'chip alert' }, 'high') : null, time),
          d.detail ? h('div', { class: 'tl-body' }, d.detail) : null,
          h('div', { class: `tiny ${!done && d.due && d.due < todayISO() ? 'lvl-warn' : 'faint'}`, style: { marginTop: '4px' } },
            [!done && d.due ? dueText(d.due) : null, d.created_by === 'advisor' ? 'from the advisor' : d.created_by === 'system' ? 'added by GrowOp' : null].filter(Boolean).join(' · ')))));
    }
    if (it.type === 'brief') {
      return h('div', { class: 'card tight tl-item brief' },
        h('details', { class: 'exp' },
          h('summary', null, icon('sparkles'), h('span', { class: 't', style: { flex: 1 } }, d.headline), time),
          h('div', { class: 'tl-body' }, h('p', null, d.summary),
            !d.plantOnly && d.concerns?.length ? h('div', { style: { marginTop: '8px' } }, h('div', { class: 'label' }, 'Concerns'), h('ul', { class: 'clean' }, d.concerns.map((c) => h('li', null, c)))) : null,
            !d.plantOnly && d.actions?.length ? h('div', { style: { marginTop: '8px' } }, h('div', { class: 'label' }, 'Actions'), h('ul', { class: 'clean' }, d.actions.map((c) => h('li', null, c)))) : null,
            h('a', { href: '#/advisor', class: 'small', style: { display: 'inline-block', marginTop: '8px' } }, 'Open in Advisor'))));
    }
    return h('div');
  }

  function openPhoto(p) {
    const img = h('img', { class: 'photo-full', alt: 'Tent photo' });
    let url = null;
    api.blobUrl(`/api/photos/${p.id}/image`).then((u) => { url = u; img.src = u; }).catch((e) => toast(errText(e), 'error'));
    openModal({ title: `Photo · ${fmtDateTime(p.created_at)}`, size: 'medium', body: h('div', { class: 'stack' }, img, p.note ? h('p', { class: 'muted small' }, p.note) : null, renderAnalysis(p.analysis)), onClose: () => { if (url) URL.revokeObjectURL(url); } });
  }

  function formPlant() { return tab === 'tent' ? null : typeof tab === 'number' ? tab : undefined; }

  function logForm() {
    const kind = select(KINDS.map((k) => ({ value: k, label: LOG_LABEL[k] || capitalize(k) })), 'water');
    const value = input({ type: 'number', step: 'any', inputmode: 'decimal', placeholder: VALUE_HINT.water });
    const unit = input({ placeholder: 'L', value: 'L' });
    const note = h('textarea', { class: 'input', placeholder: 'Anything worth remembering', rows: 2 });
    kind.addEventListener('change', () => { value.placeholder = VALUE_HINT[kind.value] || 'optional'; unit.value = UNIT_FOR[kind.value] || ''; });
    const save = h('button', { class: 'btn', type: 'submit', value: 'save' }, icon('plus'), 'Save');
    const ask = h('button', { class: 'btn ghost', type: 'submit', value: 'ask' }, icon('sparkles'), 'Save & ask the advisor (≈ $0.05)');
    const result = h('div');
    let advise = false;
    save.addEventListener('click', () => { advise = false; });
    ask.addEventListener('click', () => { advise = true; });
    const form = h('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      const pid = formPlant();
      if (pid === undefined) { replaceChildren(result, notice('Pick a plant\'s tab (or Tent) first, then add the entry.', 'warn')); return; }
      save.disabled = ask.disabled = true;
      replaceChildren(result, h('div', { class: 'row muted small' }, spinner(), advise ? 'Saving and asking the advisor: this can take up to 40 s.' : 'Saving…'));
      try {
        const body = { kind: kind.value, plant_id: pid, advise };
        if (value.value !== '') body.value = Number(value.value);
        if (unit.value) body.unit = unit.value; if (note.value) body.note = note.value;
        const r = await api.post('/api/log', body);
        const adv = r.advice;
        replaceChildren(result, advise && adv && adv.summary ? h('div', { class: `notice ${adv.urgency === 'urgent' ? 'alert' : adv.urgency === 'attention' ? 'warn' : ''}` }, icon('sparkles'), h('div', null, h('div', null, adv.summary), adv.steps?.length ? h('ul', { class: 'clean', style: { marginTop: '6px' } }, adv.steps.map((x) => h('li', null, x))) : null)) : notice('Saved. The advisor reads it in the next daily brief.', 'info', 'check'));
        value.value = ''; note.value = ''; toast('Entry added', 'ok'); load(); ctx.refreshStatus();
      } catch (err) { replaceChildren(result, notice(errText(err), 'alert')); }
      save.disabled = ask.disabled = false;
    } },
      h('div', { class: 'form-grid' }, field('What', kind), field('Amount', value), field('Unit', unit), field('Note', note, { class: 'wide' })),
      h('div', { class: 'form-actions' }, h('span', { class: 'small muted', style: { marginRight: 'auto' } }, 'Save is instant and free. Asking the advisor costs a few cents.'), ask, save), result);
    return form;
  }

  let tabAuto = true; // true until the person picks a tab; lets the first plant become default once status arrives
  function renderTabs() {
    const ps = plants();
    if (tab == null || (tabAuto && tab === 'tent' && ps.length)) tab = ps[0]?.id ?? 'tent';
    const extra = ps.length > 1 ? [{ id: 'compare', label: 'Compare' }] : [];
    replaceChildren(refs.tabs, [...ps.map((p) => ({ id: p.id, label: plantLabel(p) })), { id: 'tent', label: 'Tent' }, ...extra].map((t) =>
      h('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === t.id), onclick: () => { tab = t.id; tabAuto = false; renderTabs(); render(); } }, t.label)));
    refs.forLabel.textContent = tab === 'tent' ? 'for the tent (both plants)' : tab === 'compare' ? '(pick a plant\'s tab first)' : `for ${plantLabel(ps.find((p) => p.id === tab))} plant`;
  }

  function renderFilters() {
    replaceChildren(refs.filters, FILTERS.map((f) => h('button', { type: 'button', 'aria-pressed': String(filter === f.value), onclick: () => { filter = f.value; renderFilters(); render(); } }, f.label)));
  }

  function mount(el, params) {
    root = el; refs = {};
    if (params?.get('filter')) filter = params.get('filter');
    refs.loading = h('span', { class: 'row muted small' }, spinner(), 'Loading…');
    refs.tabs = h('div', { class: 'tabs', role: 'tablist' });
    refs.filters = h('div', { class: 'filters' });
    refs.timeline = h('div', { class: 'timeline' });
    refs.forLabel = h('span', { class: 'muted small' });
    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'Journal'), h('div', { class: 'date' }, 'Everything that happened, newest first.')), refs.loading),
      refs.tabs,
      h('div', { class: 'card' }, h('details', { class: 'exp' }, h('summary', null, icon('plus'), 'Add log entry ', refs.forLabel), h('div', { style: { marginTop: '12px' } }, logForm()))),
      refs.filters, refs.timeline);
    renderTabs(); renderFilters(); load();
  }
  function onStatus() { if (root && data) { const before = refs.tabs.children.length; renderTabs(); if (before !== refs.tabs.children.length) render(); } }
  function unmount() { for (const u of thumbUrls) URL.revokeObjectURL(u); thumbUrls = []; root = null; data = null; }
  return { mount, unmount, onStatus, onSettings() {}, title: 'Journal' };
}

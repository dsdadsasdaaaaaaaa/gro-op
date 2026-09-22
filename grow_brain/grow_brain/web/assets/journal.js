// Journal: per-plant timeline of log entries, photos, photo requests, tasks and briefs.
import { api } from './api.js';
import { icon, LOG_ICON } from './icons.js';
import {
  h, replaceChildren, num, capitalize, plantLabel, dayKey, fmtTime, fmtDateTime, parseISO, spinner, notice, toast, errText,
  openModal, field, input, select, todayISO,
} from './util.js';
import { renderAnalysis } from './overview.js';

const KINDS = ['ph', 'ec', 'ppm', 'water', 'feed', 'height', 'note', 'observation', 'defoliation', 'training', 'transplant', 'other'];
const FILTERS = [{ value: 'all', label: 'Everything' }, { value: 'log', label: 'Logs' }, { value: 'photo', label: 'Photos' }, { value: 'request', label: 'Photo requests' }, { value: 'task', label: 'Tasks' }, { value: 'brief', label: 'Briefs' }];

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

  function render() {
    if (!data) return;
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
      const title = [capitalize(d.kind), val, d.context].filter(Boolean).join(' · ');
      return h('div', { class: 'card tight tl-item log' },
        h('div', { class: 'tl-head' }, icon(LOG_ICON[d.kind] || 'note'), h('span', { class: 't' }, title), time),
        (d.note || d.advice_summary) ? h('div', { class: 'tl-body' }, d.note ? h('div', null, d.note) : null, d.advice_summary ? h('div', { class: 'adv' }, icon('sparkles'), ' ', d.advice_summary) : null) : null);
    }
    if (it.type === 'photo') {
      const img = h('img', { class: 'thumb', alt: 'Photo thumbnail', loading: 'lazy' });
      api.blobUrl(`/api/photos/${d.id}/thumb`).then((u) => { thumbUrls.push(u); img.src = u; }).catch(() => {});
      const a = d.analysis || {};
      return h('div', { class: 'card tight tl-item photo' },
        h('div', { class: 'tl-head' }, icon('image'), h('span', { class: 't' }, 'Photo', a.health_score != null ? h('span', { class: `chip ${a.health_score >= 7 ? 'good' : a.health_score >= 4 ? 'warn' : 'alert'}`, style: { marginLeft: '8px' } }, `health ${a.health_score}/10`) : null), time),
        h('div', { class: 'tl-body tl-photo' }, h('button', { class: 'thumb', type: 'button', 'aria-label': 'Open photo', onclick: () => openPhoto(d) }, img), h('div', null, a.summary ? h('div', null, a.summary) : h('div', { class: 'muted' }, 'No analysis'), d.note ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, d.note) : null)));
    }
    if (it.type === 'request') {
      const open = d.status === 'open';
      return h('div', { class: `card tight tl-item request ${open ? 'open-req' : ''}` },
        h('div', { class: 'tl-head' }, icon('camera'), h('span', { class: 't' }, d.title), h('span', { class: `chip ${open ? 'warn' : d.status === 'done' ? 'good' : ''}` }, open ? 'Photo wanted' : d.status), time),
        h('div', { class: 'tl-body' }, open ? h('div', null, d.instructions) : null, d.reason ? h('div', { class: 'small muted', style: { marginTop: '4px' } }, d.reason) : null,
          open ? h('div', { class: 'row', style: { marginTop: '10px' } }, h('span', { class: 'small muted' }, 'Take it with the phone app.'), h('button', { class: 'btn sm quiet', onclick: async () => { try { await api.post(`/api/photo-requests/${d.id}/skip`); toast('Skipped'); load(); ctx.refreshStatus(); } catch (e) { toast(errText(e), 'error'); } } }, 'Skip')) : null));
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
          h('div', { class: 'tiny faint', style: { marginTop: '4px' } }, [d.due ? `due ${d.due}` : null, d.created_by === 'advisor' ? 'from the advisor' : null].filter(Boolean).join(' · ')))));
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

  function logForm() {
    const kind = select(KINDS.map((k) => ({ value: k, label: capitalize(k) })), 'water');
    const value = input({ type: 'number', step: 'any', inputmode: 'decimal', placeholder: 'e.g. 6.3' });
    const unit = input({ placeholder: 'pH, L, cm…' });
    const context = input({ placeholder: 'water_in, runoff, reservoir…' });
    const note = h('textarea', { class: 'input', placeholder: 'Anything worth remembering', rows: 2 });
    const submit = h('button', { class: 'btn', type: 'submit' }, icon('plus'), 'Add entry');
    const result = h('div');
    const form = h('form', { class: 'stack', onsubmit: async (e) => {
      e.preventDefault();
      submit.disabled = true; replaceChildren(result, h('div', { class: 'row muted small' }, spinner(), 'Saving — the advisor may take up to 40 s to reply.'));
      try {
        const body = { kind: kind.value, plant_id: tab === 'tent' ? null : tab };
        if (value.value !== '') body.value = Number(value.value);
        if (unit.value) body.unit = unit.value; if (context.value) body.context = context.value; if (note.value) body.note = note.value;
        const r = await api.post('/api/log', body);
        const adv = r.advice;
        replaceChildren(result, adv && adv.summary ? h('div', { class: `notice ${adv.urgency === 'urgent' ? 'alert' : adv.urgency === 'attention' ? 'warn' : ''}` }, icon('sparkles'), h('div', null, h('div', null, adv.summary), adv.steps?.length ? h('ul', { class: 'clean', style: { marginTop: '6px' } }, adv.steps.map((s) => h('li', null, s))) : null)) : notice('Logged.', 'info', 'check'));
        value.value = ''; note.value = ''; toast('Entry added', 'ok'); load(); ctx.refreshStatus();
      } catch (err) { replaceChildren(result, notice(errText(err), 'alert')); }
      submit.disabled = false;
    } },
      h('div', { class: 'form-grid' }, field('Kind', kind), field('Value', value), field('Unit', unit), field('Context', context), field('Note', note, { class: 'wide' })),
      h('div', { class: 'form-actions' }, h('span', { class: 'small muted', style: { marginRight: 'auto' } }, 'The advisor replies with advice when it is on.'), submit), result);
    return form;
  }

  let tabAuto = true; // true until the person picks a tab; lets the first plant become default once status arrives
  function renderTabs() {
    const ps = plants();
    if (tab == null || (tabAuto && tab === 'tent' && ps.length)) tab = ps[0]?.id ?? 'tent';
    const extra = ps.length > 1 ? [{ id: 'compare', label: 'Compare' }] : [];
    replaceChildren(refs.tabs, [...ps.map((p) => ({ id: p.id, label: plantLabel(p) })), { id: 'tent', label: 'Tent' }, ...extra].map((t) =>
      h('button', { type: 'button', role: 'tab', 'aria-selected': String(tab === t.id), onclick: () => { tab = t.id; tabAuto = false; renderTabs(); render(); } }, t.label)));
    refs.forLabel.textContent = tab === 'tent' ? 'for the tent' : tab === 'compare' ? 'for a plant (pick its tab)' : `for ${plantLabel(ps.find((p) => p.id === tab))} plant`;
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

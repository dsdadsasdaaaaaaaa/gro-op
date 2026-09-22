// Settings: plants, tent, targets, camera, preferences, backup, connection, events.
import { api, getConn, setConn, clearConn } from './api.js';
import { icon, levelIcon } from './icons.js';
import {
  h, replaceChildren, num, cToF, fToC, capitalize, STAGE_NAMES, fmtDateTime, spinner, notice, toast, errText, confirmDialog,
  field, input, select, downloadBlob, todayISO,
} from './util.js';

const STAGES = ['seedling', 'veg', 'flower', 'flush', 'drying', 'curing', 'done'];
const MEDIA = ['soil', 'coco', 'hydro', 'other'];

export function createSettings(ctx) {
  let root = null, refs = {}, settings = null, grow = null, targets = null, camera = null;
  const usesF = () => (settings?.units || ctx.units()) === 'f';

  function saveBtn(label = 'Save') { return h('button', { class: 'btn', type: 'submit' }, label); }
  async function submitForm(btn, fn, okText = 'Saved') {
    btn.disabled = true; const prev = [...btn.childNodes]; replaceChildren(btn, spinner(), 'Saving…');
    try { await fn(); toast(okText, 'ok'); } catch (e) { toast(errText(e), 'error'); }
    btn.disabled = false; replaceChildren(btn, ...prev);
  }

  // ---------- plants ----------
  function plantForm(p, onDone) {
    const notifyOpts = [{ value: '', label: 'No push' }, ...(settings?.notify_services_available || []).map((s) => ({ value: s, label: s }))];
    if (p?.notify_service && !notifyOpts.some((o) => o.value === p.notify_service)) notifyOpts.push({ value: p.notify_service, label: p.notify_service });
    const f = {
      name: input({ value: p?.name || '', required: true, placeholder: "Levi's plant" }), owner: input({ value: p?.owner || '', placeholder: 'Levi' }),
      strain: input({ value: p?.strain ?? 'Liberty Haze' }), breeder: input({ value: p?.breeder ?? "Barney's Farm" }), seed_type: input({ value: p?.seed_type ?? 'feminized photoperiod' }),
      medium: select(MEDIA.map((m) => ({ value: m, label: capitalize(m) })), p?.medium || 'soil'), pot_size_l: input({ type: 'number', step: '0.5', min: 0, inputmode: 'decimal', value: p?.pot_size_l ?? 11 }),
      start_date: input({ type: 'date', value: p?.start_date || '' }), notify_service: select(notifyOpts, p?.notify_service || ''), notes: h('textarea', { class: 'input', rows: 2 }, p?.notes || ''),
    };
    const btn = saveBtn(p ? 'Save plant' : 'Add plant');
    const form = h('form', { class: 'stack', onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => {
      const body = { name: f.name.value.trim(), owner: f.owner.value.trim(), strain: f.strain.value, breeder: f.breeder.value, seed_type: f.seed_type.value, medium: f.medium.value, pot_size_l: Number(f.pot_size_l.value) || 0, start_date: f.start_date.value || null, notes: f.notes.value, notify_service: f.notify_service.value || null };
      if (p) await api.put(`/api/plants/${p.id}`, body); else await api.post('/api/plants', body);
      ctx.refreshStatus(); onDone();
    }, p ? 'Plant saved' : 'Plant added'); } },
      h('div', { class: 'form-grid' }, field('Name', f.name), field('Owner', f.owner), field('Strain', f.strain), field('Breeder', f.breeder), field('Seed type', f.seed_type), field('Medium', f.medium), field('Pot size (L)', f.pot_size_l), field('Start date', f.start_date), field('Notify', f.notify_service, { hint: 'Photo requests go to this phone' }), field('Notes', f.notes, { class: 'wide' })),
      h('div', { class: 'form-actions' },
        p ? h('button', { class: 'btn danger ghost', type: 'button', onclick: async () => {
          if (!(await confirmDialog({ title: `Remove ${p.name}?`, message: 'It is archived; its journal stays.', confirmText: 'Remove', danger: true, ic: 'trash' }))) return;
          try { await api.del(`/api/plants/${p.id}`); toast('Plant removed'); ctx.refreshStatus(); onDone(); } catch (e) { toast(errText(e), 'error'); }
        } }, icon('trash'), 'Remove') : null,
        h('button', { class: 'btn quiet', type: 'button', onclick: onDone }, 'Cancel'), btn));
    return form;
  }

  function renderPlants() {
    const plants = ctx.getStatus()?.plants || [];
    const list = h('div', { class: 'stack' });
    for (const p of plants) {
      const box = h('div', { class: 'plant-edit' });
      const show = () => replaceChildren(box, h('div', { class: 'head' }, icon('leaf', 'lvl-good'), h('b', null, p.name), h('span', { class: 'muted small' }, [p.owner, p.strain, p.start_date ? `since ${p.start_date}` : 'not started'].filter(Boolean).join(' · ')), h('button', { class: 'btn sm quiet', onclick: () => replaceChildren(box, plantForm(p, () => show())) }, 'Edit')));
      show(); list.append(box);
    }
    const addBox = h('div');
    const addBtn = h('button', { class: 'btn ghost', onclick: () => { replaceChildren(addBox, h('div', { class: 'plant-edit' }, plantForm(null, () => replaceChildren(addBox)))); } }, icon('plus'), 'Add plant');
    replaceChildren(refs.plants, list, addBox, addBtn);
  }

  // ---------- tent ----------
  function renderTent() {
    if (!grow) return;
    const stageSel = select(STAGES.map((s) => ({ value: s, label: STAGE_NAMES[s] })), grow.stage);
    const changeBtn = h('button', { class: 'btn ghost', type: 'button', onclick: async () => {
      const s = stageSel.value; if (s === grow.stage) return;
      if (!(await confirmDialog({ title: `Move the tent to ${STAGE_NAMES[s]}?`, message: 'Targets reset to the stage defaults and the advisor is told.', confirmText: 'Change stage' }))) { stageSel.value = grow.stage; return; }
      try { grow = await api.post('/api/grow/stage', { stage: s }); toast(`Now in ${STAGE_NAMES[s]}`, 'ok'); ctx.refreshStatus(); renderTent(); loadTargets(); } catch (e) { toast(errText(e), 'error'); }
    } }, 'Change stage');
    const ducted = h('input', { type: 'checkbox', checked: !!grow.exhaust_ducted });
    const flowerDays = input({ type: 'number', min: 30, max: 120, value: grow.expected_flower_days ?? 65 });
    const btn = saveBtn();
    replaceChildren(refs.tent,
      h('div', { class: 'kv' }, h('dt', null, 'Stage'), h('dd', null, h('b', null, STAGE_NAMES[grow.stage] || grow.stage), grow.stage_started ? h('span', { class: 'muted' }, ` since ${grow.stage_started}${(grow.day_in_stage ?? ctx.getStatus()?.grow?.day_in_stage) != null ? ` (day ${grow.day_in_stage ?? ctx.getStatus().grow.day_in_stage})` : ''}`) : null),
        grow.expected_harvest_date ? [h('dt', null, 'Harvest'), h('dd', null, `around ${grow.expected_harvest_date}`)] : null),
      h('div', { class: 'row', style: { marginTop: '12px' } }, stageSel, changeBtn),
      h('form', { style: { marginTop: '14px' }, onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => { grow = await api.put('/api/grow', { exhaust_ducted: ducted.checked, expected_flower_days: Number(flowerDays.value) || 65 }); }); } },
        h('div', { class: 'form-grid' }, h('label', { class: 'check' }, ducted, 'Exhaust is ducted outside the tent'), field('Expected flower days', flowerDays)),
        h('div', { class: 'form-actions' }, btn)));
  }

  // ---------- targets ----------
  function renderTargets() {
    if (!targets) return;
    const f = usesF();
    const t = targets;
    const tmin = input({ type: 'number', step: '0.5', inputmode: 'decimal', value: num(f ? (t.temp_min_f ?? cToF(t.temp_min_c)) : t.temp_min_c, 1) });
    const tmax = input({ type: 'number', step: '0.5', inputmode: 'decimal', value: num(f ? (t.temp_max_f ?? cToF(t.temp_max_c)) : t.temp_max_c, 1) });
    const hmin = input({ type: 'number', step: '1', value: t.humidity_min }), hmax = input({ type: 'number', step: '1', value: t.humidity_max });
    const vmin = input({ type: 'number', step: '0.05', value: t.vpd_min }), vmax = input({ type: 'number', step: '0.05', value: t.vpd_max });
    const lon = input({ type: 'time', value: t.light_on_time || '06:00' }), lh = input({ type: 'number', step: '0.5', min: 0, max: 24, value: t.light_hours });
    const btn = saveBtn();
    replaceChildren(refs.targets,
      h('div', { class: 'row small muted', style: { marginBottom: '12px' } }, h('span', { class: 'chip brand' }, { stage_default: 'stage default', advisor: 'set by advisor', manual: 'manual' }[t.source] || t.source), t.note || ''),
      h('form', { onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => {
        const body = { temp_min_c: f ? fToC(Number(tmin.value)) : Number(tmin.value), temp_max_c: f ? fToC(Number(tmax.value)) : Number(tmax.value), humidity_min: Number(hmin.value), humidity_max: Number(hmax.value), vpd_min: Number(vmin.value), vpd_max: Number(vmax.value), light_on_time: lon.value, light_hours: Number(lh.value) };
        body.temp_min_c = Math.round(body.temp_min_c * 10) / 10; body.temp_max_c = Math.round(body.temp_max_c * 10) / 10;
        targets = await api.put('/api/targets', body); renderTargets(); ctx.refreshStatus();
      }); } },
        h('div', { class: 'form-grid' }, field(`Temp min (${f ? '°F' : '°C'})`, tmin), field(`Temp max (${f ? '°F' : '°C'})`, tmax), field('Humidity min (%)', hmin), field('Humidity max (%)', hmax), field('VPD min (kPa)', vmin), field('VPD max (kPa)', vmax), field('Lights on at', lon), field('Light hours', lh)),
        h('div', { class: 'form-actions' }, h('button', { class: 'btn quiet', type: 'button', onclick: async () => {
          if (!(await confirmDialog({ title: 'Reset targets to the stage defaults?', confirmText: 'Reset' }))) return;
          try { targets = await api.del('/api/targets'); renderTargets(); ctx.refreshStatus(); toast('Targets reset', 'ok'); } catch (e) { toast(errText(e), 'error'); }
        } }, 'Reset to defaults'), btn)));
  }
  async function loadTargets() { try { targets = await api.get('/api/targets'); if (root) renderTargets(); } catch (e) { if (root) replaceChildren(refs.targets, notice(errText(e), 'alert')); } }

  // ---------- camera ----------
  function renderCamera() {
    if (!camera) return;
    const cands = camera.candidates || [];
    const cur = camera.camera?.entity_id || '';
    const opts = [{ value: '', label: 'Off' }, ...cands.map((c) => ({ value: c.entity_id, label: `${c.name}${c.brand ? ` (${c.brand}${c.model ? ' ' + c.model : ''})` : ''}` }))];
    if (cur && !cands.some((c) => c.entity_id === cur)) opts.push({ value: cur, label: cur });
    const sel = select(opts, cur, { 'aria-label': 'Camera' });
    const btn = saveBtn('Use this camera');
    replaceChildren(refs.camera,
      camera.camera ? h('div', { class: 'kv', style: { marginBottom: '12px' } }, h('dt', null, 'Current'), h('dd', null, camera.camera.name, camera.camera.available === false ? h('span', { class: 'chip alert', style: { marginLeft: '6px' } }, 'unavailable') : h('span', { class: 'chip good', style: { marginLeft: '6px' } }, 'live')), h('dt', null, 'Timelapse'), h('dd', null, `${camera.camera.frame_count || 0} frames`, camera.camera.last_frame_at ? `, last ${fmtDateTime(camera.camera.last_frame_at)}` : ''), camera.camera.error ? [h('dt', null, 'Error'), h('dd', { class: 'lvl-alert' }, camera.camera.error)] : null) : h('p', { class: 'muted small', style: { marginBottom: '12px' } }, 'No camera selected.'),
      h('form', { onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => { await api.put('/api/camera', { entity_id: sel.value || null }); camera = await api.get('/api/camera'); renderCamera(); ctx.refreshStatus(); }); } },
        h('div', { class: 'form-grid' }, field('Camera entity', sel, { hint: cands.length ? 'Any Home Assistant camera (Wyze via the bridge, Tapo, …)' : 'No cameras found in Home Assistant' })),
        h('div', { class: 'form-actions' }, btn)));
  }

  // ---------- preferences ----------
  function renderPrefs() {
    if (!settings) return;
    const s = settings;
    const notifyOpts = [{ value: '', label: 'Off' }, ...(s.notify_services_available || []).map((x) => ({ value: x, label: x }))];
    if (s.notify_service && !notifyOpts.some((o) => o.value === s.notify_service)) notifyOpts.push({ value: s.notify_service, label: s.notify_service });
    const f = {
      units: select([{ value: 'c', label: '°C' }, { value: 'f', label: '°F' }], s.units), brief_time: input({ type: 'time', value: s.brief_time || '08:00' }), timezone: input({ value: s.timezone || '', placeholder: 'America/New_York' }),
      notify_service: select(notifyOpts, s.notify_service || ''), auto: h('input', { type: 'checkbox', checked: !!s.auto_apply_advisor_targets }), model: input({ value: s.model || '' }),
      temp_offset_c: input({ type: 'number', step: '0.1', inputmode: 'decimal', value: s.temp_offset_c ?? 0 }), humidity_offset: input({ type: 'number', step: '0.5', inputmode: 'decimal', value: s.humidity_offset ?? 0 }),
      price: input({ type: 'number', step: '0.001', min: 0, inputmode: 'decimal', value: s.price_per_kwh ?? '', placeholder: '0.15' }), currency: input({ value: s.currency || 'CAD', maxlength: 4 }),
      capture: input({ type: 'number', min: 1, max: 240, value: s.camera_capture_minutes ?? 30 }),
    };
    const btn = saveBtn();
    replaceChildren(refs.prefs,
      h('form', { onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => {
        const body = { units: f.units.value, brief_time: f.brief_time.value, timezone: f.timezone.value.trim(), notify_service: f.notify_service.value || null, auto_apply_advisor_targets: f.auto.checked, model: f.model.value.trim(), temp_offset_c: Number(f.temp_offset_c.value) || 0, humidity_offset: Number(f.humidity_offset.value) || 0, price_per_kwh: f.price.value === '' ? null : Number(f.price.value), currency: f.currency.value.trim() || 'CAD', camera_capture_minutes: Number(f.capture.value) || 30 };
        settings = await api.put('/api/settings', body); ctx.setSettings(settings); renderPrefs(); renderTargets();
      }); } },
        h('div', { class: 'form-grid' }, field('Units', f.units), field('Brief time', f.brief_time), field('Timezone', f.timezone), field('Default notify service', f.notify_service, { hint: 'Briefs and safety alerts go to everyone' }), field('Advisor model', f.model), h('label', { class: 'check' }, f.auto, 'Let the advisor adjust targets'),
          field('Temp offset (°C)', f.temp_offset_c, { hint: 'Added to the raw sensor reading' }), field('Humidity offset (%)', f.humidity_offset), field('Price per kWh', f.price), field('Currency', f.currency), field('Camera frame every (min)', f.capture)),
        h('div', { class: 'form-actions' }, btn)));
  }

  // ---------- backup / connection / events ----------
  async function backup(btn) {
    btn.disabled = true; replaceChildren(btn, spinner(), 'Preparing…');
    try { const blob = await api.blob('/api/backup'); downloadBlob(blob, `growop-backup-${todayISO()}.zip`); toast('Backup downloaded', 'ok'); }
    catch (e) { toast(errText(e), 'error'); }
    btn.disabled = false; replaceChildren(btn, icon('download'), 'Download backup');
  }

  function renderConnection() {
    const c = getConn();
    replaceChildren(refs.conn,
      h('div', { class: 'kv' }, h('dt', null, 'Server'), h('dd', null, c.server || 'this page'), h('dt', null, 'API key'), h('dd', null, c.key ? '•'.repeat(Math.min(12, c.key.length)) : '—'), h('dt', null, 'Version'), h('dd', null, refs.version)),
      h('div', { class: 'form-actions', style: { justifyContent: 'flex-start' } }, h('button', { class: 'btn quiet', onclick: async () => { if (await confirmDialog({ title: 'Disconnect?', message: 'You will be asked for the API key again.', confirmText: 'Disconnect' })) { clearConn(); location.reload(); } } }, icon('key'), 'Change key / disconnect')));
    api.get('/api/health').then((hh) => { refs.version.textContent = `Grow Brain ${hh.version}${hh.advisor_enabled ? ' · advisor on' : ' · advisor off'}`; }).catch(() => {});
  }

  async function loadEvents() {
    try {
      const r = await api.get('/api/events?limit=100');
      if (!root) return;
      replaceChildren(refs.events, (r.events || []).length ? r.events.map((e) => h('div', { class: 'event' }, h('span', { class: `dot ${e.level}` }), h('span', { class: 'kind' }, e.kind), h('span', null, e.message), h('time', { datetime: e.at, title: e.at }, fmtDateTime(e.at)))) : h('div', { class: 'empty' }, 'No events yet.'));
    } catch (e) { if (root) replaceChildren(refs.events, notice(errText(e), 'alert')); }
  }

  async function loadAll() {
    const [s, g, c] = await Promise.allSettled([api.get('/api/settings'), api.get('/api/grow'), api.get('/api/camera')]);
    if (!root) return;
    if (s.status === 'fulfilled') { settings = s.value; ctx.setSettings(settings); renderPrefs(); } else replaceChildren(refs.prefs, notice(errText(s.reason), 'alert'));
    if (g.status === 'fulfilled') { grow = g.value; renderTent(); } else replaceChildren(refs.tent, notice(errText(g.reason), 'alert'));
    if (c.status === 'fulfilled') { camera = c.value; renderCamera(); } else replaceChildren(refs.camera, notice(errText(c.reason), 'alert'));
    renderPlants(); loadTargets(); loadEvents();
  }

  function mount(el) {
    root = el; refs = {};
    const loading = () => h('div', { class: 'row muted small' }, spinner(), 'Loading…');
    refs.plants = h('div', null, loading()); refs.tent = h('div', null, loading()); refs.targets = h('div', null, loading()); refs.camera = h('div', null, loading()); refs.prefs = h('div', null, loading()); refs.conn = h('div'); refs.events = h('div', { class: 'events' }, loading());
    refs.version = h('span', { class: 'muted' }, '…');
    const backupBtn = h('button', { class: 'btn' }, icon('download'), 'Download backup');
    backupBtn.onclick = () => backup(backupBtn);
    const card = (title, ic, body, cls = '') => h('section', { class: `card ${cls}`.trim(), 'aria-label': title }, h('div', { class: 'card-head' }, h('h2', null, icon(ic), title)), body);
    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'Settings'), h('div', { class: 'date' }, 'Plants, tent, targets, camera and preferences.'))),
      h('div', { class: 'settings-grid' },
        card('Plants', 'leaf', refs.plants, 'span2'),
        card('Tent', 'home', refs.tent), card('Targets', 'vpd', refs.targets),
        card('Camera', 'camera', refs.camera), card('Preferences', 'gear', refs.prefs),
        card('Backup', 'archive', h('div', { class: 'stack' }, h('p', { class: 'muted small' }, 'A zip of the database and photos. Keep one somewhere safe now and then.'), h('div', null, backupBtn))),
        card('Connection', 'key', refs.conn),
        card('Events', 'list', refs.events, 'span2')));
    renderConnection(); loadAll();
  }
  function onStatus() { if (root && settings) renderPlants(); }
  function onSettings(s) { settings = s; }
  function unmount() { root = null; }
  return { mount, unmount, onStatus, onSettings, title: 'Settings' };
}

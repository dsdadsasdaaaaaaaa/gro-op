// Settings: plants, tent, targets, camera, preferences, backup, connection, events.
import { api, getConn, setConn, clearConn, MODE } from './api.js';
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

  // 'notify.mobile_app_sm_g781w' → 'Samsung phone (sm g781w)', 'notify.mobile_app_iphone' → 'iPhone'
  function phoneName(svc) {
    const id = String(svc || '').replace(/^notify\./, '').replace(/^mobile_app_/, '');
    if (/^sm_/.test(id)) return `Samsung phone (${id.replace(/_/g, ' ')})`;
    if (/iphone/.test(id)) return id === 'iphone' ? 'iPhone' : `iPhone (${id.replace(/_/g, ' ')})`;
    if (/ipad/.test(id)) return `iPad (${id.replace(/_/g, ' ')})`;
    return id.replace(/_/g, ' ');
  }
  async function testPush(svc) {
    if (!svc) { toast('Pick a phone first', 'error'); return; }
    try { await api.post('/api/notify/test?service=' + encodeURIComponent(svc)); toast('Test sent: check that phone', 'ok'); } catch (e) { toast(errText(e), 'error'); }
  }

  // ---------- plants ----------
  function plantForm(p, onDone) {
    const notifyOpts = [{ value: '', label: 'No phone' }, ...(settings?.notify_services_available || []).map((s) => ({ value: s, label: phoneName(s) }))];
    if (p?.notify_service && !notifyOpts.some((o) => o.value === p.notify_service)) notifyOpts.push({ value: p.notify_service, label: phoneName(p.notify_service) });
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
      h('div', { class: 'form-grid' }, field('Name', f.name), field('Owner', f.owner), field('Strain', f.strain), field('Breeder', f.breeder), field('Seed type', f.seed_type), field('Medium', f.medium), field('Pot size (L)', f.pot_size_l), field('Start date', f.start_date), field('Phone for alerts', h('div', { class: 'row', style: { flexWrap: 'nowrap' } }, f.notify_service, h('button', { class: 'btn sm quiet', type: 'button', onclick: () => testPush(f.notify_service.value) }, 'Send test')), { hint: 'Tent alerts and this plant\'s reminders go to this phone' }), field('Notes', f.notes, { class: 'wide' })),
      h('div', { class: 'form-actions' },
        p ? h('button', { class: 'btn danger ghost', type: 'button', onclick: async () => {
          if (!(await confirmDialog({ title: `Remove ${p.name}?`, message: 'It disappears from the tent. Its journal and photos are kept, and you can bring it back from Settings → Plants.', confirmText: 'Remove', danger: true, ic: 'trash' }))) return;
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
    const removed = h('div', { class: 'stack' });
    replaceChildren(refs.plants, list, addBox, addBtn, removed);
    api.get('/api/plants?include_archived=true').then((r) => {
      const gone = r.archived || [];
      if (!gone.length || !root) return;
      replaceChildren(removed, h('div', { class: 'label', style: { marginTop: '12px' } }, 'Removed plants'),
        gone.map((g) => h('div', { class: 'row' }, h('span', { class: 'muted' }, g.name), h('button', { class: 'btn sm quiet', onclick: async () => {
          try { await api.post(`/api/plants/${g.id}/restore`); toast(`${g.name} is back`, 'ok'); ctx.refreshStatus(); renderPlants(); } catch (e) { toast(errText(e), 'error'); }
        } }, 'Bring back'))));
    }).catch(() => {});
  }

  // ---------- tent ----------
  function renderTent() {
    if (!grow) return;
    const stageSel = select(STAGES.map((s) => ({ value: s, label: STAGE_NAMES[s] })), grow.stage);
    const changeBtn = h('button', { class: 'btn ghost', type: 'button', onclick: async () => {
      const s = stageSel.value; if (s === grow.stage) return;
      const lightNote = { flower: ' The light switches to 12 hours on and 12 hours off by itself: never turn it on during the dark hours.', veg: ' The light stays on 18 hours a day.', drying: ' The light stays off from now on.', curing: ' Lights, humidifier and exhaust go idle.' }[s] || '';
      if (!(await confirmDialog({ title: `Move the tent to ${STAGE_NAMES[s]}?`, message: `Temperature and humidity go to the ${STAGE_NAMES[s].toLowerCase()} settings and the advisor is told.${lightNote}`, confirmText: 'Change stage' }))) { stageSel.value = grow.stage; return; }
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
    const lon = input({ type: 'time', value: t.light_on_time || '06:00' }), lh = input({ type: 'number', step: '0.5', min: 0, max: 24, value: t.light_hours });
    const btn = saveBtn();
    replaceChildren(refs.targets,
      h('div', { class: 'row small muted', style: { marginBottom: '12px' } }, h('span', { class: 'chip brand' }, { stage_default: 'stage default', advisor: 'set by advisor', manual: 'manual' }[t.source] || t.source), t.note || ''),
      h('form', { onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => {
        const body = { temp_min_c: f ? fToC(Number(tmin.value)) : Number(tmin.value), temp_max_c: f ? fToC(Number(tmax.value)) : Number(tmax.value), humidity_min: Number(hmin.value), humidity_max: Number(hmax.value), light_on_time: lon.value, light_hours: Number(lh.value) };
        body.temp_min_c = Math.round(body.temp_min_c * 10) / 10; body.temp_max_c = Math.round(body.temp_max_c * 10) / 10;
        targets = await api.put('/api/targets', body); renderTargets(); ctx.refreshStatus();
      }); } },
        h('div', { class: 'form-grid' }, field(`Temp min (${f ? '°F' : '°C'})`, tmin), field(`Temp max (${f ? '°F' : '°C'})`, tmax), field('Humidity min (%)', hmin), field('Humidity max (%)', hmax), field('Lights on at', lon), field('Light hours', lh)),
        h('p', { class: 'tiny faint' }, 'These are the daytime settings; at night the tent is allowed to be a few degrees cooler. Air dryness (VPD) follows from temperature and humidity.'),
        h('div', { class: 'form-actions' }, h('button', { class: 'btn quiet', type: 'button', onclick: async () => {
          if (!(await confirmDialog({ title: 'Reset targets to the stage defaults?', message: 'Your own changes and the advisor\'s tweaks for this stage are dropped.', confirmText: 'Reset' }))) return;
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

  // ---------- shared tent settings ----------
  function renderPrefs() {
    if (!settings) return;
    const s = settings;
    const phones = (s.notify_services_available || []);
    const phoneOpts = (none) => [{ value: '', label: none }, ...phones.map((x) => ({ value: x, label: phoneName(x) }))];
    const models = s.models_available || [s.model || 'claude-opus-5'];
    const f = {
      units: select([{ value: 'c', label: '°C' }, { value: 'f', label: '°F' }], s.units), brief_time: input({ type: 'time', value: s.brief_time || '08:00' }),
      auto: h('input', { type: 'checkbox', checked: !!s.auto_apply_advisor_targets }),
      budget: input({ type: 'number', min: 1, max: 500, step: 1, value: s.advisor_budget_usd ?? 40 }),
      timezone: input({ value: s.timezone || '', placeholder: 'America/New_York' }),
      notify_service: select(phoneOpts('Nobody extra'), s.notify_service || ''), admin: select(phoneOpts('The first plant\'s phone'), s.admin_notify_service || ''),
      model: select(models.map((m) => ({ value: m, label: m })), s.model || models[0]),
      temp_offset_c: input({ type: 'number', step: '0.1', inputmode: 'decimal', value: s.temp_offset_c ?? 0 }), humidity_offset: input({ type: 'number', step: '0.5', inputmode: 'decimal', value: s.humidity_offset ?? 0 }),
      price: input({ type: 'number', step: '0.001', min: 0, inputmode: 'decimal', value: s.price_per_kwh ?? '', placeholder: '0.15' }), currency: input({ value: s.currency || 'CAD', maxlength: 4 }),
      capture: input({ type: 'number', min: 1, max: 240, value: s.camera_capture_minutes ?? 30 }),
      tank: input({ type: 'number', min: 0.5, max: 48, step: 0.5, value: s.humidifier_tank_hours ?? 4 }),
    };
    const btn = saveBtn();
    replaceChildren(refs.prefs,
      h('form', { onsubmit: (e) => { e.preventDefault(); submitForm(btn, async () => {
        const body = { units: f.units.value, brief_time: f.brief_time.value, auto_apply_advisor_targets: f.auto.checked, advisor_budget_usd: Number(f.budget.value) || 40,
          timezone: f.timezone.value.trim(), notify_service: f.notify_service.value || null, admin_notify_service: f.admin.value || null, model: f.model.value,
          temp_offset_c: Number(f.temp_offset_c.value) || 0, humidity_offset: Number(f.humidity_offset.value) || 0, price_per_kwh: f.price.value === '' ? null : Number(f.price.value),
          currency: f.currency.value.trim() || 'CAD', camera_capture_minutes: Number(f.capture.value) || 30, humidifier_tank_hours: Number(f.tank.value) || 4 };
        settings = await api.put('/api/settings', body); ctx.setSettings(settings); renderPrefs(); renderTargets();
      }); } },
        h('p', { class: 'muted small' }, 'These apply to the whole tent, for both of you.'),
        h('div', { class: 'form-grid' }, field('Units', f.units), field('Morning brief at', f.brief_time), field('Monthly advisor budget ($)', f.budget, { hint: `Spent this month: $${Number(s.advisor_month_usd || 0).toFixed(2)}` }), h('label', { class: 'check' }, f.auto, 'Let the advisor fine-tune temperature and humidity')),
        h('details', { class: 'exp', style: { marginTop: '12px' } }, h('summary', null, 'Advanced (tent setup)'),
          h('div', { class: 'form-grid', style: { marginTop: '10px' } },
            field('Extra phone for every alert', f.notify_service, { hint: 'Each plant\'s own phone already gets alerts' }), field('Update notices go to', f.admin),
            field('Humidifier tank lasts (h of misting)', f.tank), field('Timezone', f.timezone), field('Advisor model', f.model),
            field('Temp offset (°C)', f.temp_offset_c, { hint: 'Added to the raw sensor reading' }), field('Humidity offset (%)', f.humidity_offset),
            field('Price per kWh', f.price), field('Currency', f.currency), field('Camera frame every (min)', f.capture))),
        h('div', { class: 'form-actions' }, btn)));
  }

  // ---------- set up a phone (QR) ----------
  let qrUrl = null;
  async function showQr() {
    const server = refs.qrUrl.value.trim();
    if (!server) { toast('Enter the add-on address first', 'error'); return; }
    try {
      const blob = await api.blob('/api/setup-qr.png?url=' + encodeURIComponent(server));
      if (qrUrl) URL.revokeObjectURL(qrUrl);
      qrUrl = URL.createObjectURL(blob);
      replaceChildren(refs.qrBox, h('img', { src: qrUrl, alt: 'Setup QR code', style: { width: '240px', height: '240px', borderRadius: '12px', background: '#fff', padding: '8px' } }),
        h('p', { class: 'muted small' }, 'Contains the address and the API key; only show it to people who should control the tent.'));
    } catch (e) { toast(errText(e), 'error'); }
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
    const keyName = MODE === 'hosted' ? 'Dashboard password' : 'API key';
    replaceChildren(refs.conn,
      h('div', { class: 'kv' },
        MODE === 'addon' ? [h('dt', null, 'Server'), h('dd', null, c.server || 'this page')] : [h('dt', null, 'Signed in'), h('dd', null, MODE === 'ingress' ? 'through Home Assistant' : 'with the dashboard password')],
        MODE !== 'ingress' ? [h('dt', null, keyName), h('dd', null, c.key ? '•'.repeat(Math.min(12, c.key.length)) : '—')] : null,
        h('dt', null, 'Version'), h('dd', null, refs.version)),
      MODE !== 'ingress' ? h('div', { class: 'form-actions', style: { justifyContent: 'flex-start' } }, h('button', { class: 'btn quiet', onclick: async () => { if (await confirmDialog({ title: 'Sign out?', message: `You will be asked for the ${keyName.toLowerCase()} again.`, confirmText: 'Sign out' })) { clearConn(); location.reload(); } } }, icon('key'), 'Sign out')) : null);
    api.get('/api/health').then((hh) => { refs.version.textContent = `Grow Brain add-on ${hh.version}${hh.advisor_enabled ? ' · advisor on' : ' · advisor off'}`; }).catch(() => {});
  }

  async function loadEvents() {
    try {
      const r = await api.get('/api/events?limit=100');
      if (!root) return;
      replaceChildren(refs.events, (r.events || []).length ? r.events.map((e) => h('div', { class: `event ${e.resolved_at ? 'resolved' : ''}` },
        h('span', { class: `dot ${e.resolved_at ? 'info' : e.level}` }), h('span', { class: 'kind' }, e.kind),
        h('span', null, e.message, e.resolved_at ? h('span', { class: 'chip good', style: { marginLeft: '6px' } }, 'cleared') : null),
        h('time', { datetime: e.at, title: e.at }, fmtDateTime(e.at)))) : h('div', { class: 'empty' }, 'No events yet.'));
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
    refs.qrUrl = input({ value: location.port === '8099' ? location.origin : 'http://homeassistant.local:8099', placeholder: 'http://homeassistant.local:8099' });
    refs.qrBox = h('div', { class: 'stack' });
    backupBtn.onclick = () => backup(backupBtn);
    const card = (title, ic, body, cls = '') => h('section', { class: `card ${cls}`.trim(), 'aria-label': title }, h('div', { class: 'card-head' }, h('h2', null, icon(ic), title)), body);
    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'Settings'), h('div', { class: 'date' }, 'Plants, tent, targets, camera and shared settings.'))),
      h('div', { class: 'settings-grid' },
        card('Plants', 'leaf', refs.plants, 'span2'),
        card('Tent', 'home', refs.tent), card('Targets', 'vpd', refs.targets),
        card('Camera', 'camera', refs.camera), card('Tent settings (shared)', 'gear', refs.prefs),
        card('Set up a phone', 'key', MODE === 'hosted'
          ? h('p', { class: 'muted small' }, 'For safety the setup QR code is only shown at home: open GrowOp from Home Assistant\'s sidebar, then Settings → Set up a phone.')
          : h('div', { class: 'stack' }, h('p', { class: 'muted small' }, 'On the phone, install GrowOp, join the home Wi-Fi, then point the phone\'s camera at this QR code: the app opens already connected. It works on the home Wi-Fi only.'), refs.qrUrl, h('div', { class: 'row' }, h('button', { class: 'btn', onclick: showQr }, icon('key'), 'Show QR code')), refs.qrBox)),
        card('Backup', 'archive', MODE === 'hosted'
          ? h('p', { class: 'muted small' }, 'Backups hold everything, so they can only be downloaded at home: open GrowOp from Home Assistant\'s sidebar. Home Assistant\'s own backups include GrowOp too.')
          : h('div', { class: 'stack' }, h('p', { class: 'muted small' }, 'A zip of the database and photos. Home Assistant\'s own backups include it too.'), h('div', null, backupBtn))),
        card('Connection', 'key', refs.conn),
        card('Events', 'list', refs.events, 'span2')));
    renderConnection(); loadAll();
  }
  function onStatus() { if (root && settings) renderPlants(); }
  function onSettings(s) { settings = s; }
  function unmount() { root = null; }
  return { mount, unmount, onStatus, onSettings, title: 'Settings' };
}

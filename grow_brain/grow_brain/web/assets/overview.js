// Overview page: glanceable tent status.
import { api } from './api.js';
import { icon, DEVICE_ICON, levelIcon } from './icons.js';
import {
  h, append, clear, replaceChildren, num, bandStatus, relTime, countdown, fmtDateLong, fmtTime, fmtDateTime, parseISO,
  cToF, capitalize, plantLabel, STAGE_NAMES, confirmDialog, chooseDialog, openModal, toast, spinner, notice, errText, select, segmented,
} from './util.js';
import { vitalChart, lightsFromPoints } from './charts.js';

const VITALS = {
  temp: { title: 'Temp', ic: 'thermo', decimals: 1, tol: (f) => (f ? 2.7 : 1.5), scale: (f) => (f ? [50, 104] : [10, 40]) },
  humidity: { title: 'Humidity', ic: 'humidity', unit: '%', decimals: 0, tol: () => 5, scale: () => [20, 90] },
  vpd: { title: 'VPD', ic: 'vpd', unit: 'kPa', decimals: 2, tol: () => 0.2, scale: () => [0, 2] },
};

function polar(cx, cy, r, deg) { const a = deg * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
function arcPath(cx, cy, r, a0, a1) {
  const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
  const large = a1 - a0 > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/** Ring gauge like the phones: 270° sweep from bottom-left, target band arc, marker dot, big number. */
function makeRing(spec) {
  const S = 120, cx = 60, cy = 60, r = 52, sweep = 270, start = 135;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${S} ${S}`);
  const track = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  track.setAttribute('class', 'track'); track.setAttribute('d', arcPath(cx, cy, r, start, start + sweep));
  track.setAttribute('fill', 'none'); track.setAttribute('stroke-width', '5'); track.setAttribute('stroke-linecap', 'round');
  const arc = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  arc.setAttribute('class', 'arc'); arc.setAttribute('fill', 'none'); arc.setAttribute('stroke-width', '9'); arc.setAttribute('stroke-linecap', 'round');
  const marker = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  marker.setAttribute('class', 'marker'); marker.setAttribute('r', '6.5'); marker.setAttribute('fill', 'currentColor');
  svg.append(track, arc, marker);
  const n = h('div', { class: 'n num' }, '—');
  const u = h('div', { class: 'u' }, spec.unit || '');
  const ring = h('div', { class: 'ring lvl-unknown', role: 'img' }, svg, h('div', { class: 'value' }, n, u));
  const bandEl = h('div', { class: 'band num' }, 'no target');
  const el = h('div', { class: 'vital' }, h('div', { class: 'title' }, icon(spec.ic), spec.title), ring, bandEl);

  function set({ value, min, max, unit, scaleMin, scaleMax, decimals, level, muted }) {
    const frac = (v) => Math.min(Math.max((v - scaleMin) / (scaleMax - scaleMin), 0), 1);
    ring.className = `ring lvl-${muted ? 'unknown' : level}`;
    u.textContent = unit;
    n.textContent = value == null ? '—' : num(value, decimals);
    if (min != null && max != null && max > min) { arc.setAttribute('d', arcPath(cx, cy, r, start + frac(min) * sweep, start + frac(max) * sweep)); arc.style.opacity = muted ? '0.25' : '0.85'; }
    else arc.removeAttribute('d');
    if (value != null) {
      const [mx, my] = polar(cx, cy, r, start + frac(value) * sweep);
      marker.setAttribute('cx', mx.toFixed(2)); marker.setAttribute('cy', my.toFixed(2)); marker.style.display = '';
    } else marker.style.display = 'none';
    bandEl.textContent = min != null && max != null ? `${num(min, decimals)}–${num(max, decimals)}` : 'no target';
    ring.setAttribute('aria-label', `${spec.title} ${value == null ? 'unknown' : num(value, decimals) + ' ' + unit}${min != null ? `, target ${num(min, decimals)} to ${num(max, decimals)}` : ''}, ${level}`);
  }
  return { el, set };
}

export function createOverview(ctx) {
  let root = null;
  let refs = {};
  let charts = {};
  let history = [];
  let historyTimer = null;
  let snapTimer = null;
  let snapAbort = null;
  let snapUrl = null;
  let ticker = null;
  let pop = null;
  let lastStatus = null;
  let modalOpen = false;

  const usesF = () => ctx.units() === 'f';

  // ---------- header ----------
  function renderHeader(s) {
    const standby = !!s.standby;
    const day = s.grow?.day_total;
    const stage = STAGE_NAMES[s.grow?.stage] || capitalize(s.grow?.stage || '');
    const strains = [...new Set((s.plants || []).map((p) => p.strain).filter(Boolean))];
    refs.hero.textContent = standby ? 'Tent is off' : (day != null ? `Day ${day}` : 'Your grow');
    refs.hero.className = `hero ${standby ? 'standby' : ''}`;
    refs.sub.textContent = [stage, strains.join(' & ')].filter(Boolean).join(' · ');
    refs.date.textContent = `${fmtDateLong(new Date())} · ${fmtTime(new Date())}`;

    const running = !standby;
    refs.pill.className = `tent-pill ${running ? 'running' : ''}`;
    refs.pill.setAttribute('aria-label', running ? 'Tent running. Turn off' : 'Tent is off. Start');
    replaceChildren(refs.pill,
      h('span', { class: `dot ${running ? 'on' : ''}` }),
      running ? 'Tent running' : 'Tent is off',
      h('span', { class: 'act' }, running ? 'Turn off' : 'Start', icon('power')));
  }

  async function togglePower() {
    const s = lastStatus; if (!s) return;
    if (!s.standby) {
      const ok = await confirmDialog({ title: 'Turn the tent off?', message: 'Every device switches off and stays off until you start it again.', confirmText: 'Turn off', cancelText: 'Keep running', danger: true, ic: 'power' });
      if (!ok) return;
      try { await api.post('/api/control/standby'); toast('Tent is off'); } catch (e) { toast(errText(e), 'error'); }
    } else {
      try { await api.post('/api/control/start'); toast('Tent started', 'ok'); } catch (e) { toast(errText(e), 'error'); }
    }
    ctx.refreshStatus();
  }

  // ---------- plants ----------
  function renderPlants(s) {
    const plants = s.plants || [];
    const stage = STAGE_NAMES[s.grow?.stage] || capitalize(s.grow?.stage || '');
    replaceChildren(refs.plants, plants.length ? plants.map((p) => h('div', { class: 'card plant-card' },
      h('div', { class: 'avatar' }, icon('leaf')),
      h('div', null,
        h('div', { class: 'name' }, p.name),
        h('div', { class: 'meta' }, [p.owner, p.day_total != null && p.start_date ? `Day ${p.day_total}` : 'Not started', stage].filter(Boolean).join(' · '))))) :
      h('div', { class: 'card plant-card muted' }, 'No plants yet — add them in Settings.'));
  }

  // ---------- vitals ----------
  function tempVals(s) {
    const f = usesF();
    const sensor = s.sensor || {}, t = s.targets || {};
    const value = f ? (sensor.temp_f ?? (sensor.temp_c != null ? cToF(sensor.temp_c) : null)) : sensor.temp_c;
    const min = f ? (t.temp_min_f ?? (t.temp_min_c != null ? cToF(t.temp_min_c) : null)) : t.temp_min_c;
    const max = f ? (t.temp_max_f ?? (t.temp_max_c != null ? cToF(t.temp_max_c) : null)) : t.temp_max_c;
    return { value, min, max };
  }

  function renderVitals(s) {
    const f = usesF();
    const muted = !!s.standby || !!s.sensor?.stale;
    const t = s.targets || {}, sensor = s.sensor || {};
    const tv = tempVals(s);
    const tScale = VITALS.temp.scale(f);
    refs.rings.temp.set({ ...tv, unit: f ? '°F' : '°C', scaleMin: tScale[0], scaleMax: tScale[1], decimals: 1, level: bandStatus(tv.value, tv.min, tv.max, VITALS.temp.tol(f)), muted });
    refs.rings.humidity.set({ value: sensor.humidity, min: t.humidity_min, max: t.humidity_max, unit: '%', scaleMin: 20, scaleMax: 90, decimals: 0, level: bandStatus(sensor.humidity, t.humidity_min, t.humidity_max, 5), muted });
    refs.rings.vpd.set({ value: sensor.vpd_kpa, min: t.vpd_min, max: t.vpd_max, unit: 'kPa', scaleMin: 0, scaleMax: 2, decimals: 2, level: bandStatus(sensor.vpd_kpa, t.vpd_min, t.vpd_max, 0.2), muted });
    replaceChildren(refs.vitalsMeta, sensor.stale
      ? h('span', { class: 'chip warn' }, icon('warn'), 'Sensor not reporting')
      : h('span', { class: 'faint tiny' }, sensor.updated_at ? relTime(sensor.updated_at) : ''));

    const a = s.assessment || {};
    const level = s.standby ? 'standby' : (a.level || 'warn');
    const cls = { good: 'lvl-good', warn: 'lvl-warn', alert: 'lvl-alert', standby: 'muted' }[level] || 'muted';
    refs.assess.className = `assess ${level === 'alert' ? 'alert' : ''}`;
    replaceChildren(refs.assess,
      h('div', { class: 'row', style: { gap: '10px' } }, icon(levelIcon(level), cls), h('span', { class: level === 'standby' ? 'muted' : '' }, s.standby ? 'Tent is off' : (a.headline || 'Waiting for the first reading'))),
      level === 'alert' && a.details?.length ? h('ul', null, a.details.map((d) => h('li', null, d))) : null);
    updateChartBands(s);
  }

  function chartSeries() {
    const f = usesF();
    const x = history.map((p) => parseISO(p.t).getTime() / 1000);
    return {
      x,
      temp: history.map((p) => (f ? (p.temp_f ?? (p.temp_c != null ? cToF(p.temp_c) : null)) : p.temp_c)),
      humidity: history.map((p) => p.humidity),
      vpd: history.map((p) => p.vpd_kpa),
      lights: lightsFromPoints(history),
    };
  }

  function updateChartBands(s) {
    const tv = tempVals(s), t = s.targets || {};
    const ser = chartSeries();
    const f = usesF();
    const cfg = {
      temp: { band: { min: tv.min, max: tv.max }, unit: f ? '°F' : '°C', decimals: 1, color: `--${bandStatus(tv.value, tv.min, tv.max, VITALS.temp.tol(f)) === 'unknown' ? 'primary' : bandStatus(tv.value, tv.min, tv.max, VITALS.temp.tol(f))}` },
      humidity: { band: { min: t.humidity_min, max: t.humidity_max }, unit: '%', decimals: 0, color: `--${bandStatus(s.sensor?.humidity, t.humidity_min, t.humidity_max, 5) === 'unknown' ? 'primary' : bandStatus(s.sensor?.humidity, t.humidity_min, t.humidity_max, 5)}` },
      vpd: { band: { min: t.vpd_min, max: t.vpd_max }, unit: 'kPa', decimals: 2, color: `--${bandStatus(s.sensor?.vpd_kpa, t.vpd_min, t.vpd_max, 0.2) === 'unknown' ? 'primary' : bandStatus(s.sensor?.vpd_kpa, t.vpd_min, t.vpd_max, 0.2)}` },
    };
    for (const k of Object.keys(cfg)) {
      const c = { ...cfg[k], x: ser.x, y: ser[k], lights: ser.lights, rangeHours: 24 };
      if (charts[k]) charts[k].update(c);
      else charts[k] = vitalChart(refs.chartEls[k], { ...c, height: k === 'vpd' ? 118 : 96, showX: k === 'vpd', syncKey: 'overview' });
      const last = ser[k].filter((v) => v != null);
      replaceChildren(refs.chartTitles[k], VITALS[k].title, h('b', { class: 'num' }, last.length ? `${num(last[last.length - 1], c.decimals)} ${c.unit}` : ''));
    }
  }

  async function loadHistory() {
    try {
      const r = await api.get('/api/history?hours=24&points=600');
      history = r.points || [];
      if (lastStatus) updateChartBands(lastStatus);
    } catch (e) { /* chart stays empty */ }
  }

  // ---------- light bar ----------
  function renderLight(s) {
    const t = s.targets || {}, l = s.light || {};
    const muted = !!s.standby;
    const lit = !!l.is_on && !muted;
    const parts = t.light_on_time ? t.light_on_time.split(':').map(Number) : null;
    const segs = [];
    if (parts && parts.length >= 2 && t.light_hours > 0) {
      const st = (parts[0] * 60 + parts[1]) / 1440, len = Math.min(t.light_hours / 24, 1), e = st + len;
      if (e <= 1) segs.push([st, e]); else segs.push([st, 1], [0, e - 1]);
    }
    const now = new Date(); const nowF = (now.getHours() * 60 + now.getMinutes()) / 1440;
    const detail = [];
    if (muted) detail.push('Standby');
    else if (l.next_change_at) detail.push(`${l.is_on ? 'Off in ' : 'On in '}${countdown(l.next_change_at)}`);
    if (l.schedule) detail.push(l.schedule);
    if (t.light_on_time) detail.push(`on at ${t.light_on_time}`);
    replaceChildren(refs.lightHead, icon(lit ? 'sun' : 'moon', lit ? 'lvl-sun' : ''), h('h2', null, muted ? 'Lights off' : (l.is_on ? 'Lights on' : 'Lights off')), h('span', { class: 'detail' }, detail.join(' · ')));
    refs.lightHead.querySelector('.ic').style.color = lit ? 'var(--sun)' : 'var(--night)';
    const bar = refs.lightBar; clear(bar);
    bar.style.opacity = muted ? '0.5' : '1';
    let biggest = null;
    for (const [a, b] of segs) { bar.append(h('div', { class: 'seg-on', style: { left: `${a * 100}%`, width: `${(b - a) * 100}%` } })); if (!biggest || b - a > biggest[1] - biggest[0]) biggest = [a, b]; }
    if (biggest && biggest[1] - biggest[0] > 0.12) bar.append(h('span', { class: 'glyph sun', style: { left: `${(biggest[0] + biggest[1]) / 2 * 100}%` } }, icon('sun', 'fill')));
    const gaps = []; let cur = 0;
    for (const [a, b] of [...segs].sort((p, q) => p[0] - q[0])) { if (a > cur) gaps.push([cur, a]); cur = Math.max(cur, b); }
    if (cur < 1) gaps.push([cur, 1]);
    const gap = gaps.sort((p, q) => (q[1] - q[0]) - (p[1] - p[0]))[0];
    if (gap && gap[1] - gap[0] > 0.12) bar.append(h('span', { class: 'glyph moon', style: { left: `${(gap[0] + gap[1]) / 2 * 100}%` } }, icon('moon', 'fill')));
    bar.append(h('div', { class: 'now', style: { left: `${nowF * 100}%` }, title: 'Now' }));
    refs.lightCard.classList.toggle('muted-card', muted);
  }

  // ---------- devices ----------
  function reasonLine(d, standby) {
    if (!d.entity_id) return 'Not set up';
    if (d.available === false) return 'Unavailable';
    if (standby) return 'Standby';
    if (d.mode && d.mode !== 'auto') return `Manual · ${d.mode}${d.reason ? ' · ' + d.reason : ''}`;
    if (d.reason) return d.reason;
    return d.state === 'on' ? 'On · automatic' : 'Off · automatic';
  }

  function renderDevices(s) {
    const devices = (s.devices || []).filter((d) => d.kind === 'switch' && d.entity_id);
    refs.devicesAll.textContent = s.standby ? 'All off' : '';
    replaceChildren(refs.devices, devices.length ? devices.map((d) => {
      const on = d.state === 'on' && !s.standby;
      const btn = h('button', { class: `device ${on ? 'on' : ''} ${s.standby ? 'dim' : ''}`, type: 'button', 'aria-label': `${d.label}, ${on ? 'on' : 'off'}. ${reasonLine(d, s.standby)}`, onclick: (e) => openDevicePopover(d, e.currentTarget) },
        h('span', { class: 'icon' }, icon(DEVICE_ICON[d.role] || 'plug'), h('span', { class: `dot ${d.available === false ? 'off' : on ? 'on' : 'idle'}` })),
        h('span', { class: 'body' }, h('div', { class: 'name' }, d.label), h('div', { class: 'why' }, reasonLine(d, s.standby))),
        d.power_w != null ? h('span', { class: 'watts num' }, `${Math.round(d.power_w)} W`) : null);
      return btn;
    }) : h('div', { class: 'empty' }, 'No devices mapped yet.'));
  }

  function closePopover() { if (pop) { pop.el.remove(); document.removeEventListener('mousedown', pop.outside); document.removeEventListener('keydown', pop.key); pop = null; } }

  function openDevicePopover(d, anchor) {
    closePopover();
    const s = lastStatus;
    const on = d.state === 'on' && !s.standby;
    const el = h('div', { class: 'pop', role: 'dialog', 'aria-label': `${d.label} controls` });
    const why = h('div', { class: 'why' }, s.standby ? 'The tent is in standby, so everything stays off.' : (d.reason || 'No reason reported.'));
    const status = h('div', { class: 'row' },
      h('span', { class: `chip ${d.available === false ? 'alert' : on ? 'good' : ''}` }, d.available === false ? 'Unavailable' : s.standby ? 'Off · standby' : (d.state === 'on' ? 'On' : d.state === 'off' ? 'Off' : 'Unknown')),
      d.mode && d.mode !== 'auto' ? h('span', { class: 'chip warn' }, 'Manual') : null,
      d.power_w != null ? h('span', { class: 'chip brand num' }, icon('zap'), `${d.power_w.toFixed(1)} W`) : null);
    const until = parseISO(d.override_until);
    const busy = h('div', { class: 'row small muted hidden' }, spinner(), 'Updating…');
    const durations = h('div', { class: 'durations hidden' });
    let pending = null;
    async function apply(mode, minutes) {
      busy.classList.remove('hidden');
      try {
        await api.post(`/api/devices/${d.role}/override`, minutes ? { mode, minutes } : { mode });
        toast(mode === 'auto' ? `${d.label}: automatic` : `${d.label}: ${mode}${minutes ? ` for ${minutes / 60} h` : ' until changed'}`, 'ok');
        closePopover(); ctx.refreshStatus();
      } catch (e) { toast(errText(e), 'error'); busy.classList.add('hidden'); }
    }
    const seg = segmented([{ label: 'Auto', value: 'auto' }, { label: 'On', value: 'on' }, { label: 'Off', value: 'off' }], d.mode || 'auto', (v) => {
      if (v === 'auto') { durations.classList.add('hidden'); apply('auto'); return; }
      pending = v;
      replaceChildren(durations,
        h('button', { class: 'btn ghost sm', onclick: () => apply(pending, 60) }, '1 hour'),
        h('button', { class: 'btn ghost sm', onclick: () => apply(pending, 240) }, '4 hours'),
        h('button', { class: 'btn ghost sm', onclick: () => apply(pending, null) }, 'Until changed'));
      durations.classList.remove('hidden');
    }, 'lg');
    append(el, [
      h('div', { class: 'head' }, h('span', { class: 'icon' }, icon(DEVICE_ICON[d.role] || 'plug')), h('div', null, h('h3', null, d.label), status)),
      h('div', null, h('div', { class: 'label' }, 'Why'), why, until ? h('div', { class: 'tiny lvl-warn row' }, icon('clock'), `Manual until ${fmtTime(until)}`) : null),
      h('div', null, h('div', { class: 'label', style: { marginBottom: '6px' } }, 'Mode'), seg, h('div', { class: 'tiny faint', style: { marginTop: '6px' } }, 'Auto lets the grow brain decide. On or Off holds it there for a while.')),
      durations, busy,
    ]);
    document.body.append(el);
    const r = anchor.getBoundingClientRect();
    const w = el.offsetWidth, hgt = el.offsetHeight;
    let left = Math.min(Math.max(12, r.left), window.innerWidth - w - 12);
    let top = r.bottom + 8;
    if (top + hgt > window.innerHeight - 12) top = Math.max(12, r.top - hgt - 8);
    el.style.left = `${left}px`; el.style.top = `${top}px`;
    const outside = (e) => { if (!el.contains(e.target) && !anchor.contains(e.target)) closePopover(); };
    const key = (e) => { if (e.key === 'Escape') { closePopover(); anchor.focus(); } };
    document.addEventListener('mousedown', outside); document.addEventListener('keydown', key);
    pop = { el, outside, key };
    seg.querySelector('button[aria-pressed="true"]')?.focus();
  }

  // ---------- camera ----------
  async function snap() {
    if (!root || document.visibilityState !== 'visible' || modalOpen) return;
    if (!lastStatus?.camera?.entity_id) return;
    snapAbort = new AbortController();
    try {
      const url = await api.blobUrl('/api/camera/snapshot', { signal: snapAbort.signal });
      if (!root) { URL.revokeObjectURL(url); return; }
      refs.camImg.src = url;
      refs.camImg.classList.remove('hidden'); refs.camEmpty.classList.add('hidden');
      if (snapUrl) URL.revokeObjectURL(snapUrl);
      snapUrl = url;
      refs.camTime.textContent = fmtTime(new Date());
    } catch (e) { if (e.name !== 'AbortError') refs.camTime.textContent = 'no signal'; }
  }
  function startSnaps() { stopSnaps(); snap(); snapTimer = setInterval(snap, 5000); }
  function stopSnaps() { if (snapTimer) clearInterval(snapTimer); snapTimer = null; if (snapAbort) snapAbort.abort(); }

  function renderCamera(s) {
    const cam = s.camera;
    if (!cam || !cam.entity_id) {
      refs.camImg.classList.add('hidden'); refs.camEmpty.classList.remove('hidden');
      replaceChildren(refs.camEmpty, icon('camera'), 'No camera selected', h('span', { class: 'tiny' }, 'Pick one in Settings'));
      refs.camName.textContent = 'Camera'; refs.camLive.classList.add('hidden');
      return;
    }
    refs.camName.textContent = cam.name || 'Tent camera';
    refs.camLive.classList.toggle('hidden', cam.available === false);
    refs.camFrames.textContent = cam.frame_count ? `${cam.frame_count} timelapse frames` : (cam.error || '');
    if (cam.available === false) { refs.camEmpty.classList.remove('hidden'); replaceChildren(refs.camEmpty, icon('camera'), cam.error || 'Camera unavailable'); }
  }

  async function openTimelapse() {
    if (!lastStatus?.camera?.entity_id) { ctx.navigate('#/settings'); return; }
    modalOpen = true; stopSnaps();
    const cache = new Map();
    let frames = [], filtered = [], idx = 0, playing = false, playTimer = null, live = false, liveTimer = null, liveUrl = null, range = 168;
    const img = h('img', { alt: 'Tent camera frame' });
    const stamp = h('div', { class: 'stamp' }, '…');
    const stage = h('div', { class: 'stage' }, img, stamp);
    const slider = h('input', { type: 'range', class: 'range', min: 0, max: 0, value: 0, 'aria-label': 'Timelapse position' });
    const playBtn = h('button', { class: 'btn icon ghost', 'aria-label': 'Play' }, icon('play'));
    const liveBtn = h('button', { class: 'btn sm quiet' }, icon('camera'), 'Live');
    const countEl = h('span', { class: 'tiny faint num' });
    const rangeSeg = segmented([{ label: '24 h', value: 24 }, { label: '7 d', value: 168 }], range, (v) => { range = v; applyFilter(); });
    const analysisBox = h('div', { class: 'analysis' });
    const plants = lastStatus.plants || [];
    const plantSel = select([{ value: '', label: 'Whole tent' }, ...plants.map((p) => ({ value: p.id, label: p.name }))], plants[0]?.id ?? '', { 'aria-label': 'Plant to look at' });
    const askBtn = h('button', { class: 'btn' }, icon('sparkles'), 'Ask the advisor to look now');

    async function loadFrame(f) {
      if (cache.has(f.id)) return cache.get(f.id);
      const url = await api.blobUrl(f.url || `/api/camera/frames/${f.id}`);
      cache.set(f.id, url);
      return url;
    }
    async function show(i) {
      if (!filtered.length) return;
      idx = Math.min(Math.max(0, i), filtered.length - 1);
      slider.value = idx;
      const f = filtered[idx];
      const d = parseISO(f.t);
      stamp.textContent = `${d ? fmtDateTime(f.t) : ''}${f.lights_on ? ' · lights on' : ' · lights off'}`;
      countEl.textContent = `${idx + 1} / ${filtered.length}`;
      try { img.src = await loadFrame(f); } catch { /* skip */ }
      for (let k = 1; k <= 3; k++) if (filtered[idx + k]) loadFrame(filtered[idx + k]).catch(() => {});
    }
    function applyFilter() {
      const since = Date.now() - range * 3600 * 1000;
      filtered = frames.filter((f) => (parseISO(f.t)?.getTime() || 0) >= since);
      slider.max = Math.max(0, filtered.length - 1);
      slider.disabled = filtered.length < 2;
      stopLive();
      show(filtered.length - 1);
    }
    function stopPlay() { playing = false; if (playTimer) clearInterval(playTimer); playTimer = null; replaceChildren(playBtn, icon('play')); playBtn.setAttribute('aria-label', 'Play'); }
    function startPlay() {
      if (filtered.length < 2) return;
      stopLive(); playing = true; replaceChildren(playBtn, icon('pause')); playBtn.setAttribute('aria-label', 'Pause');
      if (idx >= filtered.length - 1) idx = -1;
      playTimer = setInterval(() => { if (idx >= filtered.length - 1) { stopPlay(); return; } show(idx + 1); }, 1000 / 6);
    }
    async function liveTick() {
      if (!live) return;
      try { const u = await api.blobUrl('/api/camera/snapshot'); if (liveUrl) URL.revokeObjectURL(liveUrl); liveUrl = u; if (live) { img.src = u; stamp.textContent = `Live · ${fmtTime(new Date())}`; } } catch { /* retry */ }
    }
    function startLive() { stopPlay(); live = true; liveBtn.className = 'btn sm'; liveTick(); liveTimer = setInterval(liveTick, 2000); }
    function stopLive() { live = false; liveBtn.className = 'btn sm quiet'; if (liveTimer) clearInterval(liveTimer); liveTimer = null; }

    playBtn.onclick = () => (playing ? stopPlay() : startPlay());
    liveBtn.onclick = () => (live ? (stopLive(), show(idx)) : startLive());
    slider.oninput = () => { stopPlay(); stopLive(); show(Number(slider.value)); };
    askBtn.onclick = async () => {
      askBtn.disabled = true; replaceChildren(analysisBox, h('div', { class: 'row muted small' }, spinner(), 'Taking a snapshot and asking the advisor… this can take up to a minute.'));
      try {
        const pid = plantSel.value ? Number(plantSel.value) : null;
        const photo = await api.post('/api/camera/analyse', { plant_id: pid });
        replaceChildren(analysisBox, renderAnalysis(photo.analysis));
      } catch (e) { replaceChildren(analysisBox, notice(errText(e), 'alert')); }
      askBtn.disabled = false;
    };

    const body = h('div', { class: 'tl' },
      h('div', null, stage, h('div', { class: 'controls' },
        h('div', { class: 'row' }, playBtn, slider, countEl),
        h('div', { class: 'row', style: { justifyContent: 'space-between' } }, h('div', { class: 'row' }, rangeSeg, liveBtn), h('span', { class: 'tiny faint' }, '← → step · space play')))),
      h('div', { class: 'side' },
        h('h3', null, 'Ask the advisor'),
        h('div', { class: 'stack' }, plantSel, askBtn),
        analysisBox,
        h('div', { class: 'tiny faint' }, 'Frames are captured every ' + (ctx.getSettings()?.camera_capture_minutes || 30) + ' minutes and kept for 14 days.')));
    const m = openModal({ title: lastStatus.camera.name || 'Tent camera', body, size: 'wide', onClose: () => {
      stopPlay(); stopLive(); for (const u of cache.values()) URL.revokeObjectURL(u); if (liveUrl) URL.revokeObjectURL(liveUrl);
      modalOpen = false; if (root) startSnaps();
    } });
    m.el.addEventListener('keydown', (e) => {
      if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT' && e.target.type !== 'range' || e.target.tagName === 'SELECT') return;
      if (e.key === 'ArrowLeft') { e.preventDefault(); stopPlay(); stopLive(); show(idx - 1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); stopPlay(); stopLive(); show(idx + 1); }
      else if (e.key === ' ') { e.preventDefault(); playing ? stopPlay() : startPlay(); }
    });
    try {
      const r = await api.get('/api/camera/frames?days=7');
      frames = (r.frames || []).slice().sort((a, b) => (parseISO(a.t)?.getTime() || 0) - (parseISO(b.t)?.getTime() || 0));
      if (!frames.length) { stamp.textContent = 'No timelapse frames yet — showing live'; startLive(); }
      else applyFilter();
    } catch (e) { stamp.textContent = errText(e); startLive(); }
  }

  // ---------- needs you / alerts ----------
  function renderNeeds(s) {
    const items = [];
    if (s.unread_brief) items.push(h('a', { class: 'pill night', href: '#/advisor' }, icon('sparkles'), 'New brief'));
    if (s.open_photo_requests > 0) items.push(h('a', { class: 'pill', href: '#/journal?filter=request' }, icon('camera'), s.open_photo_requests === 1 ? '1 photo request' : `${s.open_photo_requests} photo requests`));
    if (s.open_tasks > 0) items.push(h('a', { class: 'pill', href: '#/journal?filter=task' }, icon('list'), s.open_tasks === 1 ? '1 task' : `${s.open_tasks} tasks`));
    refs.needsCard.classList.toggle('hidden', !items.length);
    replaceChildren(refs.needs, items);
  }

  function renderAlerts(s) {
    const alerts = s.alerts || [];
    const extra = [];
    if (s.control_paused_until) extra.push({ level: 'warn', message: `Automation paused until ${fmtTime(parseISO(s.control_paused_until))}`, at: null });
    if (!s.ha_connected) extra.push({ level: 'alert', message: "Can't reach Home Assistant", at: null });
    const all = [...extra, ...alerts];
    refs.alertsCard.classList.toggle('hidden', !all.length);
    replaceChildren(refs.alerts, all.map((a) => h('div', { class: 'alert-item' }, icon(levelIcon(a.level), `lvl-${a.level}`), h('span', null, a.message), a.at ? h('time', { datetime: a.at }, relTime(a.at)) : null)));
  }

  // ---------- lifecycle ----------
  function mount(el) {
    root = el; refs = {}; charts = {};
    refs.hero = h('h1', { class: 'hero' }, '…');
    refs.sub = h('div', { class: 'sub' });
    refs.date = h('div', { class: 'date' });
    refs.pill = h('button', { class: 'tent-pill', type: 'button', onclick: togglePower });
    refs.plants = h('div', { class: 'plants' });
    refs.rings = { temp: makeRing(VITALS.temp), humidity: makeRing(VITALS.humidity), vpd: makeRing(VITALS.vpd) };
    refs.vitalsMeta = h('div');
    refs.assess = h('div', { class: 'assess', 'aria-live': 'polite' });
    refs.chartEls = {}; refs.chartTitles = {};
    const minis = h('div', { class: 'mini-charts' });
    for (const k of ['temp', 'humidity', 'vpd']) {
      refs.chartEls[k] = h('div', { class: 'chart' });
      refs.chartTitles[k] = h('div', { class: 'mc-title' }, VITALS[k].title);
      minis.append(h('div', { class: 'mini-chart' }, refs.chartTitles[k], refs.chartEls[k]));
    }
    refs.lightHead = h('div', { class: 'lightbar-head' });
    refs.lightBar = h('div', { class: 'lightbar', role: 'img', 'aria-label': 'Light schedule for today' });
    refs.lightCard = h('div', { class: 'card tight' }, refs.lightHead, refs.lightBar,
      h('div', { class: 'lightbar-ticks', 'aria-hidden': 'true' }, ['12am', '6am', '12pm', '6pm', '12am'].map((t) => h('span', null, t))));
    refs.devices = h('div', { class: 'devices' });
    refs.devicesAll = h('span', { class: 'small muted' });
    refs.camImg = h('img', { class: 'hidden', alt: 'Live view of the tent' });
    refs.camEmpty = h('div', { class: 'no-cam' });
    refs.camLive = h('span', { class: 'live' }, h('span', { class: 'dot' }), 'LIVE');
    refs.camName = h('b');
    refs.camFrames = h('span');
    refs.camTime = h('span', { class: 'num' });
    const camera = h('button', { class: 'card camera', type: 'button', 'aria-label': 'Open the tent camera and timelapse', onclick: openTimelapse },
      h('div', { class: 'frame' }, refs.camImg, refs.camEmpty, refs.camLive,
        h('div', { class: 'cap' }, h('div', null, refs.camName, refs.camFrames), h('div', { style: { textAlign: 'right' } }, refs.camTime, h('div', { class: 'tiny', style: { opacity: 0.8 } }, 'Tap for timelapse')))));
    refs.needs = h('div', { class: 'needs' });
    refs.needsCard = h('div', { class: 'card tight hidden' }, h('div', { class: 'card-head' }, h('h2', null, 'Needs you')), refs.needs);
    refs.alerts = h('div', { class: 'alerts' });
    refs.alertsCard = h('div', { class: 'card tight hidden' }, h('div', { class: 'card-head' }, h('h2', null, icon('bell'), 'Alerts')), refs.alerts);

    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, refs.hero, refs.sub, refs.date), refs.pill),
      refs.plants,
      h('div', { class: 'overview-grid' },
        h('div', { class: 'col' },
          h('div', { class: 'card' },
            h('div', { class: 'card-head' }, h('h2', null, 'Vitals'), refs.vitalsMeta),
            h('div', { class: 'vitals-rings' }, refs.rings.temp.el, refs.rings.humidity.el, refs.rings.vpd.el),
            refs.assess,
            minis,
            h('div', { class: 'chart-legend' }, h('span', null, h('i', { style: { background: 'var(--primary-tint)' } }), 'target band'), h('span', null, h('i', { style: { background: 'var(--sun-tint)' } }), 'lights on'), h('span', { class: 'faint' }, 'last 24 h'))),
          h('div', null, h('div', { class: 'section-title' }, 'Devices', refs.devicesAll), refs.devices)),
        h('div', { class: 'col' }, camera, refs.lightCard, refs.needsCard, refs.alertsCard)));

    const s = ctx.getStatus();
    if (s) onStatus(s);
    loadHistory();
    historyTimer = setInterval(loadHistory, 5 * 60 * 1000);
    startSnaps();
    ticker = setInterval(() => { if (lastStatus) { renderLight(lastStatus); refs.date.textContent = `${fmtDateLong(new Date())} · ${fmtTime(new Date())}`; } }, 30 * 1000);
    document.addEventListener('visibilitychange', onVis);
    window.addEventListener('growop:theme', onTheme);
  }

  function onVis() { if (!root) return; if (document.visibilityState === 'visible') startSnaps(); else stopSnaps(); }
  function onTheme() { for (const c of Object.values(charts)) c.rebuild(); }

  function onStatus(s) {
    lastStatus = s;
    if (!root) return;
    renderHeader(s); renderPlants(s); renderVitals(s); renderLight(s); renderDevices(s); renderCamera(s); renderNeeds(s); renderAlerts(s);
  }

  function onSettings() { if (lastStatus && root) { renderVitals(lastStatus); } }

  function unmount() {
    stopSnaps(); closePopover();
    if (historyTimer) clearInterval(historyTimer); if (ticker) clearInterval(ticker);
    for (const c of Object.values(charts)) c.destroy();
    if (snapUrl) URL.revokeObjectURL(snapUrl); snapUrl = null;
    document.removeEventListener('visibilitychange', onVis);
    window.removeEventListener('growop:theme', onTheme);
    root = null; charts = {}; refs = {};
  }

  return { mount, unmount, onStatus, onSettings, title: 'Overview' };
}

/** Photo analysis block (shared with the journal). */
export function renderAnalysis(a) {
  if (!a) return h('div', { class: 'muted small' }, 'No analysis yet.');
  const sevCls = { info: 'brand', warn: 'warn', alert: 'alert' };
  return h('div', { class: 'analysis' },
    h('div', { class: 'row' }, a.health_score != null ? h('span', { class: `score lvl-${a.health_score >= 7 ? 'good' : a.health_score >= 4 ? 'warn' : 'alert'}` }, `${a.health_score}/10`) : null, h('span', null, a.summary || '')),
    a.findings?.length ? h('div', { class: 'stack' }, a.findings.map((f) => h('div', { class: 'finding' }, h('div', { class: 't' }, h('span', { class: `chip ${sevCls[f.severity] || ''}` }, f.severity), f.title), h('div', { class: 'small muted' }, f.detail)))) : null,
    a.actions?.length ? h('div', null, h('div', { class: 'label' }, 'What to do'), h('ul', { class: 'clean' }, a.actions.map((x) => h('li', null, x)))) : null);
}

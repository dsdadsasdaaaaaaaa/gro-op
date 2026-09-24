// History page: 24 h / 7 d / 30 d charts, stats, device timeline, energy.
import { api, isMissing } from './api.js';
import { icon, DEVICE_ICON } from './icons.js';
import { h, replaceChildren, num, cToF, parseISO, segmented, spinner, notice, errText } from './util.js';
import { vitalChart, lightsFromPoints, deviceTimeline } from './charts.js';

const RANGES = [{ label: '24 h', value: 24 }, { label: '7 d', value: 168 }, { label: '30 d', value: 720 }];

export function createHistory(ctx) {
  let root = null, refs = {}, charts = {}, hours = 24, points = [], devEvents = null, energy = null, loading = false;
  const usesF = () => ctx.units() === 'f';

  function bands() {
    const s = ctx.getStatus() || {}; const t = s.targets || {}; const f = usesF();
    return {
      temp: { min: f ? (t.temp_min_f ?? (t.temp_min_c != null ? cToF(t.temp_min_c) : null)) : t.temp_min_c, max: f ? (t.temp_max_f ?? (t.temp_max_c != null ? cToF(t.temp_max_c) : null)) : t.temp_max_c },
      humidity: { min: t.humidity_min, max: t.humidity_max },
      vpd: { min: t.vpd_min, max: t.vpd_max },
    };
  }

  /** The day band from status, or the night band derived the same way the controller does. */
  function bandAt(k, lightsOn) {
    const s = ctx.getStatus() || {}; const d = s.day_targets || s.targets || {}; const f = usesF();
    const conv = (c) => (c == null ? null : f ? cToF(c) : c);
    if (k === 'humidity') return { min: d.humidity_min, max: d.humidity_max };
    if (k === 'vpd') return { min: d.vpd_min, max: d.vpd_max };
    const drop = d.night_temp_drop_c || 0;
    if (lightsOn || !drop) return { min: conv(d.temp_min_c), max: conv(d.temp_max_c) };
    return { min: conv(Math.min(d.temp_min_c - drop, 18)), max: conv(d.temp_max_c - drop + 1) };
  }

  function series() {
    const f = usesF();
    return {
      x: points.map((p) => parseISO(p.t).getTime() / 1000),
      temp: points.map((p) => (f ? (p.temp_f ?? (p.temp_c != null ? cToF(p.temp_c) : null)) : p.temp_c)),
      humidity: points.map((p) => p.humidity),
      vpd: points.map((p) => p.vpd_kpa),
      lights: lightsFromPoints(points),
    };
  }

  function renderCharts() {
    const ser = series(), b = bands(), f = usesF();
    const cfg = {
      temp: { unit: f ? '°F' : '°C', decimals: 1, color: '--good' },
      humidity: { unit: '%', decimals: 0, color: '--primary' },
      vpd: { unit: 'kPa', decimals: 2, color: '--night' },
    };
    for (const k of Object.keys(cfg)) {
      const c = { ...cfg[k], x: ser.x, y: ser[k], band: b[k], lights: ser.lights, rangeHours: hours };
      if (charts[k]) charts[k].update(c); else charts[k] = vitalChart(refs.chartEls[k], { ...c, height: 190, showX: true, syncKey: 'history' });
      refs.bandLabels[k].textContent = b[k].min != null ? `target ${num(b[k].min, c.decimals)}–${num(b[k].max, c.decimals)} ${c.unit}` : '';
    }
    refs.chartsEmpty.classList.toggle('hidden', points.length > 0);
  }

  function renderStats() {
    const ser = series(), b = bands(), f = usesF();
    const rows = [['temp', `Temp (${f ? '°F' : '°C'})`, 1], ['humidity', 'Humidity (%)', 0], ['vpd', 'Air dryness, VPD (kPa)', 2]];
    const span = ser.x.length > 1 ? (ser.x[ser.x.length - 1] - ser.x[0]) / 3600 : 0;
    const lightPts = points.filter((p) => p.light_on).length;
    const lightHours = points.length ? span * lightPts / points.length : 0;
    const table = h('table', { class: 'stats' },
      h('thead', null, h('tr', null, h('th', null, 'Vital'), h('th', null, 'Min'), h('th', null, 'Avg'), h('th', null, 'Max'), h('th', null, 'In band'))),
      h('tbody', null, rows.map(([k, label, d]) => {
        const vals = ser[k].filter((v) => v != null);
        if (!vals.length) return h('tr', null, h('td', null, label), h('td', null, '—'), h('td', null, '—'), h('td', null, '—'), h('td', null, '—'));
        const min = Math.min(...vals), max = Math.max(...vals), avg = vals.reduce((a, v) => a + v, 0) / vals.length;
        // each reading is judged against the band that applied then: day band with the lights on, night band without
        let hit = 0, n = 0;
        ser[k].forEach((v, i) => {
          if (v == null) return;
          const band = bandAt(k, points[i]?.light_on);
          if (band.min == null) return;
          n += 1; if (v >= band.min && v <= band.max) hit += 1;
        });
        const inBand = n ? hit / n * 100 : null;
        return h('tr', null, h('td', null, label), h('td', null, num(min, d)), h('td', null, num(avg, d)), h('td', null, num(max, d)),
          h('td', { class: inBand == null ? '' : inBand >= 80 ? 'lvl-good' : inBand >= 50 ? 'lvl-warn' : 'lvl-alert' }, inBand == null ? '—' : `${Math.round(inBand)}%`));
      }),
      h('tr', null, h('td', null, 'Lights on'), h('td', { colspan: 3 }, ''), h('td', null, `${num(lightHours, 1)} h`))));
    replaceChildren(refs.stats, points.length ? table : h('div', { class: 'empty' }, 'No readings in this range yet.'));
  }

  function renderTimeline() {
    const s = ctx.getStatus() || {};
    const labels = Object.fromEntries((s.devices || []).map((d) => [d.role, d.label]));
    if (devEvents === null) { replaceChildren(refs.timeline, notice("Device history needs a newer Grow Brain add-on.", 'info')); return; }
    const end = Date.now() / 1000, start = end - hours * 3600;
    refs.timeline.className = '';
    deviceTimeline(refs.timeline, { events: devEvents, labels, start, end });
  }

  function renderEnergy() {
    if (energy === null) { replaceChildren(refs.energy, notice("Energy data needs a newer Grow Brain add-on.", 'info')); return; }
    const cur = energy.currency || '';
    const money = (v) => (v == null ? null : `${cur ? cur + ' ' : ''}${v.toFixed(2)}`);
    const tiles = h('div', { class: 'tiles' },
      h('div', { class: 'tile' }, h('div', { class: 'k' }, 'Today'), h('div', { class: 'v' }, num(energy.today_kwh, 2), h('small', null, 'kWh'))),
      h('div', { class: 'tile' }, h('div', { class: 'k' }, 'This month'), h('div', { class: 'v' }, num(energy.month_kwh, 1), h('small', null, 'kWh'))),
      energy.today_cost != null ? h('div', { class: 'tile' }, h('div', { class: 'k' }, 'Cost today'), h('div', { class: 'v' }, money(energy.today_cost))) : null,
      energy.month_cost != null ? h('div', { class: 'tile' }, h('div', { class: 'k' }, 'Cost this month'), h('div', { class: 'v' }, money(energy.month_cost))) : null);
    const devs = (energy.devices || []).slice().sort((a, b) => (b.month_kwh || 0) - (a.month_kwh || 0));
    const maxM = Math.max(0.001, ...devs.map((d) => d.month_kwh || 0));
    const rows = h('div', { class: 'energy-rows' },
      h('div', { class: 'energy-row energy-head' }, h('span'), h('span', null, 'Device'), h('span', { class: 'r' }, 'Now'), h('span', { class: 'r' }, 'Today'), h('span', { class: 'r month' }, 'Month')),
      devs.map((d) => h('div', { class: 'energy-row' },
        icon(DEVICE_ICON[d.role] || 'plug', 'muted'),
        h('div', null, h('div', { class: 'nm', title: d.label || d.role }, d.label || d.role), h('div', { class: 'bar' }, h('i', { style: { width: `${(d.month_kwh || 0) / maxM * 100}%` } }))),
        h('span', { class: 'r' }, d.power_w != null ? h('b', null, `${Math.round(d.power_w)} W`) : '—'),
        h('span', { class: 'r' }, d.today_kwh != null ? `${num(d.today_kwh, 2)} kWh` : '—'),
        h('span', { class: 'r month' }, d.month_kwh != null ? `${num(d.month_kwh, 1)} kWh` : '—'))));
    replaceChildren(refs.energy, tiles, devs.length ? rows : h('div', { class: 'empty' }, 'No plugs report power yet.'),
      energy.price_per_kwh == null ? h('div', { class: 'tiny faint', style: { marginTop: '10px' } }, 'Set a price per kWh in Settings to see costs.') : null);
  }

  async function load() {
    if (!root) return;
    loading = true; refs.loading.classList.remove('hidden');
    const pts = hours <= 24 ? 600 : hours <= 168 ? 1500 : 3000;
    const [hist, dev, en] = await Promise.allSettled([
      api.get(`/api/history?hours=${hours}&points=${pts}`),
      api.get(`/api/devices/history?hours=${hours}`),
      api.get('/api/energy'),
    ]);
    if (!root) return;
    if (hist.status === 'fulfilled') points = hist.value.points || []; else { points = []; replaceChildren(refs.chartsEmpty, notice(errText(hist.reason), 'alert')); }
    devEvents = dev.status === 'fulfilled' ? (dev.value.events || []) : (isMissing(dev.reason) ? null : []);
    if (dev.status === 'rejected' && !isMissing(dev.reason)) replaceChildren(refs.timeline, notice(errText(dev.reason), 'alert'));
    energy = en.status === 'fulfilled' ? en.value : null;
    renderCharts(); renderStats(); renderTimeline(); renderEnergy();
    loading = false; refs.loading.classList.add('hidden');
  }

  function mount(el) {
    root = el; refs = {}; charts = {};
    refs.loading = h('span', { class: 'row muted small' }, spinner(), 'Loading…');
    refs.chartEls = {}; refs.bandLabels = {};
    const chartCards = ['temp', 'humidity', 'vpd'].map((k) => {
      refs.chartEls[k] = h('div', { class: 'chart' });
      refs.bandLabels[k] = h('span', { class: 'band num' });
      return h('div', { class: 'card tight chart-card' }, h('h3', null, { temp: 'Temperature', humidity: 'Humidity', vpd: 'VPD' }[k], refs.bandLabels[k]), refs.chartEls[k]);
    });
    refs.chartsEmpty = h('div', { class: 'empty hidden' }, 'No readings in this range yet.');
    refs.stats = h('div');
    refs.timeline = h('div');
    refs.energy = h('div');
    const seg = segmented(RANGES, hours, (v) => { hours = v; load(); }, 'lg');
    replaceChildren(root,
      h('header', { class: 'page-head' }, h('div', null, h('h1', null, 'History'), h('div', { class: 'date' }, 'Temperature, humidity and VPD against their targets; lights-on periods shaded.')), h('div', { class: 'row' }, refs.loading, seg)),
      h('div', { class: 'charts' }, chartCards, refs.chartsEmpty,
        h('div', { class: 'chart-legend' }, h('span', null, h('i', { style: { background: 'var(--primary-tint)' } }), 'target band'), h('span', null, h('i', { style: { background: 'var(--sun-tint)' } }), 'lights on'))),
      h('div', { class: 'grid grid-2 history-grid' },
        h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, 'Stats')), refs.stats),
        h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, icon('zap'), 'Energy')), refs.energy)),
      h('div', { class: 'card' }, h('div', { class: 'card-head' }, h('h2', null, 'Device timeline'), h('span', { class: 'tiny faint' }, 'when GrowOp switched things on')), refs.timeline));
    load();
    window.addEventListener('growop:theme', onTheme);
  }
  function onTheme() { for (const c of Object.values(charts)) c.rebuild(); }
  let statusKey = '';
  function onStatus(s) {
    // Targets and device labels come from status; re-render when they first arrive or change.
    const key = JSON.stringify([s.targets, (s.devices || []).map((d) => d.label)]);
    if (key === statusKey) return;
    statusKey = key;
    if (root && !loading && (points.length || devEvents)) { renderCharts(); renderStats(); renderTimeline(); }
  }
  function onSettings() { if (root && !loading) { renderCharts(); renderStats(); } }
  function unmount() { for (const c of Object.values(charts)) c.destroy(); charts = {}; root = null; window.removeEventListener('growop:theme', onTheme); }
  return { mount, unmount, onStatus, onSettings, title: 'History' };
}

// Charts: uPlot line charts with target-band + lights-on shading, and a device timeline.
import { h, cssVar, num, fmtTime, fmtDateShort, parseISO } from './util.js';
import { icon, DEVICE_ICON } from './icons.js';

const FONT = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

export function hasUPlot() { return typeof window.uPlot === 'function'; }

/** Lights-on intervals [[startSec, endSec], ...] from history points. */
export function lightsFromPoints(points) {
  const out = [];
  let start = null;
  let lastT = null;
  for (const p of points) {
    const t = parseISO(p.t)?.getTime() / 1000;
    if (!t) continue;
    if (p.light_on && start == null) start = t;
    if (!p.light_on && start != null) { out.push([start, t]); start = null; }
    lastT = t;
  }
  if (start != null && lastT != null) out.push([start, Math.max(lastT, Date.now() / 1000)]);
  return out;
}

function fmtTick(ts, rangeHours) {
  const d = new Date(ts * 1000);
  if (rangeHours <= 36) {
    const s = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: d.getMinutes() ? '2-digit' : undefined }).format(d);
    return s.replace(' ', '').toLowerCase();
  }
  if (rangeHours <= 24 * 8) {
    if (d.getHours() === 0 && d.getMinutes() === 0) return new Intl.DateTimeFormat(undefined, { weekday: 'short', day: 'numeric' }).format(d);
    return new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric' }).format(d).replace(' ', ' ').toLowerCase();
  }
  return fmtDateShort(d);
}

function tintOf(varName, alpha) {
  const v = cssVar(varName);
  const m = v.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
  }
  return v;
}

/**
 * A single-series time chart.
 * cfg: { x:[sec], y:[val], color:'--good', unit, decimals, band:{min,max}|null, lights:[[s,e]], height, showX, rangeHours, syncKey, label }
 */
export function vitalChart(el, cfg) {
  let u = null;
  let tip = null;
  let ro = null;
  let current = { ...cfg };

  function build() {
    if (!hasUPlot()) { el.textContent = 'Charts unavailable (uPlot failed to load).'; return; }
    el.classList.add('chart');
    const width = Math.max(120, el.clientWidth || 300);
    const stroke = cssVar(current.color || '--primary');
    const text3 = cssVar('--text-3');
    const line = cssVar('--line');
    const sunTint = cssVar('--sun-tint');
    const bandTint = cssVar('--primary-tint');
    const band = current.band && current.band.min != null && current.band.max != null ? current.band : null;
    const rangeHours = current.rangeHours || 24;
    const decimals = current.decimals ?? 1;

    const shade = (u) => {
      const ctx = u.ctx; const { left, top, width, height } = u.bbox;
      ctx.save(); ctx.beginPath(); ctx.rect(left, top, width, height); ctx.clip();
      for (const [a, b] of current.lights || []) {
        const x0 = Math.max(left, u.valToPos(a, 'x', true));
        const x1 = Math.min(left + width, u.valToPos(b, 'x', true));
        if (x1 > x0) { ctx.fillStyle = sunTint; ctx.fillRect(x0, top, x1 - x0, height); }
      }
      if (band) {
        const y0 = u.valToPos(band.max, 'y', true), y1 = u.valToPos(band.min, 'y', true);
        ctx.fillStyle = bandTint; ctx.fillRect(left, y0, width, y1 - y0);
      }
      ctx.restore();
    };

    const opts = {
      width, height: current.height || 160,
      padding: [10, 14, current.showX ? 0 : 4, 0],
      legend: { show: false },
      cursor: {
        drag: { x: false, y: false }, y: false,
        points: { size: 9, width: 2, stroke: stroke, fill: cssVar('--card') },
        sync: current.syncKey ? { key: current.syncKey, setSeries: false, scales: ['x', null] } : undefined,
      },
      scales: {
        x: { time: true },
        y: {
          range: (u, dmin, dmax) => {
            let lo = dmin, hi = dmax;
            if (lo == null || hi == null || !Number.isFinite(lo) || !Number.isFinite(hi)) { lo = band ? band.min : 0; hi = band ? band.max : 1; }
            if (band) { lo = Math.min(lo, band.min); hi = Math.max(hi, band.max); }
            if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
            const pad = (hi - lo) * 0.15;
            return [lo - pad, hi + pad];
          },
        },
      },
      axes: [
        { show: !!current.showX, stroke: text3, grid: { stroke: line, width: 1 }, ticks: { show: false }, font: FONT, size: 26, gap: 6,
          values: (u, splits) => splits.map((s) => fmtTick(s, rangeHours)) },
        { stroke: text3, grid: { stroke: line, width: 1 }, ticks: { show: false }, font: FONT, size: 44, gap: 4,
          values: (u, splits) => splits.map((s) => num(s, decimals <= 1 ? decimals : 1)) },
      ],
      series: [
        {},
        { stroke, width: 2, points: { show: false }, spanGaps: false },
      ],
      hooks: {
        drawClear: [shade],
        setCursor: [(u) => {
          const idx = u.cursor.idx;
          if (idx == null || !tip) { if (tip) tip.style.display = 'none'; return; }
          const x = u.data[0][idx], y = u.data[1][idx];
          if (y == null) { tip.style.display = 'none'; return; }
          const d = new Date(x * 1000);
          const when = rangeHours <= 36 ? fmtTime(d) : `${fmtDateShort(d)} ${fmtTime(d)}`;
          tip.innerHTML = `${when} · <b>${num(y, decimals)}${current.unit ? ' ' + current.unit : ''}</b>`;
          tip.style.display = 'block';
          const left = u.valToPos(x, 'x') + u.bbox.left / devicePixelRatio;
          const top = u.valToPos(y, 'y') + u.bbox.top / devicePixelRatio;
          tip.style.left = `${Math.min(Math.max(left, 60), el.clientWidth - 60)}px`;
          tip.style.top = `${Math.max(top, 28)}px`;
        }],
      },
    };
    u = new window.uPlot(opts, [current.x || [], current.y || []], el);
    tip = h('div', { class: 'u-tip' });
    el.append(tip);
    el.addEventListener('mouseleave', () => { if (tip) tip.style.display = 'none'; });
    ro = new ResizeObserver(() => { if (u && el.clientWidth) u.setSize({ width: el.clientWidth, height: current.height || 160 }); });
    ro.observe(el);
  }

  function destroy() {
    if (ro) { ro.disconnect(); ro = null; }
    if (u) { u.destroy(); u = null; }
    if (tip) { tip.remove(); tip = null; }
    el.innerHTML = '';
  }

  function update(next = {}, { rebuild = false } = {}) {
    const structural = ['band', 'lights', 'color', 'height', 'showX', 'rangeHours', 'decimals', 'unit'].some((k) => k in next && JSON.stringify(next[k]) !== JSON.stringify(current[k]));
    current = { ...current, ...next };
    if (!u || rebuild || structural) { destroy(); build(); return; }
    u.setData([current.x || [], current.y || []]);
  }

  build();
  return { update, destroy, rebuild: () => { destroy(); build(); }, get uplot() { return u; } };
}

/** Nice tick times between start and end (seconds). */
function axisTicks(start, end) {
  const span = end - start;
  let step;
  if (span <= 36 * 3600) step = 6 * 3600;
  else if (span <= 8 * 86400) step = 86400;
  else step = 5 * 86400;
  const ticks = [];
  const first = Math.ceil(start / step) * step;
  for (let t = first; t < end; t += step) ticks.push(t);
  return { ticks, step };
}

/**
 * Gantt-style device timeline from /api/devices/history events.
 * cfg: { events:[{t, role, state, reason}], labels:{role:label}, start, end (sec) }
 */
export function deviceTimeline(el, { events, labels = {}, start, end }) {
  el.classList.add('gantt');
  el.innerHTML = '';
  const byRole = new Map();
  for (const e of events) {
    const t = parseISO(e.t)?.getTime() / 1000;
    if (!t) continue;
    if (!byRole.has(e.role)) byRole.set(e.role, []);
    byRole.get(e.role).push({ t, state: e.state, reason: e.reason });
  }
  if (!byRole.size) { el.append(h('div', { class: 'empty' }, 'No device switches in this range yet.')); return; }
  const span = end - start;
  const order = ['light', 'exhaust_fan', 'intake_fan', 'circulation_fan', 'circulation_fan_2', 'humidifier', 'dehumidifier', 'heater', 'cooler'];
  const roles = [...byRole.keys()].sort((a, b) => (order.indexOf(a) + 100) % 100 - (order.indexOf(b) + 100) % 100);
  for (const role of roles) {
    const evs = byRole.get(role).sort((a, b) => a.t - b.t);
    const track = h('div', { class: 'g-track' });
    let onSince = null;
    // If the first event we see is "off", the device was on from the start of the range.
    if (evs.length && evs[0].state === 'off') onSince = { t: start, reason: '' };
    const bars = [];
    for (const e of evs) {
      if (e.state === 'on' && onSince == null) onSince = e;
      else if (e.state === 'off' && onSince != null) { bars.push([onSince.t, e.t, onSince.reason || e.reason]); onSince = null; }
    }
    if (onSince != null) bars.push([onSince.t, end, onSince.reason]);
    for (const [a, b, reason] of bars) {
      const l = Math.max(0, (a - start) / span * 100), r = Math.min(100, (b - start) / span * 100);
      if (r <= l) continue;
      const title = `${labels[role] || role}: on ${fmtDateShort(new Date(a * 1000))} ${fmtTime(new Date(a * 1000))} → ${fmtTime(new Date(b * 1000))}${reason ? ` · ${reason}` : ''}`;
      track.append(h('div', { class: `g-bar ${role === 'light' ? 'light' : ''}`, style: { left: `${l}%`, width: `${r - l}%` }, title, role: 'img', 'aria-label': title }));
    }
    el.append(h('div', { class: 'g-row' }, h('div', { class: 'g-label' }, icon(DEVICE_ICON[role] || 'plug'), labels[role] || role), track));
  }
  const axis = h('div', { class: 'g-axis' });
  const { ticks } = axisTicks(start, end);
  axis.append(h('span', { style: { left: '0%' } }, fmtTick(start, span / 3600)));
  for (const t of ticks) { const pct = (t - start) / span * 100; if (pct > 6 && pct < 93) axis.append(h('span', { style: { left: `${pct}%` } }, fmtTick(t, span / 3600))); }
  axis.append(h('span', { style: { left: '100%' } }, 'now'));
  el.append(h('div', { class: 'g-row' }, h('div'), axis));
}

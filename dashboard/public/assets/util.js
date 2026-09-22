// DOM builder, formatting helpers, modals and toasts.
import { icon } from './icons.js';

export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v);
      else if (k === 'html') el.innerHTML = v;
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, v);
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

export function replaceChildren(el, ...children) { clear(el); return append(el, children); }

// ---------- numbers / units ----------
export const cToF = (c) => c * 9 / 5 + 32;
export const fToC = (f) => (f - 32) * 5 / 9;

export function num(v, decimals = 1) {
  if (v == null || Number.isNaN(v)) return '—';
  return Number(v).toFixed(decimals);
}

export function bandStatus(value, min, max, tol) {
  if (value == null || min == null || max == null) return 'unknown';
  if (value >= min && value <= max) return 'good';
  const dist = value < min ? min - value : value - max;
  return dist <= tol ? 'warn' : 'alert';
}

export function capitalize(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }

export function plantLabel(p) {
  if (!p) return 'Tent';
  if (p.owner) return `${p.owner}'s`;
  return p.name;
}

export const STAGE_NAMES = { seedling: 'Seedling', veg: 'Veg', flower: 'Flower', flush: 'Flush', drying: 'Drying', curing: 'Curing', done: 'Done' };

// ---------- time ----------
export function parseISO(s) {
  if (!s) return null;
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function relTime(iso) {
  const d = parseISO(iso);
  if (!d) return '';
  const s = Math.round((Date.now() - d.getTime()) / 1000);
  if (s < 10) return 'just now';
  if (s < 60) return `${s} secs ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const hh = Math.round(m / 60);
  if (hh < 24) return `${hh} h ago`;
  const dd = Math.round(hh / 24);
  return dd === 1 ? 'yesterday' : `${dd} days ago`;
}

export function countdown(iso) {
  const d = parseISO(iso);
  if (!d) return '';
  let s = Math.max(0, Math.round((d.getTime() - Date.now()) / 1000));
  const hh = Math.floor(s / 3600); s -= hh * 3600;
  const mm = Math.floor(s / 60);
  if (hh > 0) return `${hh}h ${mm}m`;
  return `${mm}m`;
}

export function fmtTime(d) {
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(d);
}
export function fmtDateLong(d) {
  return new Intl.DateTimeFormat(undefined, { weekday: 'long', month: 'long', day: 'numeric' }).format(d);
}
export function fmtDateShort(d) {
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(d);
}
export function fmtDateTime(iso) {
  const d = parseISO(iso);
  if (!d) return '';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d);
}
export function dayKey(iso) {
  const d = parseISO(iso);
  if (!d) return '';
  const today = new Date();
  const y = new Date(); y.setDate(today.getDate() - 1);
  const same = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (same(d, today)) return 'Today';
  if (same(d, y)) return 'Yesterday';
  return new Intl.DateTimeFormat(undefined, { weekday: 'short', month: 'long', day: 'numeric' }).format(d);
}
export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// ---------- widgets ----------
export function spinner() { return h('span', { class: 'spinner', role: 'status', 'aria-label': 'Loading' }); }

export function notice(text, level = 'info', ic = null) {
  const cls = { info: '', warn: 'warn', alert: 'alert', night: 'night' }[level] || '';
  return h('div', { class: `notice ${cls}`.trim() }, icon(ic || (level === 'warn' ? 'warn' : level === 'alert' ? 'octagon' : 'info')), h('span', null, text));
}

export function toast(text, kind = '') {
  const host = document.getElementById('toasts');
  const t = h('div', { class: `toast ${kind}`.trim() }, kind === 'error' ? icon('warn') : kind === 'ok' ? icon('check') : null, text);
  host.append(t);
  setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; setTimeout(() => t.remove(), 300); }, kind === 'error' ? 5000 : 2800);
}

let modalStack = [];
export function openModal({ title, body, size = '', onClose, closeLabel = 'Close' }) {
  const host = document.getElementById('modals');
  const modal = h('div', { class: `modal ${size}`.trim(), role: 'dialog', 'aria-modal': 'true', 'aria-label': title || 'Dialog' });
  const back = h('div', { class: 'modal-back' }, modal);
  const closeBtn = h('button', { class: 'btn quiet icon', 'aria-label': closeLabel, onclick: () => close() }, icon('x'));
  if (title !== false) modal.append(h('div', { class: 'modal-head' }, h('h2', null, title || ''), closeBtn));
  append(modal, [body]);
  const prevFocus = document.activeElement;
  function close(result) {
    if (!back.isConnected) return;
    back.remove();
    modalStack = modalStack.filter((m) => m !== close);
    document.body.style.overflow = modalStack.length ? 'hidden' : '';
    if (onClose) onClose(result);
    if (prevFocus && prevFocus.focus) prevFocus.focus();
  }
  back.addEventListener('mousedown', (e) => { if (e.target === back) close(); });
  modal.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } });
  host.append(back);
  document.body.style.overflow = 'hidden';
  modalStack.push(close);
  const first = modal.querySelector('input, select, textarea, button:not([aria-label="Close"])') || closeBtn;
  setTimeout(() => first.focus(), 30);
  return { close, el: modal };
}

export function confirmDialog({ title, message, confirmText = 'Confirm', cancelText = 'Cancel', danger = false, ic = null }) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal({
      title: false,
      onClose: () => { if (!done) resolve(false); },
      body: h('div', { class: 'centered stack' },
        ic ? icon(ic, `big-ic ${danger ? 'lvl-alert' : ''}`) : null,
        h('h2', { style: { fontSize: '20px' } }, title),
        message ? h('p', { class: 'muted' }, message) : null,
        h('div', { class: 'modal-actions' },
          h('button', { class: `btn big ${danger ? 'danger' : ''}`, onclick: () => { done = true; m.close(); resolve(true); } }, confirmText),
          h('button', { class: 'btn big ghost', onclick: () => { done = true; m.close(); resolve(false); } }, cancelText))),
    });
    setTimeout(() => m.el.querySelector('.btn.ghost')?.focus(), 40);
  });
}

export function chooseDialog({ title, message, options }) {
  return new Promise((resolve) => {
    let done = false;
    const m = openModal({
      title: false,
      onClose: () => { if (!done) resolve(null); },
      body: h('div', { class: 'centered stack' },
        h('h2', { style: { fontSize: '20px' } }, title),
        message ? h('p', { class: 'muted' }, message) : null,
        h('div', { class: 'modal-actions' },
          options.map((o) => h('button', { class: `btn big ${o.ghost ? 'ghost' : ''}`, onclick: () => { done = true; m.close(); resolve(o.value); } }, o.label)),
          h('button', { class: 'btn big quiet', onclick: () => { done = true; m.close(); resolve(null); } }, 'Cancel'))),
    });
  });
}

export function segmented(options, value, onChange, cls = '') {
  const wrap = h('div', { class: `seg ${cls}`.trim(), role: 'group' });
  const set = (v) => { for (const b of wrap.children) b.setAttribute('aria-pressed', String(b.dataset.v === String(v))); };
  for (const o of options) {
    wrap.append(h('button', { type: 'button', dataset: { v: String(o.value) }, 'aria-pressed': String(o.value === value), onclick: () => { set(o.value); onChange(o.value); } }, o.label));
  }
  wrap.set = set;
  return wrap;
}

export function field(label, input, opts = {}) {
  const id = input.id || `f_${Math.random().toString(36).slice(2, 8)}`;
  input.id = id;
  return h('div', { class: `field ${opts.class || ''}`.trim() }, h('label', { for: id }, label), input, opts.hint ? h('span', { class: 'tiny faint' }, opts.hint) : null);
}

export function input(attrs = {}) { return h('input', { class: 'input', ...attrs }); }
export function select(options, value, attrs = {}) {
  const s = h('select', { class: 'input', ...attrs });
  for (const o of options) s.append(h('option', { value: o.value ?? '', selected: String(o.value ?? '') === String(value ?? '') }, o.label));
  return s;
}

export function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

export function cssVar(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function errText(e) {
  if (!e) return 'Something went wrong';
  if (e.detail) return e.detail;
  if (e.message) return e.message;
  return String(e);
}

// GrowOp dashboard shell: connect card, theme, router, status polling.
import { api, getConn, setConn, ApiError } from './api.js';
import { icon } from './icons.js';
import { h, replaceChildren, fmtTime, toast, errText, spinner } from './util.js';
import { createOverview } from './overview.js';
import { createHistory } from './history.js';
import { createJournal } from './journal.js';
import { createAdvisor } from './advisor.js';
import { createSettings } from './settings.js';

const THEME_STORE = 'growop.theme';
const state = { status: null, settings: null, page: null, pageName: null, pollTimer: null, connected: false };

// ---------- theme ----------
const media = window.matchMedia('(prefers-color-scheme: dark)');
function getTheme() { try { return localStorage.getItem(THEME_STORE) || 'auto'; } catch { return 'auto'; } }
function applyTheme(t) {
  if (t === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  const btn = document.getElementById('theme-toggle');
  replaceChildren(btn, icon(t === 'auto' ? 'auto' : t === 'dark' ? 'moon' : 'sun'), h('span', null, t === 'auto' ? 'Auto theme' : t === 'dark' ? 'Dark' : 'Light'));
  btn.setAttribute('aria-label', `Theme: ${t}. Click to change`);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', getComputedStyle(document.documentElement).getPropertyValue('--bg').trim());
  window.dispatchEvent(new CustomEvent('growop:theme'));
}
function cycleTheme() { const order = ['auto', 'light', 'dark']; const next = order[(order.indexOf(getTheme()) + 1) % 3]; try { localStorage.setItem(THEME_STORE, next); } catch { /* ignore */ } applyTheme(next); }
media.addEventListener?.('change', () => { if (getTheme() === 'auto') applyTheme('auto'); });

// ---------- context shared with pages ----------
const ctx = {
  getStatus: () => state.status,
  getSettings: () => state.settings,
  setSettings: (s) => { state.settings = s; state.page?.onSettings?.(s); },
  units: () => state.settings?.units || 'c',
  navigate: (hash) => { location.hash = hash; },
  refreshStatus: () => poll(),
};

const PAGES = {
  overview: () => createOverview(ctx),
  history: () => createHistory(ctx),
  journal: () => createJournal(ctx),
  advisor: () => createAdvisor(ctx),
  settings: () => createSettings(ctx),
};

// ---------- status polling ----------
async function poll(force = false) {
  if (!state.connected) return;
  // Pause polling while the tab is hidden, but never skip the first status (a wall display may start hidden).
  if (!force && state.status && document.visibilityState !== 'visible') return;
  try {
    const s = await api.get('/api/status');
    state.status = s;
    state.page?.onStatus?.(s);
    updateShell(s);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return;
    setConnDot(false, errText(e));
  }
}
function startPolling() { stopPolling(); poll(true); state.pollTimer = setInterval(() => poll(), 10000); }
function stopPolling() { if (state.pollTimer) clearInterval(state.pollTimer); state.pollTimer = null; }
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') startPolling(); else stopPolling(); });

function setConnDot(ok, text) {
  const dot = document.getElementById('conn-dot'), label = document.getElementById('conn-text');
  dot.className = `dot ${ok ? 'on' : 'off'}`; label.textContent = text;
}
function updateShell(s) {
  setConnDot(s.ha_connected !== false, s.ha_connected === false ? 'Home Assistant offline' : 'Connected');
  const needs = (s.open_tasks || 0) + (s.open_photo_requests || 0);
  const badge = document.getElementById('journal-badge');
  badge.classList.toggle('hidden', !needs); badge.textContent = needs;
  const ab = document.getElementById('advisor-badge');
  ab.classList.toggle('hidden', !s.unread_brief); ab.textContent = '1';
}

// ---------- router ----------
function route() {
  const raw = location.hash.replace(/^#\/?/, '') || 'overview';
  const [name, query] = raw.split('?');
  const page = PAGES[name] ? name : 'overview';
  const params = new URLSearchParams(query || '');
  for (const a of document.querySelectorAll('.nav a')) { const cur = a.dataset.page === page; if (cur) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }
  if (state.pageName === page && !params.toString()) return;
  state.page?.unmount?.();
  const root = document.getElementById('page');
  root.innerHTML = '';
  state.page = PAGES[page](); state.pageName = page;
  state.page.mount(root, params);
  document.title = `${state.page.title} · GrowOp`;
  window.scrollTo({ top: 0 });
  if (state.status) state.page.onStatus?.(state.status);
}
window.addEventListener('hashchange', route);

// ---------- connect card ----------
function showConnect(message) {
  state.connected = false; stopPolling();
  const card = document.getElementById('connect');
  const key = document.getElementById('connect-key'), server = document.getElementById('connect-server'), err = document.getElementById('connect-err');
  const c = getConn(); key.value = c.key || ''; server.value = c.server || '';
  err.textContent = message || '';
  card.classList.remove('hidden'); document.getElementById('app').setAttribute('aria-hidden', 'true');
  setTimeout(() => key.focus(), 50);
}
async function tryConnect(e) {
  e?.preventDefault();
  const key = document.getElementById('connect-key').value.trim(), server = document.getElementById('connect-server').value.trim().replace(/\/+$/, '');
  const err = document.getElementById('connect-err'), btn = document.getElementById('connect-btn');
  if (!key) { err.textContent = location.port === '8099' ? 'Enter the API key from the add-on settings.' : 'Enter the dashboard password.'; return; }
  setConn({ key, server });
  btn.disabled = true; replaceChildren(btn, spinner(), 'Connecting…'); err.textContent = '';
  try {
    const s = await api.get('/api/status');
    state.status = s;
    await boot();
  } catch (ex) {
    err.textContent = ex instanceof ApiError && ex.status === 401 ? 'That key was not accepted.' : errText(ex);
  }
  btn.disabled = false; replaceChildren(btn, 'Connect');
}

async function boot() {
  state.connected = true;
  document.getElementById('connect').classList.add('hidden'); document.getElementById('app').removeAttribute('aria-hidden');
  try { state.settings = await api.get('/api/settings'); } catch { state.settings = null; }
  route();
  startPolling();
}

// Hosted copy (Vercel): the key field is the dashboard password, not the add-on key. // growop-hosted-label
if (location.port !== '8099') {
  const lbl = document.querySelector('label[for="connect-key"]'); if (lbl) lbl.textContent = 'Dashboard password';
  const hint = document.querySelector('p.muted.small'); if (hint && /API key/.test(hint.textContent)) hint.textContent = 'Enter the dashboard password you were given.';
  const inp = document.getElementById('connect-key'); if (inp) inp.setAttribute('autocomplete', 'current-password');
}
window.addEventListener('growop:unauthorized', () => { if (state.connected) { showConnect(location.port === '8099' ? 'The API key was rejected — enter it again.' : 'Wrong dashboard password — try again.'); } });

// ---------- init ----------
function init() {
  applyTheme(getTheme());
  document.getElementById('theme-toggle').addEventListener('click', cycleTheme);
  document.getElementById('connect-form').addEventListener('submit', tryConnect);
  for (const id of ['connect-key', 'connect-server']) document.getElementById(id).addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.keyCode === 13) tryConnect(e); });
  const showKey = document.getElementById('connect-show');
  showKey.addEventListener('click', () => { const k = document.getElementById('connect-key'); k.type = k.type === 'password' ? 'text' : 'password'; showKey.setAttribute('aria-pressed', String(k.type === 'text')); });
  const clock = document.getElementById('clock');
  const tick = () => { clock.textContent = fmtTime(new Date()); };
  tick(); setInterval(tick, 15000);
  if (getConn().key) boot().catch((e) => { if (!(e instanceof ApiError && e.status === 401)) toast(errText(e), 'error'); });
  else showConnect();
}
init();

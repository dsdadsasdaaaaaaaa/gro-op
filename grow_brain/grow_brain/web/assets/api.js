// API client: X-API-Key on every call, blobs for images, 401 -> connect card.
const KEY_STORE = 'growop.apiKey';
const SERVER_STORE = 'growop.server';
const DEVICE_STORE = 'growop.device';

/** Where this page is running: 'addon' (the add-on's own port on home Wi-Fi), 'ingress' (Home Assistant's sidebar,
 *  already signed in to Home Assistant) or 'hosted' (the password-protected copy on the internet). */
export const MODE = location.port === '8099' ? 'addon' : /\/api\/hassio_ingress\//.test(location.pathname) ? 'ingress' : 'hosted';

function deviceId() {
  try {
    let id = localStorage.getItem(DEVICE_STORE);
    if (!id) { id = 'web-' + Math.random().toString(36).slice(2, 12); localStorage.setItem(DEVICE_STORE, id); }
    return id;
  } catch { return 'web'; }
}

export class ApiError extends Error {
  constructor(status, detail) { super(detail || `HTTP ${status}`); this.status = status; this.detail = detail; }
}

export function getConn() {
  try { return { key: localStorage.getItem(KEY_STORE) || '', server: localStorage.getItem(SERVER_STORE) || '' }; }
  catch { return { key: '', server: '' }; }
}
export function setConn({ key, server }) {
  try {
    localStorage.setItem(KEY_STORE, key || '');
    if (server) localStorage.setItem(SERVER_STORE, server.replace(/\/+$/, '')); else localStorage.removeItem(SERVER_STORE);
  } catch { /* private mode */ }
}
export function clearConn() { try { localStorage.removeItem(KEY_STORE); } catch { /* ignore */ } }

function defaultBase() { return new URL('.', location.href).href.replace(/\/$/, ''); }
// Only the add-on's own page may point at another server: the hosted copy must never send its password elsewhere.
function base() { return (MODE === 'addon' && getConn().server) || defaultBase(); }

/** A plain sentence out of an error body (FastAPI sends a string, or a list of field errors). */
function detailText(d) {
  if (!d) return '';
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => (x && x.msg ? String(x.msg).replace(/^Value error, /, '') : String(x))).join('; ');
  return String(d.message || d.detail || '');
}

async function request(method, path, { body, form, signal, raw } = {}) {
  const headers = { 'X-API-Key': getConn().key, 'X-Device-Id': deviceId() };
  const init = { method, headers, signal };
  if (form) init.body = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(base() + path, init); }
  catch (e) { if (e.name === 'AbortError') throw e; throw new ApiError(0, `Can't reach GrowOp at home (${e.message})`); }
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('growop:unauthorized'));
    throw new ApiError(401, MODE === 'hosted' ? 'Wrong dashboard password' : 'Not authorised: check the API key');
  }
  if (!res.ok) {
    let detail = `Something went wrong (${res.status})`;
    try { const j = await res.json(); const t = detailText(j && j.detail); if (t) detail = t; } catch { /* not json */ }
    throw new ApiError(res.status, detail);
  }
  if (raw) return res;
  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return res.text();
}

export const api = {
  get: (path, opts) => request('GET', path, opts),
  post: (path, body, opts) => request('POST', path, { body, ...opts }),
  put: (path, body, opts) => request('PUT', path, { body, ...opts }),
  del: (path, opts) => request('DELETE', path, opts),
  postForm: (path, form, opts) => request('POST', path, { form, ...opts }),
  /** Fetch bytes with the key in a header and return an object URL (caller revokes). */
  async blobUrl(path, opts = {}) {
    const res = await request('GET', path, { ...opts, raw: true });
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },
  async blob(path, opts = {}) {
    const res = await request('GET', path, { ...opts, raw: true });
    return res.blob();
  },
};

/** True when the endpoint doesn't exist on this grow brain (older backend). */
export const isMissing = (e) => e instanceof ApiError && (e.status === 404 || e.status === 405);

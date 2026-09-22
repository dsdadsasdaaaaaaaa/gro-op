// API client: X-API-Key on every call, blobs for images, 401 -> connect card.
const KEY_STORE = 'growop.apiKey';
const SERVER_STORE = 'growop.server';

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
function base() { return getConn().server || defaultBase(); }

async function request(method, path, { body, form, signal, raw } = {}) {
  const headers = { 'X-API-Key': getConn().key };
  const init = { method, headers, signal };
  if (form) init.body = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(base() + path, init); }
  catch (e) { if (e.name === 'AbortError') throw e; throw new ApiError(0, `Can't reach the grow brain (${e.message})`); }
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('growop:unauthorized'));
    throw new ApiError(401, 'Not authorised — check the API key');
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j && j.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch { /* not json */ }
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

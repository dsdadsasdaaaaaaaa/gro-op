// GrowOp dashboard proxy: forwards /api/* to the Grow Brain add-on through Home Assistant's
// remote link (Nabu Casa) using add-on ingress. Runs on Vercel Functions (Node 24, Fluid Compute).
//
// Env vars (Vercel project settings):
//   HA_URL              https://xxxx.ui.nabu.casa
//   HA_TOKEN            Home Assistant long-lived access token (admin)
//   GROW_API_KEY        the add-on's api_key
//   DASHBOARD_PASSWORD  what the dashboard's "key" field must contain
//   DASHBOARD_PASSWORD_DAD  optional second password (Dad's own), accepted the same way
//   ADDON_SLUG          optional; auto-discovered (ends with "grow_brain")

import { createHash, timingSafeEqual } from 'node:crypto';

const HA_URL = (process.env.HA_URL || '').replace(/\/$/, '');
const HA_TOKEN = process.env.HA_TOKEN || '';
const GROW_API_KEY = process.env.GROW_API_KEY || '';
const PASSWORDS = [process.env.DASHBOARD_PASSWORD, process.env.DASHBOARD_PASSWORD_DAD].filter(Boolean);
const SESSION_TTL_MS = 10 * 60 * 1000;

// Per-instance cache (Fluid Compute keeps instances warm; a cold instance just rediscovers).
let cache = { ingressPath: null, session: null, sessionAt: 0 };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}

/** Open HA's WebSocket, authenticate, run supervisor/api commands in order, return their results. */
async function supervisor(commands) {
  if (!HA_URL || !HA_TOKEN) throw new Error('HA_URL / HA_TOKEN are not configured');
  const ws = new WebSocket(HA_URL.replace(/^http/, 'ws') + '/api/websocket');
  const queue = [];
  let wake = null;
  ws.addEventListener('message', (e) => { queue.push(JSON.parse(String(e.data))); if (wake) { const w = wake; wake = null; w(); } });
  const next = () => new Promise((resolve, reject) => {
    if (queue.length) return resolve(queue.shift());
    const t = setTimeout(() => reject(new Error('Home Assistant WebSocket timed out')), 20000);
    wake = () => { clearTimeout(t); resolve(queue.shift()); };
  });
  try {
    await new Promise((resolve, reject) => {
      ws.addEventListener('open', resolve, { once: true });
      ws.addEventListener('error', () => reject(new Error("Couldn't open Home Assistant's WebSocket")), { once: true });
    });
    await next(); // auth_required
    ws.send(JSON.stringify({ type: 'auth', access_token: HA_TOKEN }));
    const auth = await next();
    if (auth.type !== 'auth_ok') throw new Error('Home Assistant rejected the access token');
    const results = [];
    let id = 1;
    for (const [endpoint, method] of commands) {
      ws.send(JSON.stringify({ id, type: 'supervisor/api', endpoint, method }));
      let r;
      do { r = await next(); } while (r.id !== id);
      if (!r.success) throw new Error('Home Assistant: ' + (r.error?.message || r.error?.code || 'error'));
      results.push(r.result?.data ?? r.result);
      id++;
    }
    return results;
  } finally {
    try { ws.close(); } catch {}
  }
}

let inflight = null;

async function ensureSession(force = false) {
  const fresh = cache.ingressPath && cache.session && Date.now() - cache.sessionAt < SESSION_TTL_MS;
  if (fresh && !force) return cache;
  // Many parallel requests (snapshot + frames + status) must share one WebSocket handshake.
  if (!inflight) {
    inflight = refreshSession(force).finally(() => { inflight = null; });
  }
  return inflight;
}

async function refreshSession(force) {
  if (!cache.ingressPath || force) {
    let slug = process.env.ADDON_SLUG;
    if (!slug) {
      const [addons] = await supervisor([['/addons', 'get']]);
      slug = (addons?.addons || []).find((a) => a.slug === 'grow_brain' || a.slug.endsWith('_grow_brain'))?.slug;
      if (!slug) throw new Error('Grow Brain add-on not found in Home Assistant');
    }
    const [info, sess] = await supervisor([[`/addons/${slug}/info`, 'get'], ['/ingress/session', 'post']]);
    if (!info?.ingress_url) throw new Error('The add-on has no ingress address (update it to 0.3.0 or later)');
    cache = { ingressPath: info.ingress_url.replace(/\/$/, ''), session: sess.session, sessionAt: Date.now() };
  } else {
    const [sess] = await supervisor([['/ingress/session', 'post']]);
    cache.session = sess.session;
    cache.sessionAt = Date.now();
  }
  return cache;
}

/** The original /api/... path: Vercel rewrites every /api/* request here with the path in ?__path=. */
function targetPath(request) {
  const url = new URL(request.url);
  let p = url.pathname;
  const q = url.searchParams.get('__path');
  if (q !== null) {
    p = '/api/' + q;
    url.searchParams.delete('__path');
  }
  url.searchParams.delete('api_key');   // the password never travels further than this function
  return { path: p, search: url.searchParams.toString() ? '?' + url.searchParams.toString() : '' };
}

async function forward(request, bodyBuf, retried = false) {
  const { path, search } = targetPath(request);
  const { ingressPath, session } = await ensureSession(retried);
  const headers = new Headers();
  const ct = request.headers.get('content-type');
  if (ct) headers.set('content-type', ct);
  headers.set('cookie', `ingress_session=${session}`);
  headers.set('x-api-key', GROW_API_KEY);
  headers.set('authorization', `Bearer ${HA_TOKEN}`);
  headers.set('accept', request.headers.get('accept') || '*/*');
  const res = await fetch(`${HA_URL}${ingressPath}${path}${search}`, {
    method: request.method, headers, body: bodyBuf, redirect: 'manual',
  });
  // A 401 here is usually an expired ingress session; renew once and retry.
  if (res.status === 401 && !retried) return forward(request, bodyBuf, true);
  if (res.status === 401) {
    return json({ detail: "The online dashboard's key doesn't match the Grow Brain add-on. Tell whoever set up Home Assistant (GROW_API_KEY in Vercel)." }, 502);
  }
  return res;
}

// Things that stay on the home network: the setup QR (it contains the add-on key), the full database backup,
// and changing which Home Assistant devices the tent controls.
const LOCAL_ONLY = [
  [/^\/api\/setup-qr\.png$/, null], [/^\/api\/backup$/, null],
  [/^\/api\/devices\/[^/]+$/, 'PUT'], [/^\/api\/ha\/automap$/, null], [/^\/api\/ha\/entities$/, null],
];

function sameSecret(a, b) {
  const ha = createHash('sha256').update(String(a)).digest();
  const hb = createHash('sha256').update(String(b)).digest();
  return timingSafeEqual(ha, hb);
}

// Slow down password guessing: 10 wrong tries from one address locks it out for 15 minutes (per function instance).
const failures = new Map();
function clientIp(request) {
  return (request.headers.get('x-forwarded-for') || '').split(',')[0].trim() || request.headers.get('x-real-ip') || 'unknown';
}
function lockedOut(ip) {
  const f = failures.get(ip);
  return f && f.until && f.until > Date.now();
}
function recordFailure(ip) {
  const now = Date.now();
  const f = failures.get(ip) && now - failures.get(ip).first < 10 * 60 * 1000 ? failures.get(ip) : { n: 0, first: now, until: 0 };
  f.n += 1;
  if (f.n >= 10) f.until = now + 15 * 60 * 1000;
  failures.set(ip, f);
  if (failures.size > 5000) failures.clear();
}

async function handler(request) {
  const ip = clientIp(request);
  if (lockedOut(ip)) return json({ detail: 'Too many wrong passwords. Try again in 15 minutes.' }, 429);
  const key = request.headers.get('x-api-key') || '';     // header only: never in a URL, so never in a log
  // every password is checked (no early exit), so timing doesn't hint which one exists
  if (!key || !PASSWORDS.map((p) => sameSecret(key, p)).includes(true)) {
    recordFailure(ip);
    return json({ detail: 'Wrong dashboard password' }, 401);
  }
  failures.delete(ip);
  const { path } = targetPath(request);
  if (!path.startsWith('/api/')) return json({ detail: 'Not found' }, 404);
  if (LOCAL_ONLY.some(([re, method]) => re.test(path) && (!method || method === request.method))) {
    return json({ detail: "Not available on the online dashboard. Open GrowOp from Home Assistant's sidebar for this." }, 403);
  }
  try {
    const bodyBuf = ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer();
    const res = await forward(request, bodyBuf);
    const out = new Headers();
    // Never copy content-length/content-encoding: fetch() already decompressed the body.
    for (const h of ['content-type', 'content-disposition']) {
      const v = res.headers.get(h);
      if (v) out.set(h, v);
    }
    out.set('cache-control', 'no-store');
    return new Response(res.body, { status: res.status, headers: out });
  } catch (e) {
    // plain words, no internals
    const msg = /token/i.test(e.message || '') ? "Home Assistant didn't accept the online dashboard's access token."
      : /WebSocket|timed out|fetch failed|ECONN|ENOTFOUND/i.test(e.message || '') ? "Can't reach Home Assistant right now. Is the box at home online?"
      : 'The online dashboard had a problem talking to Home Assistant.';
    return json({ detail: msg }, 502);
  }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;

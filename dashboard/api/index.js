// GrowOp dashboard proxy: forwards /api/* to the Grow Brain add-on through Home Assistant's
// remote link (Nabu Casa) using add-on ingress. Runs on Vercel Functions (Node 24, Fluid Compute).
//
// Env vars (Vercel project settings):
//   HA_URL              https://xxxx.ui.nabu.casa
//   HA_TOKEN            Home Assistant long-lived access token (admin)
//   GROW_API_KEY        the add-on's api_key
//   DASHBOARD_PASSWORD  what the dashboard's "key" field must contain
//   ADDON_SLUG          optional; auto-discovered (ends with "grow_brain")

const HA_URL = (process.env.HA_URL || '').replace(/\/$/, '');
const HA_TOKEN = process.env.HA_TOKEN || '';
const GROW_API_KEY = process.env.GROW_API_KEY || '';
const DASHBOARD_PASSWORD = process.env.DASHBOARD_PASSWORD || '';
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
  return res;
}

async function handler(request) {
  const url = new URL(request.url);
  const key = request.headers.get('x-api-key') || url.searchParams.get('api_key') || '';
  if (!DASHBOARD_PASSWORD || key !== DASHBOARD_PASSWORD) {
    return json({ detail: 'Wrong dashboard password' }, 401);
  }
  if (!targetPath(request).path.startsWith('/api/')) return json({ detail: 'Not found' }, 404);
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
    return json({ detail: e.message || String(e) }, 502);
  }
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const DELETE = handler;
export const PATCH = handler;

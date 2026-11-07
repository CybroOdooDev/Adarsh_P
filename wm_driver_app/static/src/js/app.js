/**
 * WM Driver App — app.js
 *
 * Architecture
 * ─────────────
 * Storage:
 *   - localStorage  : serverUrl, apiKey, database (stored as plain text on the device)
 *   - IndexedDB     : offline submission queue (wm-driver-queue store)
 *
 * Screens:
 *   #screen-setup  → initial API key entry
 *   #screen-home   → today's stop list
 *   #screen-stop   → stop detail + 7 status action buttons
 *
 * Modals:
 *   #modal-flag    → note (required) + optional photo when tapping "Flag Issue"
 *   #modal-photo   → optional photo for any other status (Cancel logs nothing)
 *   #modal-weighed → per-category weights when tapping "Weighed"
 *
 * Offline flow:
 *   1. User taps a status button.
 *   2. A client_uuid is generated (crypto.randomUUID()).
 *   3. Geolocation is requested (best-effort, 0,0 fallback).
 *   4. The submission is written to IndexedDB immediately.
 *   5. The UI is updated optimistically.
 *   6. A POST is attempted. If it succeeds the queue entry is removed.
 *   7. If offline (or request fails), the entry stays queued.
 *   8. navigator.onLine / online event + SW postMessage trigger retry.
 */

'use strict';

// ─── Constants ───────────────────────────────────────────────────────────────

// The Android app serves these screens itself and exposes this bridge. The
// page then runs on the server's origin (or a placeholder one before a server
// is known), so the API stays same-origin while the app opens without it.
const NATIVE = (typeof window !== 'undefined' && window.WMDriverNative) || null;
const NATIVE_PLACEHOLDER_HOST = 'appassets.androidplatform.net';

function onNativePlaceholder() {
  return !!NATIVE && window.location.hostname === NATIVE_PLACEHOLDER_HOST;
}

/**
 * In the Android app, point it at the server typed on the setup screen.
 * Returns true when the app is moving there (the page reloads on that origin).
 */
function nativeSwitchServer(rawUrl) {
  if (!NATIVE || !(rawUrl || '').trim()) return false;
  const target = NATIVE.setServer(rawUrl.trim());
  return !!target && target !== window.location.origin;
}

const DB_NAME    = 'wm-driver-db';
const DB_VERSION = 1;
const STORE_QUEUE = 'queue';

const STATUS_LABELS = {
  en_route:  '🚚 En Route',
  arrived:   '📍 Arrived',
  started:   '▶️ Started',
  lifted:    '⬆️ Lifted',
  weighed:   '⚖️ Weighed',
  completed: '✅ Completed',
  flagged:   '🚩 Flagged',
};

const ALLOWED_NEXT_STATUSES = {
  null: ['en_route', 'arrived', 'flagged'],
  en_route: ['arrived', 'flagged'],
  arrived: ['started', 'flagged'],
  started: ['lifted', 'weighed', 'completed', 'flagged'],
  lifted: ['weighed', 'completed', 'flagged'],
  weighed: ['weighed', 'lifted', 'completed', 'flagged'],
  flagged: ['en_route', 'arrived', 'started', 'lifted', 'weighed', 'completed', 'flagged'],
  completed: [],
};

function getAllowedNextStatuses(currentStatus, orderState) {
  if (orderState === 'completed' || orderState === 'signed' || currentStatus === 'completed') {
    return [];
  }
  if (!currentStatus) {
    return ALLOWED_NEXT_STATUSES[null];
  }
  return ALLOWED_NEXT_STATUSES[currentStatus] || ALLOWED_NEXT_STATUSES[null];
}

function updateStatusButtons(stop) {
  const currentStatus = stop?.last_status || null;
  const isCompleted = currentStatus === 'completed' || stop?.state === 'completed' || stop?.state === 'signed';
  const grid = document.getElementById('status-grid');
  const label = document.getElementById('section-label-log-status');
  if (!grid) return;

  if (isCompleted) {
    grid.classList.add('hidden');
    if (label) label.classList.add('hidden');
    return;
  }

  grid.classList.remove('hidden');
  if (label) label.classList.remove('hidden');

  const allowed = getAllowedNextStatuses(currentStatus, stop?.state);

  grid.querySelectorAll('.status-btn').forEach((btn) => {
    const btnStatus = btn.dataset.status;
    const isAllowed = allowed.includes(btnStatus);
    btn.disabled = !isAllowed;
    if (isAllowed) {
      btn.classList.remove('disabled');
      btn.removeAttribute('aria-disabled');
    } else {
      btn.classList.add('disabled');
      btn.setAttribute('aria-disabled', 'true');
    }
  });
}

// ─── State ───────────────────────────────────────────────────────────────────

let state = {
  serverUrl:    '',
  database:     '',
  apiKey:       '',
  stops:        [],           // fetched from server
  currentStop:  null,         // stop object shown in #screen-stop
  pendingCount: 0,            // queued items awaiting sync
  pendingPhoto: null,         // base64 photo for current submission
  pendingStatus: null,        // status chosen before modal open
  missedReasons: [],          // wm.missed.reason codes offered in the flag modal
};

let db = null;

// ─── IndexedDB ───────────────────────────────────────────────────────────────

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const idb = e.target.result;
      if (!idb.objectStoreNames.contains(STORE_QUEUE)) {
        const store = idb.createObjectStore(STORE_QUEUE, { keyPath: 'clientUuid' });
        store.createIndex('orderId', 'orderId', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
    };
    req.onsuccess  = (e) => resolve(e.target.result);
    req.onerror    = (e) => reject(e.target.error);
  });
}

function queuePut(entry) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    tx.objectStore(STORE_QUEUE).put(entry);
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

function queueDelete(clientUuid) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    tx.objectStore(STORE_QUEUE).delete(clientUuid);
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

function queueGetAll() {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readonly');
    const req = tx.objectStore(STORE_QUEUE).index('createdAt').getAll();
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

function queueGetForOrder(orderId) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readonly');
    const req = tx.objectStore(STORE_QUEUE).index('orderId').getAll(orderId);
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

/** Updates of this stop still waiting to be sent (rejected ones excluded). */
async function queueCountForOrder(orderId) {
  return (await queueGetForOrder(orderId)).filter((e) => !e.rejectedReason).length;
}

/** Updates of this stop the server rejected, kept until the driver discards them. */
async function queueRejectedCountForOrder(orderId) {
  return (await queueGetForOrder(orderId)).filter((e) => e.rejectedReason).length;
}

/**
 * Flag a queued update as rejected by the server. Read and write happen in
 * one transaction and an entry that is no longer queued (sent, discarded or
 * signed out meanwhile) is left deleted: re-putting a stale copy would bring
 * back an update that was already dealt with.
 *
 * @returns {Promise<boolean>} whether the entry was still queued and is now flagged
 */
function queueMarkRejected(clientUuid, reason) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_QUEUE, 'readwrite');
    const store = tx.objectStore(STORE_QUEUE);
    let marked = false;
    const req = store.get(clientUuid);
    req.onsuccess = (e) => {
      const entry = e.target.result;
      if (entry) {
        entry.rejectedReason = reason;
        store.put(entry);
        marked = true;
      }
    };
    tx.oncomplete = () => resolve(marked);
    tx.onerror = (e) => reject(e.target.error);
  });
}

// ─── Credential Storage ──────────────────────────────────────────────────────

function normalizeServerUrl(url) {
  let cleaned = (url || '').trim().replace(/\/+$/, '');
  if (cleaned && !/^https?:\/\//i.test(cleaned)) {
    cleaned = `${window.location.protocol}//${cleaned}`;
  }
  return cleaned;
}

function saveCredentials(serverUrl, apiKey, database = '') {
  localStorage.setItem('wm_server_url', normalizeServerUrl(serverUrl));
  localStorage.setItem('wm_api_key', (apiKey || '').trim());
  localStorage.setItem('wm_database', (database || '').trim());
}

function loadCredentials() {
  return {
    serverUrl: normalizeServerUrl(localStorage.getItem('wm_server_url') || ''),
    apiKey:    (localStorage.getItem('wm_api_key') || '').trim(),
    database:  (localStorage.getItem('wm_database') || '').trim(),
  };
}

function clearCredentials() {
  localStorage.removeItem('wm_missed_reasons');
  localStorage.removeItem('wm_server_url');
  localStorage.removeItem('wm_api_key');
  localStorage.removeItem('wm_database');
  localStorage.removeItem('wm_stops');
}

// ─── Saved Route ─────────────────────────────────────────────────────────────

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`;
}

/** Keep today's stops on the device, so the list survives a restart offline. */
function saveStops() {
  try {
    localStorage.setItem('wm_stops', JSON.stringify({ date: todayKey(), stops: state.stops }));
  } catch (e) {
    console.warn('[wm-driver] could not save the route:', e.message);
  }
}

/** Stops saved today by saveStops(); [] when there are none or they are from another day. */
function loadStops() {
  try {
    const saved = JSON.parse(localStorage.getItem('wm_stops') || 'null');
    return saved && saved.date === todayKey() && Array.isArray(saved.stops) ? saved.stops : [];
  } catch (e) {
    return [];
  }
}

// ─── API Client ──────────────────────────────────────────────────────────────

/**
 * Odoo JSON-RPC 2.0 wrapper.
 * For Odoo 17+ the JSON-RPC body format is:
 *   { jsonrpc: '2.0', method: 'call', id: <n>, params: { ... } }
 * The response is:
 *   { jsonrpc: '2.0', id: <n>, result: {...} }  or  { ..., error: {...} }
 */
let _rpcId = 1;
async function apiCall(method, params = {}) {
  let base = state.serverUrl || '';
  if (base && typeof window !== 'undefined' && base === window.location.origin) {
    base = '';
  }
  const url = `${base}${method}`;
  const body = JSON.stringify({
    jsonrpc: '2.0',
    method: 'call',
    id: _rpcId++,
    params,
  });
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${state.apiKey}`,
  };
  if (state.database) {
    headers['X-Odoo-Database'] = state.database;
  }
  let response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers,
      credentials: 'omit',
      body,
    });
  } catch (e) {
    // Connection dropped / server unreachable: the request may be retried
    throw apiError(`Network error: ${e.message}`, true);
  }
  if (!response.ok) {
    // Server down, auth or rate limiting problems are temporary for a queued
    // update: keep it and retry later
    const retryable = response.status >= 500 || [401, 403, 408, 429].includes(response.status);
    if (response.status === 401) {
      throw apiError('HTTP 401: Unauthorized. Please check that your API key is correct and belongs to an active user.', retryable);
    }
    if (response.status === 403) {
      throw apiError('HTTP 403: Forbidden. Database or user permission conflict.', retryable);
    }
    throw apiError(`HTTP ${response.status}`, retryable);
  }
  const json = await response.json();
  if (json.error) {
    // The server processed and rejected the request (e.g. validation error):
    // sending it again will fail the same way
    const msg = json.error.data?.message || json.error.message || JSON.stringify(json.error);
    throw apiError(msg, false);
  }
  return json.result;
}

function apiError(message, retryable) {
  const err = new Error(message);
  err.retryable = retryable;
  return err;
}

/**
 * Fetch available databases from server and populate #select-database dropdown.
 */
async function loadDatabases(serverUrl) {
  const dbSelect = document.getElementById('select-database');
  if (!dbSelect) return;

  const rawUrl = serverUrl || document.getElementById('input-server-url')?.value || state.serverUrl || window.location.origin;
  const url = normalizeServerUrl(rawUrl);
  let base = url;
  if (base && typeof window !== 'undefined' && base === window.location.origin) {
    base = '';
  }

  dbSelect.disabled = true;
  dbSelect.innerHTML = '<option value="" disabled selected>Loading databases...</option>';

  let databases = [];
  try {
    const res = await fetch(`${base}/driver/app/dbs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: _rpcId++, params: {} }),
    });
    if (res.ok) {
      const data = await res.json();
      const resVal = data.result;
      if (resVal && Array.isArray(resVal.databases)) {
        databases = resVal.databases;
      } else if (Array.isArray(resVal)) {
        databases = resVal;
      }
    }
  } catch (_) {}

  // Fallback to /web/database/list if /driver/app/dbs didn't return
  if (!databases || databases.length === 0) {
    try {
      const res = await fetch(`${base}/web/database/list`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: _rpcId++, params: {} }),
      });
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data.result)) {
          databases = data.result;
        }
      }
    } catch (_) {}
  }

  dbSelect.innerHTML = '';

  if (!databases || databases.length === 0) {
    dbSelect.innerHTML = '<option value="" disabled selected>No databases found</option>';
    dbSelect.disabled = false;
    return;
  }

  let matched = false;
  databases.forEach((dbName) => {
    const opt = document.createElement('option');
    opt.value = dbName;
    opt.textContent = dbName;
    if (state.database && state.database === dbName) {
      opt.selected = true;
      matched = true;
    }
    dbSelect.appendChild(opt);
  });

  if (databases.length === 1) {
    dbSelect.value = databases[0];
    state.database = databases[0];
  } else if (!matched) {
    const promptOpt = document.createElement('option');
    promptOpt.value = '';
    promptOpt.textContent = 'Choose a database...';
    promptOpt.disabled = true;
    promptOpt.selected = true;
    dbSelect.insertBefore(promptOpt, dbSelect.firstChild);
    dbSelect.value = '';
  }

  dbSelect.disabled = false;
}

// ─── Geolocation ─────────────────────────────────────────────────────────────

// The phone's position is followed while a route screen is open, so a status
// tap uses a fix that is already there instead of making the driver wait for
// one. Without a recent fix a tap waits briefly, then the update is sent with
// no position (null) and the server records an estimated location instead.
const LOCATION = {
  maxAgeMs: 2 * 60 * 1000,  // older fixes are not used for a status update
  waitMs:   3000,           // how long a tap waits when there is no recent fix
};

const geo = {
  watchId: null,   // id of the running watchPosition, or null
  fix:     null,   // latest {latitude, longitude, at}
  problem: '',     // '' | 'denied' | 'insecure' | 'unsupported'
  waiters: [],     // taps waiting for the next fix
};

/** Why this page cannot get a position at all, or '' when it can try. */
function locationBlocker() {
  if (!navigator.geolocation) return 'unsupported';
  // Browsers (and the Android WebView) refuse geolocation on plain http pages
  if (window.isSecureContext === false) return 'insecure';
  return '';
}

const LOCATION_MESSAGES = {
  denied:      'Location is off for this app, so status updates are saved without your position.',
  insecure:    'Location needs a secure (https) server address, so status updates are saved without your position.',
  unsupported: 'This device cannot share its location, so status updates are saved without your position.',
};

function setLocationProblem(problem) {
  geo.problem = problem;
  const banner = document.getElementById('location-banner');
  if (!banner) return;
  const canOpenSettings = problem === 'denied' && !!NATIVE && typeof NATIVE.openAppSettings === 'function';
  const text = document.getElementById('location-banner-text');
  if (text) {
    text.textContent = (LOCATION_MESSAGES[problem] || '') + (canOpenSettings ? ' Tap to turn it on.' : '');
  }
  banner.classList.toggle('clickable', canOpenSettings);
  banner.classList.toggle('hidden', !problem);
}

function onLocationFix(pos) {
  geo.fix = {
    latitude:  pos.coords.latitude,
    longitude: pos.coords.longitude,
    at:        pos.timestamp || Date.now(),
  };
  if (geo.problem) setLocationProblem('');
  geo.waiters.splice(0).forEach((notify) => notify(geo.fix));
}

function onLocationError(err) {
  // No signal or a slow fix (codes 2 and 3) is normal on the road: keep watching.
  if (err && err.code === 1) {
    setLocationProblem('denied');
    geo.waiters.splice(0).forEach((notify) => notify(null));
  }
}

function startLocationTracking() {
  if (geo.watchId !== null) return;
  const blocker = locationBlocker();
  if (blocker) {
    setLocationProblem(blocker);
    return;
  }
  geo.watchId = navigator.geolocation.watchPosition(onLocationFix, onLocationError, {
    enableHighAccuracy: true,
    maximumAge: 30000,
  });
}

function stopLocationTracking() {
  if (geo.watchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(geo.watchId);
  }
  geo.watchId = null;
}

/** Track the position only while a route screen is open and visible. */
function updateLocationTracking() {
  const routeOpen = ['screen-home', 'screen-stop'].some(
    (id) => !document.getElementById(id)?.classList.contains('hidden'));
  if (routeOpen && document.visibilityState !== 'hidden') {
    startLocationTracking();
  } else {
    stopLocationTracking();
  }
}

/**
 * Position for a status update: the latest fix when it is recent, otherwise
 * the first one to arrive within LOCATION.waitMs. Resolves to
 * {latitude: null, longitude: null} when there is none.
 */
function getPosition() {
  const toPosition = (fix) => (fix
    ? { latitude: fix.latitude, longitude: fix.longitude }
    : { latitude: null, longitude: null });

  if (geo.fix && Date.now() - geo.fix.at <= LOCATION.maxAgeMs) {
    return Promise.resolve(toPosition(geo.fix));
  }
  const blocker = locationBlocker();
  if (blocker) {
    setLocationProblem(blocker);
    return Promise.resolve(toPosition(null));
  }
  return new Promise((resolve) => {
    let timer = null;
    const notify = (fix) => {
      clearTimeout(timer);
      const i = geo.waiters.indexOf(notify);
      if (i >= 0) geo.waiters.splice(i, 1);
      resolve(toPosition(fix));
    };
    geo.waiters.push(notify);
    timer = setTimeout(() => notify(null), LOCATION.waitMs);
    // A quick network-based fix usually arrives before the GPS one
    navigator.geolocation.getCurrentPosition(onLocationFix, onLocationError, {
      enableHighAccuracy: false,
      maximumAge: LOCATION.maxAgeMs,
      timeout: LOCATION.waitMs,
    });
    startLocationTracking();
  });
}

// ─── Toast ───────────────────────────────────────────────────────────────────

let toastTimer = null;
function showToast(message, type = 'info', duration = 2800) {
  const el = document.getElementById('toast');
  el.textContent = message;
  el.className = `toast ${type}`;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), duration);
}

// ─── Screen Navigation ───────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll('.screen').forEach((s) => s.classList.add('hidden'));
  document.getElementById(id).classList.remove('hidden');
  updateLocationTracking();
}

// ─── Sync Indicator ──────────────────────────────────────────────────────────

async function refreshSyncIndicator() {
  const items = (await queueGetAll()).filter((e) => !e.rejectedReason);
  state.pendingCount = items.length;
  const dot = document.getElementById('sync-indicator');
  if (!navigator.onLine) {
    dot.className = 'sync-dot offline';
    dot.title = 'Offline';
  } else if (items.length > 0) {
    dot.className = 'sync-dot pending';
    dot.title = `${items.length} update(s) pending sync`;
  } else {
    dot.className = 'sync-dot synced';
    dot.title = 'All synced';
  }
}

// ─── Offline Queue Retry ─────────────────────────────────────────────────────

// Status updates are sent one at a time, in queue order. Syncs are started from
// several places (app start, the 'online' event, the service worker, a tap while
// online); if two overlapped, the same update would be posted twice and the
// losing copy would come back as a rejection of an update that was in fact saved.
let sendChain = Promise.resolve();

function withSendLock(fn) {
  const run = sendChain.then(fn);
  sendChain = run.catch(() => {});
  return run;
}

/** Send every queued update (serialized with all other sends). */
function syncQueue() {
  return withSendLock(drainQueue);
}

/** Body of syncQueue; only call it while holding the send lock. */
async function drainQueue() {
  if (!navigator.onLine) return;
  // Items the server rejected stay in the queue (flagged) so the driver's
  // weights and photos are never silently lost; they are not retried.
  const items = (await queueGetAll()).filter((e) => !e.rejectedReason);
  if (!items.length) return;

  let synced = 0;
  const rejected = [];
  for (const item of items) {
    try {
      const result = await apiCall(
        `/driver/api/stop/${item.orderId}/status`,
        {
          status: item.status,
          client_uuid: item.clientUuid,
          latitude: item.latitude,
          longitude: item.longitude,
          note: item.note || '',
          photo: item.photo || null,
          timestamp: item.timestamp,
          line_weights: item.lineWeights || null,
          removed_category_ids: item.removedCategoryIds || null,
          missed_reason_id: item.missedReasonId || null,
        },
      );
      if (result.log_id || result.duplicate) {
        await queueDelete(item.clientUuid);
        synced++;
      } else if (result.error) {
        // Rejected by the server (invalid transition, already completed, ...):
        // keep the data but flag it so it is not retried forever, and tell the driver
        const reason = result.message || result.error;
        if (await queueMarkRejected(item.clientUuid, reason)) {
          rejected.push(reason);
        }
      }
    } catch (err) {
      console.warn('[wm-driver] Sync retry failed for', item.clientUuid, err);
      if (err.retryable) {
        // Still offline / server unavailable: retry the rest on the next online event
        break;
      }
      // Server-side error for this item only: keep it (flagged), keep syncing the others
      if (await queueMarkRejected(item.clientUuid, err.message)) {
        rejected.push(err.message);
      }
    }
  }
  if (synced > 0) {
    showToast(`✅ Synced ${synced} offline update${synced > 1 ? 's' : ''}`, 'success');
  }
  if (rejected.length) {
    showToast(`${rejected.length} offline update${rejected.length > 1 ? 's were' : ' was'} rejected: ${rejected.join('; ')}`, 'error', 8000);
    await fetchTodayRoute();
  }
  if (synced > 0 || rejected.length) {
    await refreshSyncIndicator();
  }
}

// ─── Stop List Rendering ─────────────────────────────────────────────────────

/**
 * Escape a server/user-provided value before interpolating it into innerHTML.
 */
function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatTime(dtStr) {
  if (!dtStr) return '';
  const d = new Date(dtStr.replace(' ', 'T') + (dtStr.includes('T') ? '' : 'Z'));
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function statusClass(status) {
  if (status === 'completed') return 'completed';
  if (status === 'flagged')   return 'flagged';
  if (status && status !== 'en_route') return 'in-progress';
  return '';
}

async function renderStopList() {
  const list = document.getElementById('stop-list');
  const empty = document.getElementById('empty-state');
  const badge = document.getElementById('stop-count');

  badge.textContent = `${state.stops.length} stop${state.stops.length !== 1 ? 's' : ''}`;

  if (!state.stops.length) {
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  const fragments = await Promise.all(state.stops.map(async (stop) => {
    const pending = await queueCountForOrder(stop.order_id);
    const rejectedCount = await queueRejectedCountForOrder(stop.order_id);
    const statusLabel = STATUS_LABELS[stop.last_status] || 'Not Started';
    const pillClass = stop.last_status
      ? (stop.last_status === 'completed' ? 'completed' : stop.last_status === 'flagged' ? 'flagged' : '')
      : 'none';

    return `
      <div class="stop-card status-${statusClass(stop.last_status)}"
           data-order-id="${escapeHtml(stop.order_id)}"
           role="button" tabindex="0">
        <div class="stop-card-header">
          <span class="stop-order-name">${escapeHtml(stop.name || 'Order #' + stop.order_id)}</span>
          <span class="stop-status-pill ${pillClass}">${statusLabel}</span>
        </div>
        <div class="stop-customer">${escapeHtml(stop.customer || '—')}</div>
        <div class="stop-address">${escapeHtml(stop.address || '—')}</div>
        <div class="stop-time">
          <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
            <path fill-rule="evenodd" d="M8 1.5A6.5 6.5 0 1 0 8 14.5 6.5 6.5 0 0 0 8 1.5zM0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8zm8-4a1 1 0 0 1 1 1v3.586l2.207 2.207a1 1 0 0 1-1.414 1.414l-2.5-2.5A1 1 0 0 1 7 9V5a1 1 0 0 1 1-1z" clip-rule="evenodd"/>
          </svg>
          ${stop.scheduled_start ? escapeHtml(formatTime(stop.scheduled_start)) : 'Unscheduled'}
        </div>
        ${pending > 0 ? `<div class="stop-pending-badge">⏳ ${pending} update${pending > 1 ? 's' : ''} pending sync</div>` : ''}
        ${rejectedCount > 0 ? `<div class="stop-rejected-badge">⚠ ${rejectedCount} update${rejectedCount > 1 ? 's' : ''} rejected — open to review</div>` : ''}
      </div>
    `;
  }));

  list.innerHTML = fragments.join('');

  // Attach click handlers
  list.querySelectorAll('.stop-card').forEach((card) => {
    card.addEventListener('click', () => {
      const orderId = parseInt(card.dataset.orderId);
      const stop = state.stops.find((s) => s.order_id === orderId);
      if (stop) openStopDetail(stop);
    });
  });
}

// ─── Stop Detail ─────────────────────────────────────────────────────────────

async function openStopDetail(stop) {
  state.currentStop = stop;
  document.getElementById('stop-header-title').textContent = stop.name || `Stop #${stop.order_id}`;
  document.getElementById('stop-detail-name').textContent = stop.name || `Order #${stop.order_id}`;
  document.getElementById('stop-detail-customer').textContent = stop.customer || '—';
  document.getElementById('stop-detail-address').textContent  = stop.address || '—';
  document.getElementById('stop-detail-time').textContent =
    stop.scheduled_start ? `Scheduled: ${formatTime(stop.scheduled_start)}` : '';

  const badge = document.getElementById('current-status-badge');
  badge.textContent = STATUS_LABELS[stop.last_status] || 'Not started';
  badge.style.color = stop.last_status === 'completed' ? 'var(--success)'
    : stop.last_status === 'flagged' ? 'var(--danger)' : '';

  updateStatusButtons(stop);

  await renderLogHistory(stop);
  showScreen('screen-stop');
}

async function renderLogHistory(stop) {
  const container = document.getElementById('log-history');

  // Fetch pending entries for this stop from IndexedDB
  const pending = (await queueGetAll()).filter((e) => e.orderId === stop.order_id);
  const pendingEntries = pending.map((e) => ({
    clientUuid: e.clientUuid,
    status: e.status,
    timestamp: e.timestamp,
    note: e.note,
    rejectedReason: e.rejectedReason || '',
  }));

  // Combined list with pending first (newest events), then server-confirmed history
  // (We don't have server logs in the client cache; in a fuller implementation you'd
  //  cache them locally, but the pending ones are the most important to show.)
  if (!pendingEntries.length) {
    container.innerHTML = `<div class="text-muted" style="padding:12px;font-size:0.85rem;">
      ${stop.last_status
        ? `Last recorded: <strong>${escapeHtml(STATUS_LABELS[stop.last_status] || stop.last_status)}</strong> at ${escapeHtml(formatTime(stop.last_status_time))}`
        : 'No status events recorded yet.'}
    </div>`;
    return;
  }

  container.innerHTML = pendingEntries.map((e) => `
    <div class="log-entry ${e.rejectedReason ? 'offline-rejected' : 'offline-pending'}">
      <span class="log-entry-status">${escapeHtml(STATUS_LABELS[e.status] || e.status)}</span>
      <div class="log-entry-meta">
        <div class="log-entry-time">${escapeHtml(formatTime(e.timestamp))}</div>
        ${e.note ? `<div class="log-entry-note">"${escapeHtml(e.note)}"</div>` : ''}
        ${e.rejectedReason
          ? `<div class="log-rejected-tag">⚠ Not accepted by the server: ${escapeHtml(e.rejectedReason)}</div>
             <button type="button" class="btn-discard-rejected" data-client-uuid="${escapeHtml(e.clientUuid)}">Discard</button>`
          : '<div class="log-pending-tag">⏳ Pending sync</div>'}
      </div>
    </div>
  `).join('');
}

// ─── Status Submission ───────────────────────────────────────────────────────

function generateClientUuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for non-secure contexts (e.g. plain HTTP on LAN IP addresses)
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

async function submitStatus(orderId, status, note = '', photo = null, lineWeights = null, removedCategoryIds = null, missedReasonId = null) {
  const clientUuid = generateClientUuid();
  const { latitude, longitude } = await getPosition();
  const timestamp = new Date().toISOString().replace('T', ' ').split('.')[0];

  const queueEntry = {
    clientUuid,
    orderId,
    status,
    note,
    photo,          // base64 string or null
    lineWeights,    // array of {category_id, weight} or null
    removedCategoryIds,  // categories the driver removed in the weigh modal, or null
    missedReasonId,      // wm.missed.reason id, set on a 'flagged' submission
    latitude,
    longitude,
    timestamp,
    createdAt: Date.now(),
  };

  // 1. Write to IndexedDB immediately (offline-safe)
  await queuePut(queueEntry);

  // 2. Optimistic UI update
  const stop = state.stops.find((s) => s.order_id === orderId);
  if (stop) {
    stop.last_status = status;
    stop.last_status_time = timestamp;
    if (lineWeights) {
      stop.lines = lineWeights.map((lw) => {
        const allowed = stop.allowed_categories?.find((ac) => ac.category_id === lw.category_id);
        const existingLine = stop.lines?.find((l) => l.category_id === lw.category_id);
        return {
          line_id: existingLine ? existingLine.line_id : lw.category_id,
          category_id: lw.category_id,
          category_name: allowed ? allowed.category_name : (existingLine ? existingLine.category_name : 'Category #' + lw.category_id),
          estimated_weight: existingLine ? existingLine.estimated_weight : 0.0,
          weight: lw.weight,
        };
      });
    }
  }
  if (state.currentStop && state.currentStop.order_id === orderId) {
    state.currentStop.last_status = status;
    state.currentStop.last_status_time = timestamp;
    if (lineWeights) {
      state.currentStop.lines = lineWeights.map((lw) => {
        const allowed = state.currentStop.allowed_categories?.find((ac) => ac.category_id === lw.category_id);
        const existingLine = state.currentStop.lines?.find((l) => l.category_id === lw.category_id);
        return {
          line_id: existingLine ? existingLine.line_id : lw.category_id,
          category_id: lw.category_id,
          category_name: allowed ? allowed.category_name : (existingLine ? existingLine.category_name : 'Category #' + lw.category_id),
          estimated_weight: existingLine ? existingLine.estimated_weight : 0.0,
          weight: lw.weight,
        };
      });
    }
    const badge = document.getElementById('current-status-badge');
    badge.textContent = STATUS_LABELS[status];
    badge.style.color = status === 'completed' ? 'var(--success)' : status === 'flagged' ? 'var(--danger)' : '';

    // Mirror the order transitions the server applies, so the buttons the
    // driver sees next match what will be accepted.
    if (status === 'flagged') {
      state.currentStop.state = 'missed';
    } else if (state.currentStop.state === 'missed') {
      // Carrying on after a flag reopens the stop. The server picks between
      // dispatched and in_progress from the real start time; the next route
      // refresh brings its answer back.
      state.currentStop.state = 'in_progress';
    }
    if (status === 'started' && state.currentStop.state === 'dispatched') {
      state.currentStop.state = 'in_progress';
    } else if (status === 'completed') {
      state.currentStop.state = 'completed';
    }
    updateStatusButtons(state.currentStop);

    await renderLogHistory(state.currentStop);
  }
  saveStops();

  await refreshSyncIndicator();
  showToast(`${STATUS_LABELS[status]} logged`, 'success');

  // 3. Try to POST immediately (under the send lock, see withSendLock)
  if (navigator.onLine) {
    await withSendLock(() => sendQueuedNow(queueEntry));
  } else {
    showToast('Offline — update queued', 'warning');
  }
}

/**
 * Send a just-queued update right away. Runs under the send lock. When older
 * updates are still waiting, the whole queue is sent instead so the server
 * receives the stop's updates in the order they were made.
 */
async function sendQueuedNow(queueEntry) {
  const {
    clientUuid, orderId, status, note, photo, lineWeights, removedCategoryIds,
    missedReasonId, latitude, longitude, timestamp,
  } = queueEntry;
  const queued = await queueGetAll();
  if (!queued.some((e) => e.clientUuid === clientUuid)) {
    return; // already sent by a sync that ran while this one waited
  }
  if (queued.some((e) => !e.rejectedReason && e.clientUuid !== clientUuid)) {
    await drainQueue();
    return;
  }
  try {
    const result = await apiCall(`/driver/api/stop/${orderId}/status`, {
      status,
      client_uuid: clientUuid,
      latitude,
      longitude,
      note: note || '',
      photo: photo || null,
      timestamp,
      line_weights: lineWeights || null,
      removed_category_ids: removedCategoryIds || null,
      missed_reason_id: missedReasonId || null,
    });
    if (result.log_id || result.duplicate) {
      await queueDelete(clientUuid);
      await refreshSyncIndicator();
    } else if (result.error) {
      // Rejected by the server: undo the optimistic update
      await queueDelete(clientUuid);
      await refreshSyncIndicator();
      showToast(result.message || result.error, 'error', 6000);
      await fetchTodayRoute();
    }
  } catch (err) {
    console.warn('[wm-driver] Online submit failed:', err.message);
    if (err.retryable) {
      // Connection dropped mid-request: keep it queued (client_uuid makes the
      // retry idempotent if the server did receive it)
      showToast('Connection problem — update saved and will sync automatically', 'warning', 4500);
    } else {
      await queueDelete(clientUuid);
      await refreshSyncIndicator();
      showToast(err.message || 'Failed to submit status update', 'error', 4500);
      await fetchTodayRoute();
    }
  }
}

// ─── Photo Helpers ───────────────────────────────────────────────────────────

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = (e) => resolve(e.target.result.split(',')[1]); // strip data:...;base64,
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function setupPhotoInput(inputId, previewId) {
  const input   = document.getElementById(inputId);
  const preview = document.getElementById(previewId);
  input.addEventListener('change', async () => {
    const file = input.files[0];
    if (!file) return;
    try {
      const b64 = await readFileAsBase64(file);
      state.pendingPhoto = b64;
      const img = document.createElement('img');
      img.src = `data:${file.type};base64,${b64}`;
      preview.innerHTML = '';
      preview.appendChild(img);
      preview.classList.remove('hidden');
    } catch (e) {
      console.error('Photo read error:', e);
    }
  });
}

// ─── Flag Modal ──────────────────────────────────────────────────────────────

/** Reason codes cached by the last route fetch; [] before the first one. */
function loadMissedReasons() {
  try {
    const cached = JSON.parse(localStorage.getItem('wm_missed_reasons') || '[]');
    return Array.isArray(cached) ? cached : [];
  } catch (e) {
    return [];
  }
}

function renderFlagReasons() {
  const select = document.getElementById('flag-reason');
  if (!select) return;
  select.innerHTML = '<option value="">Select a reason...</option>'
    + state.missedReasons.map(
      (r) => `<option value="${r.reason_id}">${escapeHtml(r.reason_name)}</option>`,
    ).join('');
}

function openFlagModal() {
  document.getElementById('flag-note').value = '';
  document.getElementById('flag-photo-input').value = '';
  document.getElementById('flag-photo-preview').classList.add('hidden');
  renderFlagReasons();
  state.pendingPhoto = null;
  document.getElementById('modal-flag').classList.remove('hidden');
  setTimeout(() => document.getElementById('flag-reason').focus(), 300);
}

function closeFlagModal() {
  document.getElementById('modal-flag').classList.add('hidden');
  state.pendingPhoto = null;
}

// ─── Photo Modal (non-flag statuses) ─────────────────────────────────────────

function openPhotoModal(status) {
  state.pendingStatus = status;
  state.pendingPhoto  = null;
  document.getElementById('status-photo-input').value = '';
  document.getElementById('status-photo-preview').classList.add('hidden');
  document.getElementById('photo-modal-title').textContent = `Log: ${STATUS_LABELS[status]}`;
  document.getElementById('modal-photo').classList.remove('hidden');
}

function closePhotoModal() {
  document.getElementById('modal-photo').classList.add('hidden');
  state.pendingStatus = null;
  state.pendingPhoto  = null;
}

// ─── Weighed Modal (Category Weight Entry) ───────────────────────────────────

function renderWeighedLineItem(catId, categoryName, estWeight, initialWeight = 0) {
  catId = escapeHtml(catId);
  return `
    <div class="weighed-line-item" id="weighed-item-cat-${catId}" data-category-id="${catId}">
      <div class="weighed-line-info">
        <span class="weighed-line-name">${escapeHtml(categoryName)}</span>
        ${estWeight ? `<span class="weighed-line-est">Est: ${escapeHtml(estWeight)} kg</span>` : ''}
      </div>
      <div class="weighed-input-wrapper">
        <input type="number" id="input-weight-cat-${catId}" data-category-id="${catId}" step="0.01" min="0" value="${escapeHtml(initialWeight || 0)}" />
        <span class="weighed-unit">kg</span>
      </div>
      <button type="button" class="btn-delete-line" data-category-id="${catId}" title="Remove category">
        <svg viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"/>
        </svg>
      </button>
    </div>
  `;
}

function openWeighedModal() {
  const linesContainer = document.getElementById('weighed-lines-list');
  const selectEl = document.getElementById('weighed-category-select');
  linesContainer.innerHTML = '';
  if (selectEl) selectEl.innerHTML = '';
  state.pendingPhoto = null;
  document.getElementById('weighed-photo-input').value = '';
  document.getElementById('weighed-photo-preview').classList.add('hidden');

  const allowed = state.currentStop?.allowed_categories || [];
  const lines = state.currentStop?.lines || [];

  if (selectEl) {
    if (!allowed.length) {
      selectEl.innerHTML = `<option value="">-- No Waste Categories Available --</option>`;
    } else {
      selectEl.innerHTML = `<option value="">+ Select a Waste Category to Add...</option>` +
        allowed.map((c) => `<option value="${escapeHtml(c.category_id)}">${escapeHtml(c.category_name)}</option>`).join('');
    }
  }

  // Pre-fill existing order lines
  if (!lines.length) {
    linesContainer.innerHTML = `<div id="weighed-empty-hint" class="text-muted" style="padding:14px;text-align:center;">Select a waste category from the dropdown above to record its weight.</div>`;
  } else {
    linesContainer.innerHTML = lines.map((l) =>
      renderWeighedLineItem(l.category_id, l.category_name, l.estimated_weight, l.weight || 0)
    ).join('');
  }

  document.getElementById('modal-weighed').classList.remove('hidden');
}

function closeWeighedModal() {
  document.getElementById('modal-weighed').classList.add('hidden');
  state.pendingPhoto = null;
}

// ─── Today's Route Fetch ─────────────────────────────────────────────────────

async function fetchTodayRoute() {
  const btn = document.getElementById('btn-refresh');
  btn.classList.add('loading');
  try {
    const result = await apiCall('/driver/api/route/today', {});
    state.stops = result.stops || [];
    if (Array.isArray(result.missed_reasons)) {
      // Cached on the device: a driver out of signal still needs this list to
      // flag a stop, and the route is only ever fetched online.
      state.missedReasons = result.missed_reasons;
      try {
        localStorage.setItem('wm_missed_reasons', JSON.stringify(state.missedReasons));
      } catch (e) {
        console.warn('[wm-driver] could not cache missed reasons:', e.message);
      }
    }
    saveStops();
    await renderStopList();
    await refreshSyncIndicator();
  } catch (err) {
    const msg = state.stops.length
      ? `Server unreachable, showing the saved route: ${err.message}`
      : `Failed to load route: ${err.message}`;
    showToast(msg, 'error', 4000);
    console.error('[wm-driver] fetchTodayRoute:', err);
  } finally {
    btn.classList.remove('loading');
  }
}

// ─── Init ────────────────────────────────────────────────────────────────────

async function init() {
  db = await openDB();

  const creds = loadCredentials();
  state.serverUrl = creds.serverUrl;
  state.apiKey    = creds.apiKey;
  state.database  = creds.database;
  state.missedReasons = loadMissedReasons();

  // Set up today date label
  const todayLabel = document.getElementById('today-date');
  if (todayLabel) {
    todayLabel.textContent = new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' });
  }

  // Register service worker. The Android app ships these files itself, so a
  // worker there would only add a second, possibly stale, copy: remove it.
  if (NATIVE && 'serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations()
      .then((regs) => regs.forEach((r) => r.unregister()))
      .catch(() => {});
  } else if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/driver/app/sw.js', { scope: '/driver/app' })
      .then(() => {
        // Listen for SW sync trigger
        navigator.serviceWorker.addEventListener('message', (e) => {
          if (e.data && e.data.type === 'SYNC_QUEUE') syncQueue();
        });
      })
      .catch((err) => console.warn('[wm-driver] SW registration failed:', err));
  }

  // Online/offline detection
  window.addEventListener('online',  () => {
    document.getElementById('offline-banner')?.classList.add('hidden');
    refreshSyncIndicator();
    syncQueue();
  });
  window.addEventListener('offline', () => {
    document.getElementById('offline-banner')?.classList.remove('hidden');
    refreshSyncIndicator();
  });
  if (!navigator.onLine) {
    document.getElementById('offline-banner')?.classList.remove('hidden');
  }

  // Location: follow the position only while the app is on screen
  document.addEventListener('visibilitychange', updateLocationTracking);
  document.getElementById('location-banner')?.addEventListener('click', () => {
    if (geo.problem === 'denied' && NATIVE && typeof NATIVE.openAppSettings === 'function') {
      NATIVE.openAppSettings();
    }
  });

  // ── Setup screen ─────────────────────────────────────────────────────────
  const serverUrlInput = document.getElementById('input-server-url');
  const dbSelect       = document.getElementById('select-database');

  const onServerUrlEntered = () => {
    if (nativeSwitchServer(serverUrlInput.value)) return;
    if (onNativePlaceholder()) return;
    loadDatabases(serverUrlInput.value.trim());
  };
  serverUrlInput?.addEventListener('blur', onServerUrlEntered);
  serverUrlInput?.addEventListener('change', onServerUrlEntered);

  dbSelect?.addEventListener('change', (e) => {
    state.database = e.target.value;
  });

  document.getElementById('btn-save-key').addEventListener('click', async () => {
    const serverUrl = serverUrlInput.value.trim();
    const database  = dbSelect ? dbSelect.value.trim() : (state.database || '');
    const apiKey    = document.getElementById('input-api-key').value.trim();
    const errEl     = document.getElementById('setup-error');

    if (!serverUrl || !apiKey) {
      errEl.textContent = 'Server URL and API Key are required.';
      errEl.classList.remove('hidden');
      return;
    }

    // Android app: the server changed, so move there first and pick the database
    if (nativeSwitchServer(serverUrl)) return;

    if (!database) {
      errEl.textContent = 'Please select a database from the dropdown.';
      errEl.classList.remove('hidden');
      return;
    }

    // Quick connectivity test
    state.serverUrl = normalizeServerUrl(serverUrl);
    state.apiKey    = apiKey;
    state.database  = database;
    try {
      // The database is selected per request via the X-Odoo-Database header
      await apiCall('/driver/api/route/today', {});
      saveCredentials(state.serverUrl, state.apiKey, state.database);
      errEl.classList.add('hidden');
      await fetchTodayRoute();
      showScreen('screen-home');
    } catch (err) {
      let msg = err.message || '';
      if (msg.includes('401') || msg.includes('Unauthorized')) {
        msg = `API key is not valid for database "${state.database}". Please verify that your API key was created in this database.`;
      } else if (msg.includes('NetworkError') || msg.includes('Failed to fetch')) {
        msg = 'Unable to reach the server. Check your internet connection and the server address, then try again.';
      }
      errEl.textContent = `Connection failed: ${msg}`;
      errEl.classList.remove('hidden');
    }
  });

  // ── Home screen ───────────────────────────────────────────────────────────
  document.getElementById('btn-refresh')?.addEventListener('click', fetchTodayRoute);
  document.getElementById('btn-logout')?.addEventListener('click', async () => {
    // Pending updates belong to this driver's key: signing out must never leave them
    // to be sent (and rejected) under the next driver. Sync first, then ask.
    if (navigator.onLine) {
      try { await syncQueue(); } catch (e) { console.warn('[wm-driver] sync before sign-out failed', e); }
    }
    const unsent = await queueGetAll();
    if (unsent.length) {
      const ok = window.confirm(
        `${unsent.length} update${unsent.length > 1 ? 's have' : ' has'} not been sent to the server yet. ` +
        'If you sign out now they will be lost. Sign out anyway?');
      if (!ok) return;
      for (const item of unsent) await queueDelete(item.clientUuid);
      await refreshSyncIndicator();
    }
    clearCredentials();
    state.serverUrl = '';
    state.apiKey    = '';
    state.database  = '';
    state.stops     = [];
    document.getElementById('input-server-url').value = window.location.origin;
    document.getElementById('input-api-key').value    = '';
    showScreen('screen-setup');
    await loadDatabases(window.location.origin);
  });

  // ── Stop detail screen ────────────────────────────────────────────────────
  document.getElementById('btn-back')?.addEventListener('click', async () => {
    await renderStopList();
    showScreen('screen-home');
  });

  // Status buttons
  document.querySelectorAll('.status-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.disabled || btn.classList.contains('disabled')) return;
      const status = btn.dataset.status;
      if (!state.currentStop) return;
      const allowed = getAllowedNextStatuses(state.currentStop.last_status, state.currentStop.state);
      if (!allowed.includes(status)) {
        showToast(`Cannot change status to ${STATUS_LABELS[status] || status} from current status`, 'warning');
        return;
      }
      if (status === 'flagged') {
        openFlagModal();
      } else if (status === 'weighed') {
        openWeighedModal();
      } else {
        openPhotoModal(status);
      }
    });
  });

  // ── Flag modal ────────────────────────────────────────────────────────────
  setupPhotoInput('flag-photo-input', 'flag-photo-preview');

  document.getElementById('btn-flag-cancel')?.addEventListener('click', closeFlagModal);
  document.getElementById('btn-flag-confirm')?.addEventListener('click', async () => {
    const reasonId = parseInt(document.getElementById('flag-reason').value, 10);
    const note = document.getElementById('flag-note').value.trim();
    if (!reasonId) {
      showToast('Choose a reason for flagging this stop.', 'error');
      return;
    }
    if (!note) {
      showToast('Describe the issue before flagging this stop.', 'error');
      return;
    }
    const photo = state.pendingPhoto;
    closeFlagModal();
    await submitStatus(state.currentStop.order_id, 'flagged', note, photo, null, null, reasonId);
  });

  // ── Weighed modal ─────────────────────────────────────────────────────────
  setupPhotoInput('weighed-photo-input', 'weighed-photo-preview');

  document.getElementById('weighed-category-select')?.addEventListener('change', (e) => {
    const catId = parseInt(e.target.value);
    if (!catId) return;

    const allowed = state.currentStop?.allowed_categories || [];
    const catObj = allowed.find((c) => c.category_id === catId);
    const categoryName = catObj ? catObj.category_name : 'Category #' + catId;

    const existingItem = document.getElementById(`weighed-item-cat-${catId}`);
    if (existingItem) {
      existingItem.style.borderColor = 'var(--accent)';
      existingItem.style.boxShadow = '0 0 12px rgba(16,185,129,0.25)';
      existingItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      const inp = document.getElementById(`input-weight-cat-${catId}`);
      if (inp) { inp.focus(); inp.select(); }
    } else {
      document.getElementById('weighed-empty-hint')?.remove();

      const existingLine = state.currentStop?.lines?.find((l) => l.category_id === catId);
      const estWeight = existingLine ? existingLine.estimated_weight : 0;
      const initialWeight = existingLine ? (existingLine.weight || 0) : 0;

      const linesContainer = document.getElementById('weighed-lines-list');
      linesContainer.insertAdjacentHTML('beforeend', renderWeighedLineItem(catId, categoryName, estWeight, initialWeight));

      const newItem = document.getElementById(`weighed-item-cat-${catId}`);
      if (newItem) {
        newItem.style.borderColor = 'var(--accent)';
        newItem.style.boxShadow = '0 0 12px rgba(16,185,129,0.25)';
      }
      const inp = document.getElementById(`input-weight-cat-${catId}`);
      if (inp) { inp.focus(); inp.select(); }
    }
    e.target.value = '';
  });

  document.getElementById('log-history')?.addEventListener('click', async (e) => {
    const btn = e.target.closest('.btn-discard-rejected');
    if (!btn) return;
    if (!window.confirm('Discard this update? The server did not accept it, so it will not be recorded.')) return;
    await queueDelete(btn.dataset.clientUuid);
    if (state.currentStop) await renderLogHistory(state.currentStop);
    await renderStopList();
    await refreshSyncIndicator();
  });

  document.getElementById('weighed-lines-list')?.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-delete-line');
    if (!btn) return;
    const catId = btn.dataset.categoryId;
    const item = document.getElementById(`weighed-item-cat-${catId}`);
    if (item) {
      item.remove();
      const remaining = document.querySelectorAll('#weighed-lines-list .weighed-line-item');
      if (!remaining.length) {
        document.getElementById('weighed-lines-list').innerHTML =
          `<div id="weighed-empty-hint" class="text-muted" style="padding:14px;text-align:center;">Select a waste category from the dropdown above to record its weight.</div>`;
      }
    }
  });

  document.getElementById('btn-weighed-cancel')?.addEventListener('click', closeWeighedModal);
  document.getElementById('btn-weighed-confirm')?.addEventListener('click', async () => {
    const inputs = document.querySelectorAll('#weighed-lines-list input[data-category-id]');
    const lineWeights = [];
    inputs.forEach((inp) => {
      const catId = parseInt(inp.dataset.categoryId);
      const val = parseFloat(inp.value) || 0.0;
      lineWeights.push({ category_id: catId, weight: val });
    });
    if (!lineWeights.some((lw) => lw.weight > 0)) {
      showToast('Enter the weight of at least one waste category.', 'error');
      return;
    }

    const photo = state.pendingPhoto;
    // Existing order lines whose row was deleted in the modal are explicit removals
    const removedCategoryIds = (state.currentStop?.lines || [])
      .map((l) => l.category_id)
      .filter((id) => !lineWeights.some((lw) => lw.category_id === id));
    closeWeighedModal();
    if (state.currentStop) {
      await submitStatus(state.currentStop.order_id, 'weighed', '', photo, lineWeights, removedCategoryIds);
    }
  });

  // ── Photo modal ───────────────────────────────────────────────────────────
  setupPhotoInput('status-photo-input', 'status-photo-preview');

  // Cancel logs nothing: a status tapped by mistake is simply dropped.
  document.getElementById('btn-photo-cancel')?.addEventListener('click', closePhotoModal);

  document.getElementById('btn-photo-confirm')?.addEventListener('click', async () => {
    const status = state.pendingStatus;
    const photo  = state.pendingPhoto;
    closePhotoModal();
    if (status && state.currentStop) {
      await submitStatus(state.currentStop.order_id, status, '', photo);
    }
  });

  // Close modals on overlay click
  document.getElementById('modal-flag')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeFlagModal();
  });
  document.getElementById('modal-weighed')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeWeighedModal();
  });
  document.getElementById('modal-photo')?.addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closePhotoModal();
  });

  // ── Kick off ─────────────────────────────────────────────────────────────
  document.getElementById('splash').classList.remove('active');

  if (state.serverUrl && state.apiKey && state.database) {
    document.getElementById('input-server-url').value = state.serverUrl;
    showScreen('screen-home');
    // Show the saved route first: with the server out of reach it is all there is
    state.stops = loadStops();
    await renderStopList();
    await fetchTodayRoute();
    // Also drain any offline queue from previous sessions
    await syncQueue();
  } else if (onNativePlaceholder()) {
    // Android app before any server is chosen: nothing to list yet
    document.getElementById('input-server-url').value = '';
    if (dbSelect) {
      dbSelect.disabled = true;
      dbSelect.innerHTML = '<option value="" disabled selected>Enter the server address first</option>';
    }
    showScreen('screen-setup');
  } else {
    const defaultUrl = state.serverUrl || window.location.origin;
    document.getElementById('input-server-url').value = defaultUrl;
    showScreen('screen-setup');
    await loadDatabases(defaultUrl);
  }
}

// Kick off once DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

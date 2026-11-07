#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    For full details, see https://www.odoo.com/documentation/20.0/legal/licenses/licenses.html
#
#############################################################################
import datetime

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

# Shared helpers injected in front of every browser test.
JS_HELPERS = r"""
const assert = (c, m) => { if (!c) { throw new Error(m); } };
const eq = (a, b, m) => assert(JSON.stringify(a) === JSON.stringify(b),
    m + ': expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitFor = async (cond, m, ms = 4000) => {
    const t = Date.now();
    while (Date.now() - t < ms) { if (await cond()) { return; } await sleep(25); }
    throw new Error('timeout waiting for: ' + m);
};
const $ = (id) => document.getElementById(id);
const isHidden = (id) => $(id).classList.contains('hidden');
const realFetch = window.fetch.bind(window);
window.fetch = (u, o = {}) => realFetch(u, {...o, credentials: 'same-origin'});
const useRealFetch = () => { window.fetch = (u, o = {}) => realFetch(u, {...o, credentials: 'same-origin'}); };
const calls = [];
const stubFetch = (handler) => {
    calls.length = 0;
    window.fetch = async (u, o = {}) => {
        const body = o.body ? JSON.parse(o.body) : null;
        calls.push({url: String(u), opts: o, body});
        return handler(String(u), o, body);
    };
};
const resp = (obj, status = 200) => ({ok: status >= 200 && status < 300, status, json: async () => obj});
const setOnline = (v) => Object.defineProperty(navigator, 'onLine', {get: () => v, configurable: true});
const geoStub = (getCurrentPosition, watchPosition = () => 1, clearWatch = () => {}) =>
    Object.defineProperty(navigator, 'geolocation', {
        value: {getCurrentPosition, watchPosition, clearWatch}, configurable: true});
const setGeo = (lat, lng) => geoStub((ok) => ok({coords: {latitude: lat, longitude: lng}}));
const resetGeo = () => {
    stopLocationTracking();
    geo.fix = null; geo.waiters.length = 0; setLocationProblem('');
    LOCATION.waitMs = 3000; LOCATION.maxAgeMs = 2 * 60 * 1000;
};
const clearQueue = async () => { for (const i of await queueGetAll()) { await queueDelete(i.clientUuid); } };
const entry = (extra) => ({
    clientUuid: crypto.randomUUID(), orderId: 1, status: 'arrived', note: '', photo: null,
    lineWeights: null, latitude: 0, longitude: 0, timestamp: '2026-01-02 10:00:00', createdAt: Date.now(), ...extra});
const mkStop = (extra) => ({
    order_id: 7, name: 'O7', customer: 'Cust', address: 'Addr', scheduled_start: '2026-01-02 10:30:00',
    last_status: null, state: 'dispatched',
    allowed_categories: [{category_id: 1, category_name: 'Alpha'}, {category_id: 2, category_name: 'Beta'}],
    lines: [{line_id: 1, category_id: 1, category_name: 'Alpha', estimated_weight: 5, weight: 0}], ...extra});
const fire = (el, type) => el.dispatchEvent(new Event(type, {bubbles: true}));
const reset = async () => {
    await waitFor(() => !$('select-database').disabled, 'initial database list');
    setOnline(true); setGeo(0, 0); resetGeo();
    await clearQueue();
    localStorage.clear();
    state.serverUrl = ''; state.apiKey = 'K'; state.database = ''; state.stops = [];
    state.currentStop = null; state.pendingPhoto = null; state.pendingStatus = null;
    stubFetch(async () => resp({result: {}}));
};
"""

JS_PURE_HELPERS = r"""
    await reset();
    // getAllowedNextStatuses
    eq(getAllowedNextStatuses(null, 'dispatched'), ['en_route', 'arrived', 'flagged'], 'first statuses');
    eq(getAllowedNextStatuses('en_route', 'dispatched'), ['arrived', 'flagged'], 'after en_route');
    eq(getAllowedNextStatuses('completed', 'dispatched'), [], 'completed status');
    eq(getAllowedNextStatuses('arrived', 'completed'), [], 'completed order');
    eq(getAllowedNextStatuses(null, 'signed'), [], 'signed order');
    eq(getAllowedNextStatuses('unknown', null), ['en_route', 'arrived', 'flagged'], 'unknown status falls back');
    assert(getAllowedNextStatuses('flagged', null).includes('completed'), 'flagged can resume');
    assert(getAllowedNextStatuses('weighed', null).includes('weighed'), 'weigh can be repeated');

    // updateStatusButtons
    const btn = (s) => document.querySelector('#status-grid .status-btn[data-status="' + s + '"]');
    updateStatusButtons({last_status: 'arrived', state: 'in_progress'});
    assert(!btn('started').disabled && btn('started').getAttribute('aria-disabled') === null, 'started enabled');
    assert(btn('en_route').disabled && btn('en_route').getAttribute('aria-disabled') === 'true', 'en_route disabled');
    assert(btn('en_route').classList.contains('disabled'), 'disabled class');
    assert(!$('status-grid').classList.contains('hidden'), 'grid shown');
    updateStatusButtons(null);
    assert(!btn('en_route').disabled && btn('lifted').disabled, 'no stop: first statuses only');
    updateStatusButtons({last_status: 'completed', state: 'dispatched'});
    assert($('status-grid').classList.contains('hidden') && $('section-label-log-status').classList.contains('hidden'),
           'completed stop hides the buttons');
    updateStatusButtons({last_status: null, state: 'signed'});
    assert($('status-grid').classList.contains('hidden'), 'signed stop hides the buttons');
    updateStatusButtons({last_status: null, state: 'dispatched'});
    assert(!$('status-grid').classList.contains('hidden') && !$('section-label-log-status').classList.contains('hidden'),
           'buttons shown again');

    // escapeHtml
    eq(escapeHtml(null), '', 'null'); eq(escapeHtml(undefined), '', 'undefined'); eq(escapeHtml(5), '5', 'number');
    eq(escapeHtml(`<a href="x">&'`), '&lt;a href=&quot;x&quot;&gt;&amp;&#39;', 'special characters');

    // formatTime
    eq(formatTime(''), '', 'empty time'); eq(formatTime(null), '', 'null time');
    assert(/\d/.test(formatTime('2026-01-02 10:30:00')), 'space separated time');
    assert(/\d/.test(formatTime('2026-01-02T10:30:00')), 'ISO time');

    // statusClass
    eq(statusClass('completed'), 'completed', 'completed'); eq(statusClass('flagged'), 'flagged', 'flagged');
    eq(statusClass('arrived'), 'in-progress', 'in progress'); eq(statusClass('en_route'), '', 'en route');
    eq(statusClass(null), '', 'none');

    // normalizeServerUrl
    eq(normalizeServerUrl('  example.com/// '), location.protocol + '//example.com', 'scheme added');
    eq(normalizeServerUrl('http://x.com/'), 'http://x.com', 'trailing slash');
    eq(normalizeServerUrl('HTTPS://x.com'), 'HTTPS://x.com', 'scheme kept');
    eq(normalizeServerUrl(''), '', 'empty'); eq(normalizeServerUrl(null), '', 'null');

    // renderWeighedLineItem
    let html = renderWeighedLineItem(5, 'Plastic <b>', 10, 2.5);
    assert(html.includes('data-category-id="5"') && html.includes('Plastic &lt;b&gt;'), 'name escaped');
    assert(html.includes('Est: 10 kg') && html.includes('value="2.5"'), 'estimate and weight');
    html = renderWeighedLineItem('1"><x', 'N', 0);
    assert(!html.includes('<x') && !html.includes('Est:') && html.includes('value="0"'), 'id escaped, no estimate');
"""

JS_STORAGE_AND_QUEUE = r"""
    await reset();
    // credentials
    saveCredentials('example.com/', '  key  ', ' dbx ');
    eq(loadCredentials(), {serverUrl: location.protocol + '//example.com', apiKey: 'key', database: 'dbx'}, 'saved');
    saveCredentials('http://a.b', 'k');
    eq(loadCredentials().database, '', 'database defaults to empty');
    clearCredentials();
    eq(loadCredentials(), {serverUrl: '', apiKey: '', database: ''}, 'cleared');

    // IndexedDB queue
    const idb = await openDB();
    assert(idb && idb.objectStoreNames.contains('queue'), 'database opens with its queue store');
    idb.close();
    const e1 = entry({orderId: 1, createdAt: 2});
    const e2 = entry({orderId: 2, createdAt: 1});
    await queuePut(e1); await queuePut(e2);
    eq((await queueGetAll()).map((e) => e.orderId), [2, 1], 'ordered by creation time');
    eq(await queueCountForOrder(1), 1, 'count for order 1');
    eq(await queueCountForOrder(99), 0, 'count for unknown order');
    await queuePut({...e1, status: 'started'});
    eq((await queueGetAll()).length, 2, 'put with the same uuid updates');
    await queueDelete(e1.clientUuid);
    eq((await queueGetAll()).map((e) => e.orderId), [2], 'deleted');

    // sync indicator
    const dot = $('sync-indicator');
    await clearQueue();
    await refreshSyncIndicator();
    eq([dot.className, dot.title, state.pendingCount], ['sync-dot synced', 'All synced', 0], 'synced');
    await queuePut(entry({}));
    await refreshSyncIndicator();
    eq([dot.className, dot.title, state.pendingCount], ['sync-dot pending', '1 update(s) pending sync', 1], 'pending');
    await queuePut(entry({rejectedReason: 'bad'}));
    await refreshSyncIndicator();
    eq(state.pendingCount, 1, 'rejected updates are not counted');
    setOnline(false);
    await refreshSyncIndicator();
    eq([dot.className, dot.title], ['sync-dot offline', 'Offline'], 'offline');
"""

JS_API_AND_DATABASES = r"""
    await reset();
    // apiCall
    state.serverUrl = 'https://srv.example'; state.apiKey = 'K'; state.database = 'dbx';
    stubFetch(async () => resp({result: {ok: 1}}));
    eq(await apiCall('/x', {a: 1}), {ok: 1}, 'result returned');
    eq(calls[0].url, 'https://srv.example/x', 'absolute url');
    eq(calls[0].opts.headers['Authorization'], 'Bearer K', 'bearer key');
    eq(calls[0].opts.headers['X-Odoo-Database'], 'dbx', 'database header');
    eq(calls[0].body.params, {a: 1}, 'params');
    state.serverUrl = location.origin; state.database = '';
    await apiCall('/y');
    eq(calls[1].url, '/y', 'same origin uses a relative url');
    assert(!('X-Odoo-Database' in calls[1].opts.headers), 'no database header without a database');
    assert(calls[1].body.id > calls[0].body.id, 'request ids increase');

    const failure = async (handler) => {
        stubFetch(handler);
        try { await apiCall('/z'); } catch (e) { return e; }
        throw new Error('apiCall should have failed');
    };
    let err = await failure(async () => resp({}, 401));
    assert(err.message.includes('Unauthorized') && err.retryable === true, '401');
    err = await failure(async () => resp({}, 403));
    assert(err.message.includes('Forbidden') && err.retryable === true, '403');
    err = await failure(async () => resp({}, 500));
    assert(err.message === 'HTTP 500' && err.retryable === true, '500');
    err = await failure(async () => resp({}, 429));
    assert(err.retryable === true, '429');
    err = await failure(async () => resp({}, 408));
    assert(err.retryable === true, '408');
    err = await failure(async () => resp({}, 404));
    assert(err.message === 'HTTP 404' && err.retryable === false, '404');
    err = await failure(async () => resp({error: {data: {message: 'Boom'}}}));
    assert(err.message === 'Boom' && err.retryable === false, 'rpc error data message');
    err = await failure(async () => resp({error: {message: 'Plain'}}));
    eq(err.message, 'Plain', 'rpc error message');
    err = await failure(async () => resp({error: {code: 1}}));
    eq(err.message, '{"code":1}', 'rpc error fallback');
    err = await failure(async () => { throw new TypeError('offline'); });
    assert(err.message === 'Network error: offline' && err.retryable === true, 'network error');
    const made = apiError('m', false);
    assert(made instanceof Error && made.retryable === false && made.message === 'm', 'apiError');

    // loadDatabases
    const sel = $('select-database');
    const options = () => [...sel.options].map((o) => o.value);
    state.database = '';
    stubFetch(async (url) => url.endsWith('/driver/app/dbs') ? resp({result: {databases: ['a', 'b']}}) : resp({}, 404));
    await loadDatabases(location.origin);
    eq(options(), ['', 'a', 'b'], 'choose prompt first');
    assert(sel.options[0].disabled && sel.value === '' && !sel.disabled, 'prompt selected, select enabled');
    eq(calls[0].url, '/driver/app/dbs', 'same origin url is relative');
    state.database = 'b';
    await loadDatabases('https://other.example/');
    eq(calls[calls.length - 1].url, 'https://other.example/driver/app/dbs', 'explicit server');
    eq([options(), sel.value], [['a', 'b'], 'b'], 'current database preselected');
    stubFetch(async () => resp({result: ['only']}));
    state.database = '';
    await loadDatabases(location.origin);
    eq([sel.value, state.database], ['only', 'only'], 'single database is chosen');
    stubFetch(async (url) => url.endsWith('/driver/app/dbs') ? resp({result: []}) : resp({result: ['z', 'y']}));
    state.database = '';
    await loadDatabases(location.origin);
    eq(options(), ['', 'z', 'y'], 'fallback list');
    assert(calls.some((c) => c.url === '/web/database/list'), 'fallback endpoint used');
    stubFetch(async () => { throw new Error('down'); });
    await loadDatabases(location.origin);
    assert(sel.textContent.includes('No databases found') && !sel.disabled, 'no database found');
    stubFetch(async () => resp({result: []}, 200));
    await loadDatabases();
    assert(sel.textContent.includes('No databases found'), 'default url, no database');
"""

JS_UI_AND_MODALS = r"""
    await reset();
    // toast & screens
    showToast('Hello', 'success', 60);
    assert($('toast').textContent === 'Hello' && $('toast').className === 'toast success', 'toast shown');
    showToast('Default');
    assert($('toast').className === 'toast info', 'default toast type');
    showToast('Gone', 'info', 40);
    await sleep(150);
    assert(isHidden('toast'), 'toast hides itself');
    showScreen('screen-home');
    assert(!isHidden('screen-home') && isHidden('screen-setup') && isHidden('screen-stop'), 'home screen');
    showScreen('screen-setup');
    assert(!isHidden('screen-setup') && isHidden('screen-home'), 'setup screen');

    // geolocation: a first fix
    resetGeo(); setGeo(1.5, 2.5);
    eq(await getPosition(), {latitude: 1.5, longitude: 2.5}, 'position');
    eq(geo.waiters.length, 0, 'waiter answered');
    // a recent fix is used at once, without asking the phone again
    let asked = 0;
    geoStub(() => { asked++; });
    eq(await getPosition(), {latitude: 1.5, longitude: 2.5}, 'recent fix reused');
    eq(asked, 0, 'no new request for a recent fix');
    // an old fix is not used: the tap waits LOCATION.waitMs for a new one, then goes without
    geo.fix.at = Date.now() - LOCATION.maxAgeMs - 1;
    LOCATION.waitMs = 50;
    let t0 = Date.now();
    eq(await getPosition(), {latitude: null, longitude: null}, 'no fix in time');
    assert(Date.now() - t0 < 1000 && asked === 1, 'waited only LOCATION.waitMs');
    eq(geo.waiters.length, 0, 'waiter removed after the wait');
    // a fix from the running watch answers a waiting tap
    resetGeo();
    let watchOk = null;
    geoStub(() => {}, (ok) => { watchOk = ok; return 7; });
    const pending = getPosition();
    eq(geo.watchId, 7, 'tracking started by a tap');
    watchOk({coords: {latitude: 8.5, longitude: 9.5}, timestamp: Date.now()});
    eq(await pending, {latitude: 8.5, longitude: 9.5}, 'fix from the watch');
    // permission refused: no position, and the driver is told
    resetGeo();
    geoStub((ok, ko) => ko({code: 1}));
    eq(await getPosition(), {latitude: null, longitude: null}, 'position refused');
    assert(geo.problem === 'denied' && !isHidden('location-banner'), 'refused banner');
    assert($('location-banner-text').textContent.startsWith('Location is off for this app'), 'refused text');
    assert(!$('location-banner').classList.contains('clickable'), 'no settings link outside the Android app');
    onLocationFix({coords: {latitude: 1, longitude: 2}});
    assert(geo.problem === '' && isHidden('location-banner'), 'a fix clears the banner');
    // no signal or a slow fix is not reported as refused, and keeps the tap waiting
    resetGeo();
    onLocationError({code: 3});
    onLocationError({code: 2});
    assert(geo.problem === '' && isHidden('location-banner'), 'timeouts not reported');
    // plain http server: geolocation is blocked by the browser
    resetGeo();
    asked = 0;
    geoStub(() => { asked++; });
    Object.defineProperty(window, 'isSecureContext', {value: false, configurable: true});
    eq(await getPosition(), {latitude: null, longitude: null}, 'insecure page');
    assert(asked === 0 && geo.problem === 'insecure' && !isHidden('location-banner'), 'insecure banner');
    assert($('location-banner-text').textContent.includes('https'), 'insecure text');
    delete window.isSecureContext;
    // no geolocation at all
    resetGeo();
    Object.defineProperty(navigator, 'geolocation', {value: undefined, configurable: true});
    eq(await getPosition(), {latitude: null, longitude: null}, 'no geolocation');
    assert(geo.problem === 'unsupported' && !isHidden('location-banner'), 'unsupported banner');
    showScreen('screen-home');
    eq(geo.watchId, null, 'no tracking without geolocation');
    // tracking follows the route screens and the page's visibility
    showScreen('screen-setup');
    resetGeo();
    let cleared = 0;
    geoStub(() => {}, () => 5, () => { cleared++; });
    showScreen('screen-home');
    eq(geo.watchId, 5, 'tracking on the stop list');
    showScreen('screen-stop');
    eq(geo.watchId, 5, 'still tracking on a stop');
    showScreen('screen-setup');
    assert(geo.watchId === null && cleared === 1, 'stopped on the sign-in screen');
    showScreen('screen-home');
    Object.defineProperty(document, 'visibilityState', {get: () => 'hidden', configurable: true});
    document.dispatchEvent(new Event('visibilitychange'));
    assert(geo.watchId === null && cleared === 2, 'stopped while the app is hidden');
    delete document.visibilityState;
    document.dispatchEvent(new Event('visibilitychange'));
    eq(geo.watchId, 5, 'resumed when visible again');
    resetGeo(); setGeo(0, 0);

    // stop list
    state.stops = [];
    await renderStopList();
    assert($('stop-count').textContent === '0 stops' && !isHidden('empty-state') && $('stop-list').innerHTML === '', 'empty list');
    await queuePut(entry({orderId: 7}));
    state.stops = [mkStop(), mkStop({order_id: 8, name: '', customer: '', address: '', scheduled_start: null,
                                      last_status: 'completed'}),
                   mkStop({order_id: 9, last_status: 'flagged'})];
    await renderStopList();
    const cards = [...document.querySelectorAll('#stop-list .stop-card')];
    assert(cards.length === 3 && $('stop-count').textContent === '3 stops' && isHidden('empty-state'), 'three stops');
    assert(cards[0].textContent.includes('1 update pending sync'), 'pending badge');
    assert(cards[1].textContent.includes('Order #8') && cards[1].textContent.includes('Unscheduled'), 'fallbacks');
    assert(cards[1].classList.contains('status-completed') && cards[2].classList.contains('status-flagged'), 'status classes');
    state.stops = [mkStop()];
    await renderStopList();
    eq($('stop-count').textContent, '1 stop', 'singular');
    document.querySelector('#stop-list .stop-card').click();
    await waitFor(() => !isHidden('screen-stop'), 'stop detail opened by click');
    eq(state.currentStop.order_id, 7, 'current stop');

    // stop detail & history
    await clearQueue();
    await openStopDetail(mkStop({last_status: 'completed', state: 'completed', last_status_time: '2026-01-02 11:00:00'}));
    assert($('stop-header-title').textContent === 'O7' && $('stop-detail-customer').textContent === 'Cust', 'details');
    assert($('stop-detail-time').textContent.startsWith('Scheduled:'), 'schedule');
    assert($('current-status-badge').style.color === 'var(--success)', 'completed colour');
    assert($('log-history').textContent.includes('Last recorded'), 'last recorded');
    await openStopDetail(mkStop({last_status: 'flagged', name: '', customer: '', address: '', scheduled_start: null}));
    assert($('current-status-badge').style.color === 'var(--danger)' && $('stop-header-title').textContent === 'Stop #7', 'flagged colour');
    assert($('stop-detail-customer').textContent === '—' && $('stop-detail-time').textContent === '', 'detail fallbacks');
    await queuePut(entry({orderId: 7, status: 'arrived', note: 'at the gate'}));
    await openStopDetail(mkStop());
    assert($('current-status-badge').textContent === 'Not started', 'not started');
    assert($('log-history').textContent.includes('Pending sync') && $('log-history').textContent.includes('at the gate'), 'pending history');
    await clearQueue();
    await renderLogHistory(mkStop());
    assert($('log-history').textContent.includes('No status events recorded yet.'), 'no events');

    // modals
    $('flag-note').value = 'old';
    state.pendingPhoto = 'x';
    openFlagModal();
    assert(!isHidden('modal-flag') && $('flag-note').value === '' && state.pendingPhoto === null, 'flag modal open');
    closeFlagModal();
    assert(isHidden('modal-flag'), 'flag modal closed');
    openPhotoModal('arrived');
    assert(!isHidden('modal-photo') && state.pendingStatus === 'arrived', 'photo modal open');
    assert($('photo-modal-title').textContent.includes('Arrived'), 'photo modal title');
    closePhotoModal();
    assert(isHidden('modal-photo') && state.pendingStatus === null, 'photo modal closed');
    state.currentStop = mkStop({lines: []});
    openWeighedModal();
    assert(!isHidden('modal-weighed') && $('weighed-empty-hint'), 'empty weigh modal');
    eq($('weighed-category-select').options.length, 3, 'categories offered');
    state.currentStop = mkStop({allowed_categories: []});
    openWeighedModal();
    assert($('weighed-category-select').textContent.includes('No Waste Categories'), 'no categories');
    assert($('input-weight-cat-1'), 'existing line prefilled');
    closeWeighedModal();
    assert(isHidden('modal-weighed'), 'weigh modal closed');

    // photo reading
    const file = new File(['hello'], 'a.txt', {type: 'text/plain'});
    eq(await readFileAsBase64(file), 'aGVsbG8=', 'base64 without the data prefix');
    const input = $('status-photo-input');
    const dt = new DataTransfer(); dt.items.add(file); input.files = dt.files;
    fire(input, 'change');
    await waitFor(() => state.pendingPhoto === 'aGVsbG8=', 'photo read');
    assert(!isHidden('status-photo-preview') && $('status-photo-preview').querySelector('img'), 'preview shown');
    state.pendingPhoto = null;
    input.files = new DataTransfer().files;
    fire(input, 'change');
    await sleep(60);
    assert(state.pendingPhoto === null, 'no file, nothing read');

    // the flag and weighed modals wire the same photo reader
    for (const [inputId, previewId] of [['flag-photo-input', 'flag-photo-preview'],
                                        ['weighed-photo-input', 'weighed-photo-preview']]) {
        const photoInput = $(inputId);
        const photoTransfer = new DataTransfer(); photoTransfer.items.add(file); photoInput.files = photoTransfer.files;
        state.pendingPhoto = null;
        fire(photoInput, 'change');
        await waitFor(() => state.pendingPhoto === 'aGVsbG8=', inputId + ' photo read');
        const photoPreview = $(previewId);
        assert(!photoPreview.classList.contains('hidden') && photoPreview.querySelector('img'), previewId + ' shown');
        assert(photoPreview.querySelector('img').src === 'data:text/plain;base64,aGVsbG8=', previewId + ' image source');
        photoInput.files = new DataTransfer().files;
        state.pendingPhoto = null;
        fire(photoInput, 'change');
        await sleep(60);
        assert(state.pendingPhoto === null, inputId + ': no file, nothing read');
    }

    // weigh modal: add and remove categories
    state.currentStop = mkStop();
    openWeighedModal();
    const select = $('weighed-category-select');
    select.value = '2'; fire(select, 'change');
    assert($('weighed-item-cat-2') && select.value === '', 'category added');
    select.value = '1'; fire(select, 'change');
    assert($('weighed-item-cat-1').style.borderColor !== '', 'existing category highlighted');
    select.value = ''; fire(select, 'change');
    eq(document.querySelectorAll('#weighed-lines-list .weighed-line-item').length, 2, 'blank choice ignored');
    document.querySelector('#weighed-item-cat-2 .btn-delete-line').click();
    assert(!$('weighed-item-cat-2'), 'category removed');
    $('weighed-lines-list').click();
    document.querySelector('#weighed-item-cat-1 .btn-delete-line').click();
    assert($('weighed-empty-hint'), 'hint shown again');
    closeWeighedModal();
"""

JS_SUBMIT_AND_SYNC = r"""
    await reset();
    setGeo(3.5, 4.5);
    const routeCalls = () => calls.filter((c) => c.url.includes('/driver/api/route/today')).length;
    const handler = (result) => async (url) => url.includes('/route/today') ? resp({result: {stops: []}}) : resp({result});
    state.stops = [mkStop()];
    state.currentStop = state.stops[0];

    // online success
    stubFetch(handler({log_id: 11}));
    await submitStatus(7, 'arrived', 'note', 'PHOTO');
    const body = calls[0].body.params;
    eq([body.status, body.note, body.photo, body.latitude, body.longitude], ['arrived', 'note', 'PHOTO', 3.5, 4.5], 'request');
    assert(body.client_uuid && body.timestamp, 'uuid and timestamp sent');
    eq((await queueGetAll()).length, 0, 'queue emptied after the send');
    eq([state.stops[0].last_status, state.currentStop.last_status], ['arrived', 'arrived'], 'optimistic status');
    assert($('toast').textContent.includes('logged'), 'toast');

    // without a position the update is sent at once with null coordinates
    resetGeo();
    LOCATION.waitMs = 50;
    geoStub(() => {});
    calls.length = 0;
    await submitStatus(7, 'started');
    eq([calls[0].body.params.latitude, calls[0].body.params.longitude], [null, null], 'no position sent as null');
    resetGeo(); setGeo(3.5, 4.5);

    // weights update the lines optimistically
    await submitStatus(7, 'weighed', '', null, [{category_id: 1, weight: 3}, {category_id: 9, weight: 1}], [2]);
    eq(state.currentStop.lines.map((l) => [l.category_id, l.category_name, l.weight]),
       [[1, 'Alpha', 3], [9, 'Category #9', 1]], 'lines updated');
    eq(calls[calls.length - 1].body.params.removed_category_ids, [2], 'removed categories sent');

    // the order state follows the status
    await submitStatus(7, 'started', '', null);
    eq(state.currentStop.state, 'in_progress', 'started');
    await submitStatus(7, 'completed', '', null);
    eq(state.currentStop.state, 'completed', 'completed');

    // outcomes of the send
    stubFetch(handler({duplicate: true}));
    await submitStatus(7, 'lifted', '', null);
    eq((await queueGetAll()).length, 0, 'duplicate removed');
    stubFetch(handler({error: 'invalid', message: 'Nope'}));
    await submitStatus(7, 'lifted', '', null);
    assert($('toast').textContent === 'Nope' && (await queueGetAll()).length === 0, 'rejected removed');
    assert(routeCalls() >= 1, 'route reloaded after a rejection');
    stubFetch(async () => { throw new TypeError('lost'); });
    await submitStatus(7, 'lifted', '', null);
    eq((await queueGetAll()).length, 1, 'network failure keeps the update');
    assert($('toast').textContent.includes('Connection problem'), 'connection toast');
    await clearQueue();
    stubFetch(async (url) => url.includes('/route/today') ? resp({result: {stops: []}}) : resp({error: {message: 'Server said no'}}));
    await submitStatus(7, 'lifted', '', null);
    assert((await queueGetAll()).length === 0 && $('toast').textContent === 'Server said no', 'server error removes the update');
    setOnline(false);
    stubFetch(handler({log_id: 1}));
    await submitStatus(7, 'lifted', '', null);
    eq([calls.length, (await queueGetAll()).length], [0, 1], 'offline: queued, nothing sent');
    assert($('toast').textContent.includes('Offline'), 'offline toast');
    await syncQueue();
    eq(calls.length, 0, 'sync does nothing while offline');
    setOnline(true);
    await clearQueue();

    // syncQueue
    await syncQueue();
    eq(calls.length, 0, 'empty queue');
    await queuePut(entry({orderId: 1, createdAt: 1})); await queuePut(entry({orderId: 2, createdAt: 2}));
    let n = 0;
    stubFetch(async () => resp({result: ++n === 1 ? {log_id: 1} : {duplicate: true}}));
    await syncQueue();
    assert((await queueGetAll()).length === 0 && $('toast').textContent.includes('Synced 2 offline updates'), 'both synced');
    await queuePut(entry({orderId: 1, createdAt: 1}));
    stubFetch(async (url) => url.includes('/route/today') ? resp({result: {stops: []}}) : resp({result: {error: 'bad', message: 'Bad move'}}));
    await syncQueue();
    let left = await queueGetAll();
    assert(left.length === 1 && left[0].rejectedReason === 'Bad move', 'flagged as rejected');
    assert($('toast').textContent.includes('was rejected: Bad move'), 'rejected toast');
    await clearQueue();
    await queuePut(entry({orderId: 1, createdAt: 1})); await queuePut(entry({orderId: 2, createdAt: 2}));
    stubFetch(async () => { throw new TypeError('offline'); });
    await syncQueue();
    eq([calls.length, (await queueGetAll()).length], [1, 2], 'retryable error stops the sync');
    await clearQueue();
    await queuePut(entry({orderId: 1, createdAt: 1})); await queuePut(entry({orderId: 2, createdAt: 2}));
    let m = 0;
    stubFetch(async (url) => {
        if (url.includes('/route/today')) { return resp({result: {stops: []}}); }
        return ++m === 1 ? resp({error: {message: 'Rejected for good'}}) : resp({result: {log_id: 5}});
    });
    await syncQueue();
    left = await queueGetAll();
    assert(left.length === 1 && left[0].rejectedReason === 'Rejected for good', 'permanent error flagged, others still sent');
    assert($('toast').textContent.includes('was rejected'), 'rejection reported');

    // fetchTodayRoute
    stubFetch(async () => resp({result: {stops: [mkStop(), mkStop({order_id: 8})]}}));
    await fetchTodayRoute();
    assert(state.stops.length === 2 && document.querySelectorAll('#stop-list .stop-card').length === 2, 'route loaded');
    assert(!$('btn-refresh').classList.contains('loading'), 'loading state removed');
    stubFetch(async () => resp({result: {}}));
    await fetchTodayRoute();
    eq(state.stops, [], 'missing stops');
    stubFetch(async () => resp({}, 500));
    const realConsoleError = console.error;
    console.error = () => {};
    await fetchTodayRoute();
    console.error = realConsoleError;
    assert($('toast').textContent.includes('Failed to load route') && !$('btn-refresh').classList.contains('loading'), 'route failure');

    // saved route: kept on the device for an offline restart
    stubFetch(async () => resp({result: {stops: [mkStop()]}}));
    await fetchTodayRoute();
    eq(loadStops().map((s) => s.order_id), [7], 'route saved on load');
    state.currentStop = state.stops[0];
    stubFetch(async () => { throw new Error('offline'); });
    const realConsoleWarn = console.warn;
    console.error = () => {}; console.warn = () => {};
    await submitStatus(7, 'arrived');
    eq(loadStops()[0].last_status, 'arrived', 'status change saved with the route');
    state.stops = [];
    state.stops = loadStops();
    await fetchTodayRoute();
    console.error = realConsoleError; console.warn = realConsoleWarn;
    assert(state.stops.length === 1 && $('toast').textContent.includes('showing the saved route'), 'saved route kept when the server is down');
    localStorage.setItem('wm_stops', JSON.stringify({date: '2000-1-1', stops: [mkStop()]}));
    eq(loadStops(), [], 'another day\'s route is ignored');
    localStorage.setItem('wm_stops', '{broken');
    eq(loadStops(), [], 'unreadable route ignored');
    saveStops();
    clearCredentials();
    assert(localStorage.getItem('wm_stops') === null, 'route removed on sign out');
    await clearQueue();
"""

JS_SYNC_LOCK_AND_REJECTED = r"""
    await reset();
    state.stops = [mkStop()];
    state.currentStop = state.stops[0];

    // Overlapping syncs send each update once: no second copy that the server
    // would refuse and the app would keep as a phantom rejected update
    await queuePut(entry({orderId: 7, createdAt: 1}));
    await queuePut(entry({orderId: 7, status: 'started', createdAt: 2}));
    const seen = {};
    stubFetch(async (url, o, body) => {
        if (url.includes('/route/today')) { return resp({result: {stops: [mkStop()]}}); }
        const uuid = body.params.client_uuid;
        seen[uuid] = (seen[uuid] || 0) + 1;
        await sleep(50);
        return resp({result: seen[uuid] === 1 ? {log_id: 1} : {error: 'duplicate_client_uuid', message: 'dup'}});
    });
    await Promise.all([syncQueue(), syncQueue(), syncQueue()]);
    eq(Object.values(seen), [1, 1], 'each update sent once');
    eq((await queueGetAll()).length, 0, 'nothing left and nothing flagged');

    // A tap during a sync is sent once, after the older update
    const sent = [];
    stubFetch(async (url, o, body) => {
        if (url.includes('/route/today')) { return resp({result: {stops: [mkStop()]}}); }
        sent.push(body.params.status);
        await sleep(30);
        return resp({result: {log_id: 1}});
    });
    await queuePut(entry({orderId: 7, status: 'en_route', createdAt: 1}));
    await Promise.all([syncQueue(), submitStatus(7, 'arrived', '', null)]);
    eq(sent, ['en_route', 'arrived'], 'sent once each, in order');
    eq((await queueGetAll()).length, 0, 'queue drained');

    // A tap online while older updates still wait sends them first
    setOnline(false);
    await submitStatus(7, 'en_route', '', null);
    setOnline(true);
    sent.length = 0;
    await submitStatus(7, 'arrived', '', null);
    eq(sent, ['en_route', 'arrived'], 'older queued update sent first');
    eq((await queueGetAll()).length, 0, 'both sent');

    // Flagging an update that is no longer queued does not bring it back
    const gone = entry({orderId: 7});
    await queuePut(gone);
    await queueDelete(gone.clientUuid);
    eq(await queueMarkRejected(gone.clientUuid, 'late'), false, 'deleted entry not flagged');
    eq((await queueGetAll()).length, 0, 'deleted entry stays deleted');

    // Rejected updates are shown as rejected (not pending) and can be discarded
    await queuePut(entry({orderId: 7, status: 'lifted', rejectedReason: 'Bad <b>move</b>', createdAt: 5}));
    await queuePut(entry({orderId: 7, status: 'weighed', createdAt: 6}));
    eq([await queueCountForOrder(7), await queueRejectedCountForOrder(7)], [1, 1], 'pending and rejected counted apart');
    state.stops = [mkStop()];
    await renderStopList();
    const card = document.querySelector('#stop-list .stop-card');
    assert(card.textContent.includes('1 update pending sync') && card.textContent.includes('1 update rejected'), 'card badges');
    await openStopDetail(mkStop());
    const hist = $('log-history');
    assert(hist.textContent.includes('Not accepted by the server: Bad <b>move</b>') && !hist.querySelector('b'), 'reason shown, escaped');
    assert(hist.textContent.includes('Pending sync'), 'pending update still listed');
    const realConfirm = window.confirm;
    window.confirm = () => false;
    hist.querySelector('.btn-discard-rejected').click();
    await sleep(100);
    eq(await queueRejectedCountForOrder(7), 1, 'kept when the driver cancels');
    window.confirm = () => true;
    $('log-history').querySelector('.btn-discard-rejected').click();
    for (let i = 0; i < 40 && await queueRejectedCountForOrder(7); i++) { await sleep(25); }
    window.confirm = realConfirm;
    eq([await queueRejectedCountForOrder(7), await queueCountForOrder(7)], [0, 1], 'discarded, pending kept');
    await waitFor(() => !$('log-history').querySelector('.btn-discard-rejected'), 'history refreshed');
"""

JS_SCREEN_HANDLERS = r"""
    await reset();
    const route = (stops) => async (url) => url.includes('/route/today') ? resp({result: {stops}}) : resp({result: {log_id: 1}});
    const sent = () => calls.filter((c) => c.url.includes('/status')).map((c) => c.body.params);
    const click = (id) => $(id).click();

    // setup screen
    showScreen('screen-setup');
    $('input-server-url').value = ''; $('input-api-key').value = '';
    click('btn-save-key');
    await waitFor(() => $('setup-error').textContent.includes('required'), 'required message');
    $('input-server-url').value = location.origin; $('input-api-key').value = 'abc';
    $('select-database').innerHTML = '<option value="" selected>none</option>';
    click('btn-save-key');
    await waitFor(() => $('setup-error').textContent.includes('select a database'), 'database message');
    $('select-database').innerHTML = '<option value="dbx" selected>dbx</option>';
    for (const [handler, expected] of [
        [async () => resp({}, 401), 'API key is not valid for database "dbx"'],
        [async () => { throw new TypeError('Failed to fetch'); }, 'Unable to reach the server'],
        [async () => resp({}, 404), 'Connection failed: HTTP 404'],
    ]) {
        stubFetch(handler);
        click('btn-save-key');
        await waitFor(() => $('setup-error').textContent.includes(expected), expected);
    }
    stubFetch(route([mkStop()]));
    click('btn-save-key');
    await waitFor(() => !isHidden('screen-home') && state.stops.length === 1, 'signed in');
    eq(loadCredentials().database, 'dbx', 'credentials saved');
    assert(isHidden('setup-error'), 'error cleared');
    eq(calls[0].opts.headers['X-Odoo-Database'], 'dbx', 'database header');

    // setup inputs
    stubFetch(async () => resp({result: {databases: ['one', 'two']}}));
    fire($('input-server-url'), 'blur');
    await waitFor(() => calls.some((c) => c.url.endsWith('/driver/app/dbs')), 'blur reloads databases');
    const before = calls.length;
    fire($('input-server-url'), 'change');
    await waitFor(() => calls.length > before, 'change reloads databases');
    await waitFor(() => !$('select-database').disabled, 'databases loaded');
    $('select-database').value = 'two'; fire($('select-database'), 'change');
    eq(state.database, 'two', 'database chosen');

    // home screen
    state.database = 'dbx';
    stubFetch(route([mkStop(), mkStop({order_id: 8})]));
    click('btn-refresh');
    await waitFor(() => state.stops.length === 2, 'refresh');
    document.querySelector('#stop-list .stop-card').click();
    await waitFor(() => !isHidden('screen-stop'), 'detail');
    click('btn-back');
    await waitFor(() => !isHidden('screen-home'), 'back to the list');

    // status buttons
    const status = (s) => document.querySelector('#status-grid .status-btn[data-status="' + s + '"]');
    state.currentStop = null;
    status('arrived').click();
    assert(isHidden('modal-photo'), 'no stop: nothing happens');
    state.currentStop = mkStop();
    updateStatusButtons(state.currentStop);
    status('arrived').click();
    assert(!isHidden('modal-photo') && state.pendingStatus === 'arrived', 'photo modal');
    closePhotoModal();
    status('flagged').click();
    assert(!isHidden('modal-flag'), 'flag modal');
    closeFlagModal();
    status('weighed').click();
    assert(isHidden('modal-weighed'), 'weigh not allowed yet');
    state.currentStop = mkStop({last_status: 'started'});
    updateStatusButtons(state.currentStop);
    status('weighed').click();
    assert(!isHidden('modal-weighed'), 'weigh modal');
    closeWeighedModal();
    state.currentStop = mkStop({last_status: 'completed'});
    const forced = status('arrived');
    forced.disabled = false; forced.classList.remove('disabled');
    forced.click();
    assert($('toast').textContent.includes('Cannot change status'), 'transition refused');

    // flag modal
    state.currentStop = mkStop();
    state.missedReasons = [{reason_id: 4, reason_name: 'Access Issue'}];
    stubFetch(route([]));
    openFlagModal();
    assert($('flag-reason').options.length === 2, 'reasons offered');
    click('btn-flag-confirm');
    assert($('toast').textContent.includes('Choose a reason') && !isHidden('modal-flag'), 'reason required');
    $('flag-reason').value = '4';
    click('btn-flag-confirm');
    assert($('toast').textContent.includes('Describe the issue') && !isHidden('modal-flag'), 'note required');
    $('flag-note').value = ' blocked road ';
    state.pendingPhoto = 'FLAGPHOTO';
    click('btn-flag-confirm');
    await waitFor(() => sent().length === 1, 'flag sent');
    eq([sent()[0].status, sent()[0].note, sent()[0].photo, sent()[0].missed_reason_id],
       ['flagged', 'blocked road', 'FLAGPHOTO', 4], 'flag request');
    assert(isHidden('modal-flag'), 'flag modal closed');
    openFlagModal(); click('btn-flag-cancel');
    assert(isHidden('modal-flag'), 'cancel');
    openFlagModal(); $('modal-flag').click();
    assert(isHidden('modal-flag'), 'overlay click closes');
    openFlagModal(); $('flag-note').click();
    assert(!isHidden('modal-flag'), 'click inside keeps it open');
    assert($('flag-reason').value === '', 'reason cleared on reopen');
    closeFlagModal();

    // photo modal
    stubFetch(route([]));
    state.currentStop = mkStop();
    openPhotoModal('arrived'); state.pendingPhoto = 'PIC'; click('btn-photo-cancel');
    assert(isHidden('modal-photo'), 'cancel closes');
    assert(state.pendingStatus === null && state.pendingPhoto === null, 'cancel clears');
    await sleep(80);
    eq(sent().length, 0, 'cancel sends nothing');
    openPhotoModal('arrived'); click('btn-photo-confirm');
    await waitFor(() => sent().length === 1, 'submit without photo sent');
    eq([sent()[0].status, sent()[0].photo], ['arrived', null], 'no photo');
    openPhotoModal('arrived'); state.pendingPhoto = 'PIC'; click('btn-photo-confirm');
    await waitFor(() => sent().length === 2, 'photo sent');
    eq(sent()[1].photo, 'PIC', 'photo sent');
    openPhotoModal('started'); $('modal-photo').click();
    assert(isHidden('modal-photo'), 'photo overlay closes');
    state.currentStop = null;
    openPhotoModal('arrived'); click('btn-photo-confirm');
    await sleep(80);
    eq(sent().length, 2, 'nothing sent without a stop');

    // weigh modal
    stubFetch(route([]));
    state.currentStop = mkStop({lines: [
        {line_id: 1, category_id: 1, category_name: 'Alpha', estimated_weight: 5, weight: 0},
        {line_id: 2, category_id: 2, category_name: 'Beta', estimated_weight: 5, weight: 0}]});
    openWeighedModal();
    click('btn-weighed-confirm');
    assert($('toast').textContent.includes('at least one'), 'weight required');
    $('input-weight-cat-1').value = '4.5';
    document.querySelector('#weighed-item-cat-2 .btn-delete-line').click();
    state.pendingPhoto = 'W';
    click('btn-weighed-confirm');
    await waitFor(() => sent().length === 1, 'weigh sent');
    eq([sent()[0].status, sent()[0].line_weights, sent()[0].removed_category_ids, sent()[0].photo],
       ['weighed', [{category_id: 1, weight: 4.5}], [2], 'W'], 'weigh request');
    openWeighedModal(); click('btn-weighed-cancel');
    assert(isHidden('modal-weighed'), 'weigh cancel');
    openWeighedModal(); $('modal-weighed').click();
    assert(isHidden('modal-weighed'), 'weigh overlay');

    // connectivity events
    setOnline(false);
    window.dispatchEvent(new Event('offline'));
    assert(!isHidden('offline-banner'), 'offline banner');
    await waitFor(() => $('sync-indicator').className === 'sync-dot offline', 'offline indicator');
    setOnline(true);
    stubFetch(route([]));
    await queuePut(entry({orderId: 7}));
    window.dispatchEvent(new Event('online'));
    assert(isHidden('offline-banner'), 'banner hidden');
    await waitFor(() => sent().length === 1, 'queue sent when back online');

    // sign out
    await clearQueue();
    state.serverUrl = 'http://srv'; state.apiKey = 'K'; state.database = 'dbx'; state.stops = [mkStop()];
    saveCredentials('http://srv', 'K', 'dbx');
    stubFetch(async () => resp({result: {databases: ['dbx']}}));
    click('btn-logout');
    await waitFor(() => !isHidden('screen-setup'), 'signed out');
    eq([loadCredentials().apiKey, state.apiKey, state.stops], ['', '', []], 'credentials cleared');
    eq($('input-server-url').value, location.origin, 'server url reset');
    // unsent updates: the driver is asked first
    saveCredentials('http://srv', 'K', 'dbx');
    await queuePut(entry({orderId: 1}));
    stubFetch(async () => { throw new TypeError('offline'); });
    const realConfirm = window.confirm;
    let asked = 0;
    window.confirm = () => { asked++; return false; };
    click('btn-logout');
    await waitFor(() => asked === 1, 'confirmation asked');
    await sleep(80);
    assert(loadCredentials().apiKey === 'K' && (await queueGetAll()).length === 1, 'stay signed in when declined');
    window.confirm = () => true;
    click('btn-logout');
    await waitFor(() => loadCredentials().apiKey === '', 'signed out after confirming');
    eq((await queueGetAll()).length, 0, 'unsent updates dropped');
    window.confirm = realConfirm;
"""

JS_SERVICE_WORKER = r"""
    await reset();
    const source = await (await realFetch('/driver/app/sw.js')).text();
    // the current cache name, so bumping it in sw.js doesn't break this test
    const cacheName = source.match(/const CACHE_NAME = '([^']+)'/)[1];
    const handlers = {};
    const store = new Map();
    const added = [];
    const deleted = [];
    let claimed = false, skipped = false, failAddAll = false;
    const fakeCaches = {
        open: async () => ({
            addAll: async (urls) => { if (failAddAll) { throw new Error('offline'); } added.push(...urls); },
            put: async (req, res) => { store.set(req.url, res); },
        }),
        keys: async () => ['old-cache', cacheName],
        delete: async (k) => { deleted.push(k); return true; },
        match: async (req) => store.get(req.url) || 'cache-miss',
    };
    const client = {messages: [], postMessage(m) { this.messages.push(m); }};
    const fakeSelf = {
        addEventListener: (type, fn) => { handlers[type] = fn; },
        skipWaiting: () => { skipped = true; },
        clients: {claim: async () => { claimed = true; }, matchAll: async () => [client]},
    };
    let networkImpl = async () => resp({});
    new Function('self', 'caches', 'fetch', 'URL', source)(fakeSelf, fakeCaches, (...a) => networkImpl(...a), URL);
    eq(Object.keys(handlers).sort(), ['activate', 'fetch', 'install', 'sync'], 'listeners registered');
    const run = async (type, event) => {
        const pending = [];
        handlers[type]({...event, waitUntil: (p) => pending.push(p)});
        await Promise.all(pending);
    };

    await run('install', {});
    assert(skipped && added.length === 3 && added.includes('/driver/app'), 'shell cached on install');
    failAddAll = true;
    await run('install', {});
    failAddAll = false;
    await run('activate', {});
    eq(deleted, ['old-cache'], 'old caches removed');
    assert(claimed, 'clients claimed');

    // fetch strategy: network first, cache when offline
    const fetchEvent = (path, method = 'GET') => {
        const ev = {request: {url: location.origin + path, method}, response: undefined};
        ev.respondWith = (p) => { ev.response = p; };
        return ev;
    };
    let ev = fetchEvent('/driver/api/route/today', 'POST');
    handlers.fetch(ev);
    assert(ev.response === undefined, 'API calls pass through');
    ev = fetchEvent('/driver/app/other', 'POST');
    handlers.fetch(ev);
    assert(ev.response === undefined, 'other methods pass through');
    const okResponse = {ok: true, clone: () => 'cloned'};
    networkImpl = async () => okResponse;
    ev = fetchEvent('/driver/app/page');
    handlers.fetch(ev);
    assert((await ev.response) === okResponse, 'network response served');
    await sleep(20);
    eq(store.get(location.origin + '/driver/app/page'), 'cloned', 'successful responses cached');
    networkImpl = async () => ({ok: false, clone: () => { throw new Error('must not clone'); }});
    ev = fetchEvent('/driver/app/broken');
    handlers.fetch(ev);
    assert((await ev.response).ok === false, 'error responses served, not cached');
    networkImpl = async () => { throw new TypeError('offline'); };
    ev = fetchEvent('/driver/app/page');
    handlers.fetch(ev);
    eq(await ev.response, 'cloned', 'cache used when offline');
    ev = fetchEvent('/driver/app/never-seen');
    handlers.fetch(ev);
    eq(await ev.response, 'cache-miss', 'cache miss when offline');

    // background sync
    await run('sync', {tag: 'wm-sync-queue'});
    eq(client.messages, [{type: 'SYNC_QUEUE'}], 'clients asked to sync');
    await run('sync', {tag: 'other'});
    eq(client.messages.length, 1, 'other tags ignored');

    // the page reacts to the worker's message
    if (navigator.serviceWorker) {
        await queuePut(entry({orderId: 7}));
        stubFetch(async (url) => url.includes('/route/today') ? resp({result: {stops: []}}) : resp({result: {log_id: 3}}));
        let registered = false;
        for (let i = 0; i < 80 && !registered; i++) {
            registered = !!(await navigator.serviceWorker.getRegistration('/driver/app'));
            if (!registered) { await sleep(50); }
        }
        if (registered) {
            await sleep(100);
            navigator.serviceWorker.dispatchEvent(new MessageEvent('message', {data: {type: 'SYNC_QUEUE'}}));
            navigator.serviceWorker.dispatchEvent(new MessageEvent('message', {data: {type: 'OTHER'}}));
            await waitFor(() => calls.some((c) => c.url.includes('/status')), 'sync triggered by the worker message');
        } else {
            console.warn('service worker registration unavailable in this browser');
        }
    }
"""


@tagged('post_install', '-at_install', 'wm_driver_app')
class TestDriverAppJs(HttpCase):
    """
    Exercises every function of the driver PWA (static/src/js/app.js) and of
    its service worker (sw.js) in headless Chrome: pure helpers, storage and
    offline queue, API client, rendering, modals, status submission and sync,
    and the handlers wired by init().
    """

    def setUp(self):
        super().setUp()
        self.driver = new_test_user(self.env, login='wm_js_driver', groups='wm_base.group_wm_driver')
        customer = self.env['res.partner'].create({'name': 'Driver JS Customer'})
        point = self.env['wm.collection.point'].create({'name': 'Driver JS Point', 'partner_id': customer.id})
        category = self.env['wm.waste.category'].create({'name': 'Driver JS Category', 'code': 'DRVJS'})
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Driver JS Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Driver JS Truck', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'DRV-JS-1', 'driver_id': self.driver.partner_id.id,
        })
        route = self.env['wm.route'].create({
            'date': fields.Date.context_today(self.driver),
            'vehicle_id': vehicle.id,
            'driver_id': self.driver.partner_id.id,
        })
        now = fields.Datetime.now()
        self.order = self.env['wm.collection.order'].create({
            'partner_id': customer.id,
            'collection_point_id': point.id,
            'route_id': route.id,
            'vehicle_id': vehicle.id,
            'driver_id': self.driver.partner_id.id,
            'scheduled_start': now,
            'scheduled_end': now + datetime.timedelta(hours=1),
            'state': 'dispatched',
            'order_line_ids': [(0, 0, {'category_id': category.id})],
        })
        self.api_key = self.env['res.users.apikeys'].with_user(self.driver).sudo()._generate(
            'rpc', 'driver js test', fields.Datetime.now() + datetime.timedelta(days=1))

    def _run_js(self, body, timeout=90):
        """Run ``body`` on the driver app page once its offline database is open."""
        code = (
            "(async () => {\n"
            "    try {\n" + JS_HELPERS + body +
            "\n        console.log('test successful');\n"
            "    } catch (e) {\n"
            "        console.error('Driver app JS test failed: ' + e.message + ' ' + (e.stack || ''));\n"
            "    }\n"
            "})();\n"
        )
        self.browser_js('/driver/app', code, ready="typeof db !== 'undefined' && !!db", timeout=timeout)

    def test_01_pure_helpers(self):
        self._run_js(JS_PURE_HELPERS)

    def test_02_credentials_queue_and_sync_indicator(self):
        self._run_js(JS_STORAGE_AND_QUEUE)

    def test_03_api_client_and_databases(self):
        self._run_js(JS_API_AND_DATABASES)

    def test_04_ui_helpers_and_modals(self):
        self._run_js(JS_UI_AND_MODALS)

    def test_05_submit_status_sync_and_route(self):
        self._run_js(JS_SUBMIT_AND_SYNC)

    def test_06_screen_handlers(self):
        self._run_js(JS_SCREEN_HANDLERS)

    def test_09_sync_lock_and_rejected_updates(self):
        self._run_js(JS_SYNC_LOCK_AND_REJECTED)

    def test_07_service_worker(self):
        self._run_js(JS_SERVICE_WORKER)

    def test_08_real_server_round_trip(self):
        """The app's own API client against the real controllers."""
        params = '{"key": "%s", "db": "%s", "order": %d}' % (self.api_key, self.env.cr.dbname, self.order.id)
        body = (
            "const P = " + params + ";\n"
            "await reset();\n"
            "useRealFetch();\n"
            "state.serverUrl = ''; state.apiKey = P.key; state.database = P.db;\n"
            "await fetchTodayRoute();\n"
            "eq(state.stops.length, 1, 'route loaded from the server (' + $('toast').textContent + ')');\n"
            "eq(state.stops[0].order_id, P.order, 'the driver order');\n"
            "state.currentStop = state.stops[0];\n"
            "await submitStatus(P.order, 'en_route', '', null);\n"
            "eq((await queueGetAll()).length, 0, 'accepted by the server');\n"
            "eq(state.stops[0].last_status, 'en_route', 'status kept');\n"
            "await submitStatus(P.order, 'lifted', '', null);\n"
            "eq((await queueGetAll()).length, 0, 'invalid transition removed from the queue');\n"
            "assert($('toast').className.includes('error'), 'rejection shown');\n"
        )
        self._run_js(body)
        logs = self.env['wm.collection.order.status.log'].search([('order_id', '=', self.order.id)])
        self.assertEqual(logs.mapped('status'), ['en_route'])

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
import json

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

XSS_NAME = 'XSS <img src=x onerror="window.__wm_xss=1">'


@tagged('post_install', '-at_install', 'wm_driver_app')
class TestUiDriverApp(HttpCase):
    """
    Runs the driver PWA in headless Chrome against the real API: stop list
    escaping, and the offline queue rules (rejected updates are dropped
    without blocking the queue; updates are kept when the network fails).
    """

    def setUp(self):
        super().setUp()
        self.driver = new_test_user(self.env, login='wm_ui_driver', groups='wm_base.group_wm_driver')
        customer = self.env['res.partner'].create({'name': 'Driver UI ' + XSS_NAME})
        point = self.env['wm.collection.point'].create({
            'name': 'Driver UI Point', 'partner_id': customer.id, 'street': XSS_NAME,
        })
        category = self.env['wm.waste.category'].create({'name': 'Driver UI Category', 'code': 'DRVUI'})
        brand = self.env['fleet.vehicle.model.brand'].create({'name': 'Driver UI Brand'})
        model = self.env['fleet.vehicle.model'].create({'name': 'Driver UI Truck', 'brand_id': brand.id})
        vehicle = self.env['fleet.vehicle'].create({
            'model_id': model.id, 'license_plate': 'DRV-UI-1', 'driver_id': self.driver.partner_id.id,
        })
        route = self.env['wm.route'].create({
            'date': fields.Date.context_today(self.driver),
            'vehicle_id': vehicle.id,
            'driver_id': self.driver.partner_id.id,
        })
        now = fields.Datetime.now()
        self.orders = self.env['wm.collection.order'].create([{
            'partner_id': customer.id,
            'collection_point_id': point.id,
            'route_id': route.id,
            'vehicle_id': vehicle.id,
            'driver_id': self.driver.partner_id.id,
            'scheduled_start': now,
            'scheduled_end': now + datetime.timedelta(hours=1),
            'state': 'dispatched',
            'order_line_ids': [(0, 0, {'category_id': category.id})],
        } for _i in range(2)])
        self.api_key = self.env['res.users.apikeys'].with_user(self.driver).sudo()._generate(
            'rpc', 'driver ui test', fields.Datetime.now() + datetime.timedelta(days=1))

    def test_driver_app_ui(self):
        params = json.dumps({
            'key': self.api_key,
            'db': self.env.cr.dbname,
            'order1': self.orders[0].id,
            'order2': self.orders[1].id,
        })
        code = """
            (async () => {
                const P = %s;
                const assert = (cond, msg) => { if (!cond) { throw new Error(msg); } };
                try {
                    // The app calls the API with credentials: 'omit'; the test
                    // server only serves requests carrying its test cookie.
                    const appFetch = window.fetch.bind(window);
                    window.fetch = (url, opts = {}) => appFetch(url, {...opts, credentials: 'same-origin'});
                    saveCredentials(location.origin, P.key, P.db);
                    state.serverUrl = '';
                    state.apiKey = P.key;
                    state.database = P.db;

                    // Stop list: server strings are escaped (X-16)
                    await fetchTodayRoute();
                    const list = document.getElementById('stop-list');
                    assert(list.querySelectorAll('.stop-card').length === 2,
                           'expected 2 stops, got ' + list.querySelectorAll('.stop-card').length);
                    assert(list.textContent.includes('onerror'), 'customer name not shown as text');
                    assert(!list.querySelector('img[src="x"]') && !window.__wm_xss, 'HTML from the server was rendered');

                    const base = {
                        note: '', photo: null, lineWeights: null, latitude: 0, longitude: 0,
                        timestamp: new Date().toISOString().replace('T', ' ').split('.')[0],
                    };
                    // A rejected update at the head neither blocks the queue nor is retried: it
                    // stays, flagged, so the driver's data is never silently lost
                    await queuePut({...base, clientUuid: crypto.randomUUID(), orderId: P.order1, status: 'bogus', createdAt: 1});
                    await queuePut({...base, clientUuid: crypto.randomUUID(), orderId: P.order1, status: 'en_route', createdAt: 2});
                    await syncQueue();
                    let left = await queueGetAll();
                    assert(left.length === 1 && !!left[0].rejectedReason && left[0].status === 'bogus',
                           'expected only the flagged rejected update to remain, got ' + left.length);

                    // A network failure keeps the update queued for later (D-01)
                    const realFetch = window.fetch;
                    window.fetch = () => Promise.reject(new TypeError('Failed to fetch'));
                    await queuePut({...base, clientUuid: crypto.randomUUID(), orderId: P.order2, status: 'en_route', createdAt: 3});
                    await syncQueue();
                    window.fetch = realFetch;
                    left = (await queueGetAll()).filter((e) => !e.rejectedReason);
                    assert(left.length === 1, 'update lost on network failure');
                    await syncQueue();
                    left = (await queueGetAll()).filter((e) => !e.rejectedReason);
                    assert(left.length === 0, 'queued update not sent once back online');

                    console.log('test successful');
                } catch (e) {
                    console.error('Driver app UI test failed: ' + e.message);
                }
            })();
        """ % params
        self.browser_js('/driver/app', code, ready="typeof db !== 'undefined' && !!db", timeout=60)

        Log = self.env['wm.collection.order.status.log']
        for order in self.orders:
            self.assertTrue(Log.search_count([('order_id', '=', order.id), ('status', '=', 'en_route')]),
                            "the en_route update reached the server")
        self.assertFalse(Log.search_count([('order_id', 'in', self.orders.ids), ('status', '=', 'bogus')]))

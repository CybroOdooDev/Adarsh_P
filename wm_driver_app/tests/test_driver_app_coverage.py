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
from unittest.mock import MagicMock, patch

from odoo.exceptions import AccessError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppLogStatusCoverage(TransactionCase):
    """Validation, ownership and error paths of ``log_status``."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()
        Users = cls.env['res.users']
        groups = [(6, 0, [
            cls.env.ref('base.group_user').id,
            cls.env.ref('wm_base.group_wm_driver').id,
        ])]
        cls.customer = cls.env['res.partner'].create({'name': 'Cov Customer'})
        cls.driver_partner = cls.env['res.partner'].create({'name': 'Cov Driver'})
        cls.driver_user = Users.create({
            'name': 'Cov Driver', 'login': 'cov_driver',
            'partner_id': cls.driver_partner.id, 'group_ids': groups,
        })
        cls.other_partner = cls.env['res.partner'].create({'name': 'Cov Other Driver'})
        cls.other_user = Users.create({
            'name': 'Cov Other', 'login': 'cov_other_driver',
            'partner_id': cls.other_partner.id, 'group_ids': groups,
        })
        cls.cat1 = cls.env['wm.waste.category'].create({'name': 'Cov Cat 1', 'code': 'COV1'})
        cls.cat2 = cls.env['wm.waste.category'].create({'name': 'Cov Cat 2', 'code': 'COV2'})
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Cov Point', 'partner_id': cls.customer.id,
            'category_ids': [(6, 0, [cls.cat1.id, cls.cat2.id])],
        })
        cls.route = cls.env['wm.route'].create({
            'name': 'Cov Route', 'driver_id': cls.driver_partner.id,
        })

    def _order(self, state='dispatched', last_status=None):
        order = self.env['wm.collection.order'].create({
            'partner_id': self.customer.id,
            'collection_point_id': self.point.id,
            'route_id': self.route.id,
            'state': state,
        })
        self.line1 = self.env['wm.collection.order.line'].create({
            'order_id': order.id, 'category_id': self.cat1.id,
            'estimated_weight': 10.0, 'weight': 0.0,
        })
        if last_status:
            self.env['wm.collection.order.status.log'].create({
                'order_id': order.id, 'status': last_status,
                'driver_id': self.driver_user.id,
            })
        return order

    def _call(self, user=None, **kwargs):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user or self.driver_user)
        # ``_()`` resolves the language through ``odoo.http.request`` too.
        with patch.object(main, 'request', mock_req), \
                patch('odoo.http.request', mock_req):
            return self.controller.log_status(**kwargs)

    def test_01_other_driver_denied(self):
        order = self._order()
        with self.assertRaises(AccessError):
            self._call(user=self.other_user, order_id=order.id, status='en_route')
        self.assertFalse(order.status_log_ids)

    def test_02_missing_order_denied(self):
        with self.assertRaises(AccessError):
            self._call(order_id=0, status='en_route')

    def test_03_invalid_status(self):
        order = self._order()
        res = self._call(order_id=order.id, status='bogus')
        self.assertEqual(res['error'], 'invalid_status')
        self.assertIn('en_route', res['valid'])
        res = self._call(order_id=order.id)
        self.assertEqual(res['error'], 'invalid_status')

    def test_04_stop_not_active(self):
        order = self._order(state='draft')
        res = self._call(order_id=order.id, status='en_route')
        self.assertEqual(res['error'], 'stop_not_active')

    def test_05_whitespace_flag_note_rejected(self):
        order = self._order()
        reason = self.env.ref('wm_collection.missed_reason_access_issue')
        for note in ('', '   ', '\n\t', None):
            res = self._call(order_id=order.id, status='flagged', note=note,
                             missed_reason_id=reason.id)
            self.assertEqual(res['error'], 'note_required_for_flagged_status')
        self.assertFalse(order.status_log_ids)
        res = self._call(order_id=order.id, status='flagged', note='Blocked gate',
                         missed_reason_id=reason.id)
        self.assertTrue(res['log_id'])
        self.assertFalse(res['duplicate'])

    def test_05b_flag_requires_a_valid_missed_reason(self):
        """A flag marks the order missed, so it carries a reason code."""
        order = self._order()
        for bad in (None, '', 'not-an-id', 0):
            res = self._call(order_id=order.id, status='flagged',
                             note='Blocked gate', missed_reason_id=bad)
            self.assertEqual(res['error'], 'missed_reason_required')
        archived = self.env['wm.missed.reason'].create({'name': 'Retired', 'active': False})
        res = self._call(order_id=order.id, status='flagged', note='Blocked gate',
                         missed_reason_id=archived.id)
        self.assertEqual(res['error'], 'invalid_missed_reason')
        self.assertFalse(order.status_log_ids)

    def test_06_bad_coordinates(self):
        order = self._order()
        res = self._call(order_id=order.id, status='en_route', latitude='abc')
        self.assertEqual(res['error'], 'invalid_coordinates')
        res = self._call(order_id=order.id, status='en_route', longitude=[1])
        self.assertEqual(res['error'], 'invalid_coordinates')
        self.assertFalse(order.status_log_ids)

    def test_07_good_coordinates_as_strings_and_none(self):
        order = self._order()
        res = self._call(order_id=order.id, status='en_route',
                         latitude='10.5', longitude=None)
        self.assertTrue(res['log_id'])
        log = self.env['wm.collection.order.status.log'].browse(res['log_id'])
        self.assertAlmostEqual(log.latitude, 10.5)
        self.assertEqual(log.location_source, 'device')

    def test_07b_missing_position_is_estimated(self):
        """No position from the phone (null, or 0 from older apps): the log
        gets the collection point's coordinates, marked as estimated."""
        self.point.write({'latitude': 11.25, 'longitude': 75.75})
        Log = self.env['wm.collection.order.status.log']
        for lat, lng in ((None, None), (0, 0)):
            order = self._order()
            res = self._call(order_id=order.id, status='en_route', latitude=lat, longitude=lng)
            log = Log.browse(res['log_id'])
            self.assertEqual((log.latitude, log.longitude, log.location_source),
                             (11.25, 75.75, 'collection_point'))
        self.point.write({'latitude': 0.0, 'longitude': 0.0})
        order = self._order()
        res = self._call(order_id=order.id, status='en_route', latitude=None, longitude=None)
        log = Log.browse(res['log_id'])
        self.assertEqual((log.latitude, log.longitude, log.location_source), (0.0, 0.0, 'none'))

    def test_08_weighed_requires_list(self):
        order = self._order(last_status='started')
        for lw in (None, {'category_id': self.cat1.id, 'weight': 5}, 'x'):
            res = self._call(order_id=order.id, status='weighed', line_weights=lw)
            self.assertEqual(res['error'], 'weight_required')

    def test_09_non_dict_line_weight_entry(self):
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed', line_weights=[5])
        self.assertEqual(res['error'], 'invalid_weight')

    def test_10_invalid_category_id(self):
        order = self._order(last_status='started')
        for cid in (None, 'abc'):
            res = self._call(order_id=order.id, status='weighed',
                             line_weights=[{'category_id': cid, 'weight': 5}])
            self.assertEqual(res['error'], 'invalid_category_id')

    def test_11_non_numeric_weight(self):
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed',
                         line_weights=[{'category_id': self.cat1.id, 'weight': 'heavy'}])
        self.assertEqual(res['error'], 'invalid_weight')

    def test_12_all_zero_weights_rejected(self):
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed',
                         line_weights=[{'category_id': self.cat1.id, 'weight': 0}])
        self.assertEqual(res['error'], 'weight_required')

    def test_13_invalid_removed_category_id(self):
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed',
                         line_weights=[{'category_id': self.cat1.id, 'weight': 5}],
                         removed_category_ids=['zzz'])
        self.assertEqual(res['error'], 'invalid_category_id')
        self.assertEqual(self.line1.weight, 0.0)

    def test_14_weigh_creates_line_and_appends_note(self):
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed', note='Hello',
                         line_weights=[{'category_id': self.cat2.id, 'weight': '7.5'}])
        self.assertTrue(res['log_id'])
        new_line = order.order_line_ids.filtered(lambda ln: ln.category_id == self.cat2)
        self.assertEqual(new_line.weight, 7.5)
        log = self.env['wm.collection.order.status.log'].browse(res['log_id'])
        self.assertIn('Hello', log.note)
        self.assertIn('Weighed: ', log.note)

    def test_15_weigh_removes_category_and_zeroes_omitted(self):
        order = self._order(last_status='started')
        self.line1.weight = 3.0
        line2 = self.env['wm.collection.order.line'].create({
            'order_id': order.id, 'category_id': self.cat2.id,
            'estimated_weight': 1.0, 'weight': 0.0,
        })
        res = self._call(order_id=order.id, status='weighed',
                         line_weights=[{'category_id': self.cat2.id, 'weight': 4}],
                         removed_category_ids=[self.cat1.id])
        self.assertTrue(res['log_id'])
        self.assertFalse(self.line1.exists())
        self.assertEqual(line2.weight, 4.0)

    def test_16_weigh_rejected_leaves_weights_untouched_on_bad_coordinates(self):
        """A rejected update must not persist weight changes."""
        order = self._order(last_status='started')
        res = self._call(order_id=order.id, status='weighed', latitude='bad',
                         line_weights=[{'category_id': self.cat1.id, 'weight': 9}])
        self.assertEqual(res['error'], 'invalid_coordinates')
        self.assertEqual(self.line1.weight, 0.0)

    def test_17_timestamps(self):
        order = self._order()
        res = self._call(order_id=order.id, status='en_route', timestamp='not-a-date',
                         client_uuid='cov-ts-1')
        self.assertTrue(res['log_id'])

    def test_18_bad_photo_does_not_break(self):
        order = self._order()
        res = self._call(order_id=order.id, status='en_route', photo='!!!not base64!!!')
        self.assertTrue(res['log_id'])

    def test_19_duplicate_uuid_same_driver(self):
        order = self._order()
        first = self._call(order_id=order.id, status='en_route', client_uuid='cov-dup')
        second = self._call(order_id=order.id, status='en_route', client_uuid='cov-dup')
        self.assertEqual(first['log_id'], second['log_id'])
        self.assertTrue(second['duplicate'])

    def test_20_completed_stop_rejected(self):
        order = self._order(state='completed')
        res = self._call(order_id=order.id, status='en_route')
        self.assertEqual(res['error'], 'stop_already_completed')


@tagged('post_install', '-at_install')
class TestDriverAppHttpCoverage(HttpCase):
    """Public PWA routes and bearer authentication."""

    def test_01_manifest(self):
        res = self.url_open('/driver/app/manifest.json')
        self.assertEqual(res.status_code, 200)
        self.assertIn('manifest+json', res.headers['Content-Type'])
        data = res.json()
        self.assertEqual(data['start_url'], '/driver/app')
        self.assertTrue(data['icons'])

    def test_02_assetlinks(self):
        res = self.url_open('/.well-known/assetlinks.json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()[0]['target']['namespace'], 'android_app')

    def test_03_service_worker(self):
        res = self.url_open('/driver/app/sw.js')
        self.assertEqual(res.status_code, 200)
        self.assertIn('javascript', res.headers['Content-Type'])
        self.assertEqual(res.headers['Service-Worker-Allowed'], '/driver/app')
        self.assertEqual(res.headers['Cache-Control'], 'no-cache')
        self.assertTrue(res.text)

    def test_04_bearer_routes_reject_anonymous(self):
        for url in ('/driver/api/route/today', '/driver/api/stop/1/status'):
            res = self.url_open(url, data='{}', headers={'Content-Type': 'application/json'})
            self.assertTrue(res.status_code in (401, 403) or 'error' in res.json(), url)
            self.assertNotIn('result', res.json() if res.status_code == 200 else {}, url)
            res = self.url_open(url, data='{}', headers={
                'Content-Type': 'application/json',
                'Authorization': 'Bearer not-a-real-key'})
            self.assertTrue(res.status_code in (401, 403) or 'error' in res.json(), url)
            self.assertNotIn('result', res.json() if res.status_code == 200 else {}, url)

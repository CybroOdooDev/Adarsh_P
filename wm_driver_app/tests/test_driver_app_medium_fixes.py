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

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppMediumFixes(TransactionCase):
    """Regression tests: weighed category removal, inactive orders and the
    database/session endpoints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()
        cls.customer = cls.env['res.partner'].create({'name': 'Medium Fix Customer'})
        cls.driver_partner = cls.env['res.partner'].create({'name': 'Medium Fix Driver'})
        cls.driver_user = cls.env['res.users'].create({
            'name': 'Medium Fix Driver User',
            'login': 'driver_medium_fix_user',
            'partner_id': cls.driver_partner.id,
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('wm_base.group_wm_driver').id,
            ])],
        })
        cls.cat_1 = cls.env['wm.waste.category'].create({'name': 'MF Paper', 'code': 'MF-PAP'})
        cls.cat_2 = cls.env['wm.waste.category'].create({'name': 'MF Metal', 'code': 'MF-MET'})
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Medium Fix Point',
            'partner_id': cls.customer.id,
            'category_ids': [(6, 0, [cls.cat_1.id, cls.cat_2.id])],
        })
        cls.route = cls.env['wm.route'].create({
            'name': 'Medium Fix Route',
            'driver_id': cls.driver_partner.id,
        })

    def _order(self, state='dispatched', last_status='started'):
        order = self.env['wm.collection.order'].create({
            'partner_id': self.customer.id,
            'collection_point_id': self.point.id,
            'route_id': self.route.id,
            'state': state,
        })
        if last_status:
            self.env['wm.collection.order.status.log'].create({
                'order_id': order.id,
                'status': last_status,
                'driver_id': self.driver_user.id,
            })
        return order

    def _mock_request(self, user=None):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user or self.driver_user)
        return mock_req

    def _log(self, order, status, uuid, **kwargs):
        with patch.object(main, 'request', self._mock_request()):
            return self.controller.log_status(
                order_id=order.id, status=status, client_uuid=uuid, **kwargs)

    def test_removed_category_weight_is_reset(self):
        """D-05: a category removed in the weighed modal loses its old weight."""
        order = self._order()
        res = self._log(order, 'weighed', 'mf-w-1', line_weights=[
            {'category_id': self.cat_1.id, 'weight': 20.0},
            {'category_id': self.cat_2.id, 'weight': 15.0},
        ])
        self.assertTrue(res.get('log_id'))
        res = self._log(order, 'weighed', 'mf-w-2', line_weights=[
            {'category_id': self.cat_1.id, 'weight': 25.0},
        ])
        self.assertTrue(res.get('log_id'))
        weights = {line.category_id: line.weight for line in order.order_line_ids}
        self.assertEqual(weights[self.cat_1], 25.0)
        self.assertEqual(weights[self.cat_2], 0.0)

    def test_explicitly_removed_category_line_is_deleted(self):
        """BUG-019: a category the driver removed in the modal is dropped, so it
        cannot leave a zero-weight line that blocks completion."""
        order = self._order()
        res = self._log(order, 'weighed', 'mf-w-5', line_weights=[
            {'category_id': self.cat_1.id, 'weight': 20.0},
            {'category_id': self.cat_2.id, 'weight': 15.0},
        ])
        self.assertTrue(res.get('log_id'))
        res = self._log(order, 'weighed', 'mf-w-6', line_weights=[
            {'category_id': self.cat_1.id, 'weight': 25.0},
        ], removed_category_ids=[self.cat_2.id])
        self.assertTrue(res.get('log_id'))
        self.assertEqual(order.order_line_ids.category_id, self.cat_1)
        self.assertEqual(order.order_line_ids.weight, 25.0)

    def test_weighed_requires_a_weight(self):
        """D-05: a weighed event needs at least one positive weight."""
        order = self._order()
        res = self._log(order, 'weighed', 'mf-w-3', line_weights=[
            {'category_id': self.cat_1.id, 'weight': 0.0},
        ])
        self.assertEqual(res.get('error'), 'weight_required')
        self.assertTrue(res.get('message'))
        res = self._log(order, 'weighed', 'mf-w-4')
        self.assertEqual(res.get('error'), 'weight_required')
        self.assertFalse(order.status_log_ids.filtered(lambda ln: ln.status == 'weighed'))

    def test_inactive_orders_reject_status_logs(self):
        """D-06: cancelled / draft stops cannot receive status logs."""
        for state in ('cancelled', 'draft'):
            order = self._order(state=state, last_status=None)
            res = self._log(order, 'en_route', 'mf-s-%s' % state)
            self.assertEqual(res.get('error'), 'stop_not_active', state)
            self.assertTrue(res.get('message'))
            self.assertFalse(order.status_log_ids)

    def test_missed_stop_can_still_be_resumed(self):
        """A stop the driver flagged is missed, but not closed to them."""
        order = self._order(state='missed', last_status=None)
        res = self._log(order, 'en_route', 'mf-s-missed')
        self.assertTrue(res.get('log_id'))
        self.assertEqual(order.state, 'dispatched')
        self.assertFalse(order.is_missed)

    def test_db_list_respects_list_db(self):
        """X-17: /driver/app/dbs does not bypass list_db=False."""
        mock_req = self._mock_request()
        mock_req.db = 'current_db'
        with patch.object(main, 'request', mock_req), \
                patch.object(main, 'config', {'list_db': False}), \
                patch.object(main.router, 'db_list') as db_list:
            res = self.controller.list_databases()
        db_list.assert_not_called()
        self.assertEqual(res, {'databases': ['current_db']})

        with patch.object(main, 'request', mock_req), \
                patch.object(main, 'config', {'list_db': True}), \
                patch.object(main.router, 'db_list', return_value=['a', 'b']) as db_list:
            res = self.controller.list_databases()
        self.assertEqual(res, {'databases': ['a', 'b']})
        self.assertFalse(db_list.call_args.kwargs.get('force'))

    def test_shell_does_not_touch_session(self):
        """X-18: GET /driver/app?db=... never logs the session out or switches db."""
        mock_req = self._mock_request()
        mock_req.session.db = 'backend_db'
        with patch.object(main, 'request', mock_req):
            # Bypass the route wrapper's response coercion of the mocked render
            DriverAppController.driver_app_shell.original_endpoint(self.controller, db='other_db')
        mock_req.session.logout.assert_not_called()
        self.assertEqual(mock_req.session.db, 'backend_db')
        self.assertFalse(hasattr(self.controller, 'switch_db'))

    def test_future_device_timestamp_is_clamped_to_server_time(self):
        """A driver phone with a wrong (future) clock must not freeze the stop status."""
        from odoo import fields
        order = self._order(last_status=None)
        res = self._log(order, 'en_route', 'mf-ts-1', timestamp='2099-01-01 00:00:00')
        self.assertTrue(res.get('log_id'))
        log = self.env['wm.collection.order.status.log'].browse(res['log_id'])
        self.assertLessEqual(log.timestamp, fields.Datetime.now())

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

import psycopg2.errors

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppDecisions(TransactionCase):
    """Decision 11: a client_uuid already used by another driver's status
    log is rejected with the normal error shape (no server error)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()
        cls.customer = cls.env['res.partner'].create({'name': 'Dec Customer'})
        cls.cat = cls.env['wm.waste.category'].create({'name': 'Dec Paper', 'code': 'DEC-PAP'})
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Dec Point',
            'partner_id': cls.customer.id,
            'category_ids': [(6, 0, [cls.cat.id])],
        })
        cls.driver_a, cls.order_a = cls._driver_with_order('a')
        cls.driver_b, cls.order_b = cls._driver_with_order('b')

    @classmethod
    def _driver_with_order(cls, suffix):
        partner = cls.env['res.partner'].create({'name': 'Dec Driver %s' % suffix})
        user = cls.env['res.users'].create({
            'name': 'Dec Driver User %s' % suffix,
            'login': 'driver_decision_%s' % suffix,
            'partner_id': partner.id,
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('wm_base.group_wm_driver').id,
            ])],
        })
        route = cls.env['wm.route'].create({'name': 'Dec Route %s' % suffix, 'driver_id': partner.id})
        order = cls.env['wm.collection.order'].create({
            'partner_id': cls.customer.id,
            'collection_point_id': cls.point.id,
            'route_id': route.id,
            'state': 'dispatched',
        })
        cls.env['wm.collection.order.status.log'].create({
            'order_id': order.id, 'status': 'started', 'driver_id': user.id,
        })
        return user, order

    def _log(self, user, order, status, uuid, **kwargs):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user)
        with patch.object(main, 'request', mock_req):
            return self.controller.log_status(
                order_id=order.id, status=status, client_uuid=uuid, **kwargs)

    def test_same_driver_retry_is_idempotent(self):
        res = self._log(self.driver_a, self.order_a, 'lifted', 'dec-uuid-same')
        self.assertFalse(res.get('duplicate'))
        again = self._log(self.driver_a, self.order_a, 'lifted', 'dec-uuid-same')
        self.assertEqual(again, {'log_id': res['log_id'], 'duplicate': True})

    def test_other_driver_uuid_is_rejected(self):
        res = self._log(self.driver_a, self.order_a, 'lifted', 'dec-uuid-shared')
        self.assertTrue(res.get('log_id'))
        logs_before = self.order_b.status_log_ids
        other = self._log(self.driver_b, self.order_b, 'lifted', 'dec-uuid-shared')
        self.assertEqual(other.get('error'), 'duplicate_client_uuid')
        self.assertTrue(other.get('message'))
        # The other driver's log id is never disclosed
        self.assertNotIn('log_id', other)
        self.assertEqual(self.order_b.status_log_ids, logs_before)

    def test_unique_violation_race_is_rejected_and_rolled_back(self):
        """If the pre-check misses a concurrent insert, the unique violation
        is caught in a savepoint: weights are rolled back, nothing crashes."""
        StatusLog = type(self.env['wm.collection.order.status.log'])

        def _raise(*args, **kwargs):
            raise psycopg2.errors.UniqueViolation()

        self._log(self.driver_b, self.order_b, 'lifted', 'dec-race-1')
        with patch.object(StatusLog, 'log_stop_event', side_effect=_raise), \
                mute_logger('odoo.addons.wm_driver_app.controllers.main'):
            res = self._log(self.driver_b, self.order_b, 'weighed', 'dec-race-2',
                            line_weights=[{'category_id': self.cat.id, 'weight': 12.0}])
        self.assertEqual(res.get('error'), 'duplicate_client_uuid')
        self.assertFalse(any(self.order_b.order_line_ids.mapped('weight')))

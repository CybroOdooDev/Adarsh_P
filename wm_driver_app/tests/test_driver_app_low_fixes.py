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
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..controllers import main
from ..controllers.main import DriverAppController


@tagged('post_install', '-at_install')
class TestDriverAppLowFixes(TransactionCase):
    """X-20: client_uuid de-duplication is scoped to the calling driver."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()
        cls.customer = cls.env['res.partner'].create({'name': 'Low Fix Customer'})
        cls.cat = cls.env['wm.waste.category'].create({'name': 'LF Paper', 'code': 'LF-PAP'})
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Low Fix Point',
            'partner_id': cls.customer.id,
            'category_ids': [(6, 0, [cls.cat.id])],
        })
        groups = [(6, 0, [
            cls.env.ref('base.group_user').id,
            cls.env.ref('wm_base.group_wm_driver').id,
        ])]
        cls.driver_a = cls.env['res.users'].create({
            'name': 'Low Fix Driver A', 'login': 'driver_low_fix_a', 'group_ids': groups,
        })
        cls.driver_b = cls.env['res.users'].create({
            'name': 'Low Fix Driver B', 'login': 'driver_low_fix_b', 'group_ids': groups,
        })
        cls.route_a = cls.env['wm.route'].create({
            'name': 'Low Fix Route A', 'driver_id': cls.driver_a.partner_id.id,
        })

    def _order(self):
        return self.env['wm.collection.order'].create({
            'partner_id': self.customer.id,
            'collection_point_id': self.point.id,
            'route_id': self.route_a.id,
            'state': 'dispatched',
        })

    def _log(self, user, order, status, uuid):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user)
        with patch.object(main, 'request', mock_req):
            return self.controller.log_status(
                order_id=order.id, status=status, client_uuid=uuid)

    def test_client_uuid_stored_at_creation_and_retry_deduplicated(self):
        order = self._order()
        self.assertEqual(order.driver_id, self.driver_a.partner_id)
        res = self._log(self.driver_a, order, 'en_route', 'lf-uuid-1')
        self.assertFalse(res['duplicate'])
        log = self.env['wm.collection.order.status.log'].browse(res['log_id'])
        self.assertEqual(log.client_uuid, 'lf-uuid-1')
        retry = self._log(self.driver_a, order, 'en_route', 'lf-uuid-1')
        self.assertEqual(retry, {'log_id': log.id, 'duplicate': True})

    def test_other_driver_cannot_probe_log_by_uuid(self):
        """Replaying another driver's client_uuid must not return their log id."""
        order = self._order()
        res = self._log(self.driver_a, order, 'en_route', 'lf-uuid-2')
        self.assertTrue(res['log_id'])
        with self.assertRaises(AccessError):
            self._log(self.driver_b, order, 'en_route', 'lf-uuid-2')

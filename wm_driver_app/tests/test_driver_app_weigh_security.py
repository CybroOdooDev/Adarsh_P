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
class TestDriverAppWeighSecurity(TransactionCase):
    """Test suite verifying driver app weigh step validation and line preservation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()

        cls.partner_customer = cls.env['res.partner'].create({
            'name': 'Customer Test Weigh',
        })
        cls.driver_partner = cls.env['res.partner'].create({
            'name': 'Driver Weigh Partner',
        })
        cls.driver_user = cls.env['res.users'].create({
            'name': 'Driver Weigh User',
            'login': 'driver_weigh_user',
            'partner_id': cls.driver_partner.id,
            'group_ids': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.env.ref('wm_base.group_wm_driver').id,
            ])],
        })

        cls.waste_cat_1 = cls.env['wm.waste.category'].create({
            'name': 'Plastic Waste Weigh',
            'code': 'PLAS-W',
        })
        cls.waste_cat_2 = cls.env['wm.waste.category'].create({
            'name': 'Glass Waste Weigh',
            'code': 'GLAS-W',
        })
        cls.waste_cat_disallowed = cls.env['wm.waste.category'].create({
            'name': 'Hazardous Waste Disallowed',
            'code': 'HAZ-W',
        })

        # Collection point allowing only cat_1 and cat_2
        cls.collection_point = cls.env['wm.collection.point'].create({
            'name': 'Collection Point Weigh',
            'partner_id': cls.partner_customer.id,
            'category_ids': [(6, 0, [cls.waste_cat_1.id, cls.waste_cat_2.id])],
        })

        cls.route = cls.env['wm.route'].create({
            'name': 'Route Weigh',
            'driver_id': cls.driver_partner.id,
        })

        cls.order = cls.env['wm.collection.order'].create({
            'partner_id': cls.partner_customer.id,
            'collection_point_id': cls.collection_point.id,
            'route_id': cls.route.id,
            'state': 'dispatched',
        })

        # Pre-existing lines: Plastic (cat_1) with estimated weight and Glass (cat_2)
        cls.line_plastic = cls.env['wm.collection.order.line'].create({
            'order_id': cls.order.id,
            'category_id': cls.waste_cat_1.id,
            'estimated_weight': 50.0,
            'weight': 0.0,
        })
        cls.line_glass = cls.env['wm.collection.order.line'].create({
            'order_id': cls.order.id,
            'category_id': cls.waste_cat_2.id,
            'estimated_weight': 30.0,
            'weight': 0.0,
        })

        # Order has arrived and started so that weighing is a valid lifecycle step
        cls.env['wm.collection.order.status.log'].create({
            'order_id': cls.order.id,
            'status': 'started',
            'driver_id': cls.driver_user.id,
        })

    def _mock_request(self, user):
        mock_req = MagicMock()
        mock_req.env = self.env(user=user)
        return mock_req

    def test_01_partial_weigh_does_not_delete_other_lines(self):
        """Submitting weights for only some categories must NOT delete other lines on the order."""
        mock_req = self._mock_request(self.driver_user)
        with patch.object(main, 'request', mock_req):
            res = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-01',
                line_weights=[{'category_id': self.waste_cat_1.id, 'weight': 65.5}],
            )
        self.assertTrue(res.get('log_id'))
        # Both lines must still exist
        self.assertTrue(self.line_plastic.exists())
        self.assertTrue(self.line_glass.exists())
        # Plastic confirmed weight updated
        self.assertEqual(self.line_plastic.weight, 65.5)
        # Glass line preserved with original estimated weight
        self.assertEqual(self.line_glass.estimated_weight, 30.0)

    def test_02_empty_line_weights_does_not_wipe_lines(self):
        """Submitting empty line_weights is rejected and must NOT delete lines on the order."""
        mock_req = self._mock_request(self.driver_user)
        with patch.object(main, 'request', mock_req):
            res = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-02',
                line_weights=[],
            )
        self.assertEqual(res.get('error'), 'weight_required')
        self.assertTrue(self.line_plastic.exists())
        self.assertTrue(self.line_glass.exists())

    def test_03_reject_disallowed_categories(self):
        """Submitting a category not allowed for the collection point must be rejected."""
        mock_req = self._mock_request(self.driver_user)
        with patch.object(main, 'request', mock_req):
            res = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-03',
                line_weights=[{'category_id': self.waste_cat_disallowed.id, 'weight': 10.0}],
            )
        self.assertEqual(res.get('error'), 'disallowed_category')

    def test_04_reject_invalid_weights(self):
        """Submitting negative, NaN, infinite, or non-numeric weights must return an error."""
        mock_req = self._mock_request(self.driver_user)

        # Negative weight
        with patch.object(main, 'request', mock_req):
            res_neg = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-04-a',
                line_weights=[{'category_id': self.waste_cat_1.id, 'weight': -100.0}],
            )
        self.assertEqual(res_neg.get('error'), 'invalid_weight')

        # NaN string
        with patch.object(main, 'request', mock_req):
            res_nan = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-04-b',
                line_weights=[{'category_id': self.waste_cat_1.id, 'weight': 'nan'}],
            )
        self.assertEqual(res_nan.get('error'), 'invalid_weight')

        # Infinity string
        with patch.object(main, 'request', mock_req):
            res_inf = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='uuid-weigh-04-c',
                line_weights=[{'category_id': self.waste_cat_1.id, 'weight': 'inf'}],
            )
        self.assertEqual(res_inf.get('error'), 'invalid_weight')

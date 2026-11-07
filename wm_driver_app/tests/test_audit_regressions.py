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
class TestDriverAppAuditRegressions(TransactionCase):
    """Regression tests for driver app defects confirmed by the 2026-10 ERP audit."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = DriverAppController()
        cls.customer = cls.env['res.partner'].create({'name': 'Audit Driver Customer'})
        cls.driver_partner = cls.env['res.partner'].create({'name': 'Audit Driver'})
        cls.driver_user = cls.env['res.users'].create({
            'name': 'Audit Driver User',
            'login': 'audit_driver_app_user',
            'partner_id': cls.driver_partner.id,
            'group_ids': [(6, 0, [cls.env.ref('base.group_user').id, cls.env.ref('wm_base.group_wm_driver').id])],
        })
        cls.plastics = cls.env['wm.waste.category'].create({'name': 'Audit Plastics', 'code': 'AUD-PLA'})
        cls.pet = cls.env['product.product'].create({
            'name': 'Audit PET', 'is_waste_material': True, 'wm_waste_category_id': cls.plastics.id})
        cls.hdpe = cls.env['product.product'].create({
            'name': 'Audit HDPE', 'is_waste_material': True, 'wm_waste_category_id': cls.plastics.id})
        cls.point = cls.env['wm.collection.point'].create({
            'name': 'Audit Driver Site', 'partner_id': cls.customer.id,
            'category_ids': [(6, 0, cls.plastics.ids)],
        })
        cls.route = cls.env['wm.route'].create({'name': 'Audit Driver Route', 'driver_id': cls.driver_partner.id})
        cls.order = cls.env['wm.collection.order'].create({
            'partner_id': cls.customer.id,
            'collection_point_id': cls.point.id,
            'route_id': cls.route.id,
            'state': 'dispatched',
            'order_line_ids': [
                (0, 0, {'category_id': cls.plastics.id, 'product_id': cls.pet.id, 'estimated_weight': 200.0}),
                (0, 0, {'category_id': cls.plastics.id, 'product_id': cls.hdpe.id, 'estimated_weight': 100.0}),
            ],
        })
        cls.env['wm.collection.order.status.log'].create({
            'order_id': cls.order.id, 'status': 'started', 'driver_id': cls.driver_user.id,
        })

    # AUD-030: one category weight was written to every line of that category
    def test_category_weight_is_not_duplicated_across_lines(self):
        mock_req = MagicMock()
        mock_req.env = self.env(user=self.driver_user)
        with patch.object(main, 'request', mock_req):
            res = self.controller.log_status(
                order_id=self.order.id,
                status='weighed',
                client_uuid='audit-weigh-01',
                line_weights=[{'category_id': self.plastics.id, 'weight': 300.0}],
            )
        self.assertTrue(res.get('log_id'), res)
        lines = self.order.order_line_ids.filtered(lambda ln: ln.category_id == self.plastics)
        self.assertEqual(len(lines), 2, "Both product lines are kept")
        self.assertAlmostEqual(sum(lines.mapped('weight')), 300.0,
                               msg="The weighed 300 kg must be recorded once, not once per line")
        self.assertAlmostEqual(self.order.confirmed_weight, 300.0)

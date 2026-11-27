# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
from odoo.tests import common, tagged


@tagged('post_install', '-at_install')
class TestMrpProductionCost(common.TransactionCase):
    """Test cost per hour calculation on MRP production orders."""

    def setUp(self):
        super().setUp()
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))

        self.test_user = self.env['res.users'].create({
            'name': 'Test User Cost',
            'login': 'test_user_cost',
            'email': 'test_user_cost@example.com',
            'group_ids': [(6, 0, [self.env.ref('mrp.group_mrp_manager').id, self.env.ref('base.group_user').id])]
        })

        self.test_employee = self.env['hr.employee'].create({
            'name': 'Test Employee',
            'user_id': self.test_user.id,
            'hour_per_cost': 50.0,
        })
        self.test_user.employee_id = self.test_employee.id

        self.workcenter = self.env['mrp.workcenter'].create({
            'name': 'Test Workcenter',
        })

        self.env['cost.per.employee'].create({
            'employee_id': self.test_employee.id,
            'mrp_workcenter_id': self.workcenter.id,
        })

        self.product = self.env['product.product'].create({
            'name': 'Test Final Product',
            'is_storable': True,
        })
        self.component = self.env['product.product'].create({
            'name': 'Test Component',
            'is_storable': True,
        })

        self.bom = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'normal',
            'bom_line_ids': [
                (0, 0, {'product_id': self.component.id, 'product_qty': 1.0})
            ],
            'operation_ids': [
                (0, 0, {
                    'name': 'Test Operation',
                    'workcenter_id': self.workcenter.id,
                    'time_cycle_manual': 60,
                })
            ]
        })

        self.production = self.env['mrp.production'].create({
            'product_id': self.product.id,
            'uom_id': self.product.uom_id.id,
            'product_qty': 1.0,
            'bom_id': self.bom.id,
        })

    def test_cost_per_hour_computation(self):
        """Test the cost per hour computation for an employee."""
        self.production.action_confirm()
        self.production = self.production.with_user(self.test_user)

        self.assertTrue(self.production.workorder_ids, "Workorders should be created")
        workorder = self.production.workorder_ids[0]
        workorder.duration = 120.0

        self.production._compute_cost_per_hour()

        # 50.0 per hour * (120 min / 60) = 100.0
        self.assertEqual(self.production.cost_per_hour, 100.0, "Cost per hour computation failed.")

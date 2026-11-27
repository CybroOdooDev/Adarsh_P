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
class TestReportMoOverviewCost(common.TransactionCase):
    """Test cost per employee in MO Overview report."""

    def setUp(self):
        super().setUp()
        self.env = self.env(context=dict(self.env.context, tracking_disable=True))

        self.test_user = self.env['res.users'].create({
            'name': 'Test User Report',
            'login': 'test_user_report',
            'email': 'test_user_report@example.com',
            'group_ids': [(6, 0, [self.env.ref('mrp.group_mrp_manager').id, self.env.ref('base.group_user').id])]
        })

        self.test_employee = self.env['hr.employee'].create({
            'name': 'Test Employee Report',
            'user_id': self.test_user.id,
            'hour_per_cost': 40.0,
        })
        self.test_user.employee_id = self.test_employee.id

        self.workcenter = self.env['mrp.workcenter'].create({
            'name': 'Report Workcenter',
        })

        self.env['cost.per.employee'].create({
            'employee_id': self.test_employee.id,
            'mrp_workcenter_id': self.workcenter.id,
        })

        self.product = self.env['product.product'].create({
            'name': 'Report Product',
            'is_storable': True,
        })
        self.component = self.env['product.product'].create({
            'name': 'Report Component',
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
                    'name': 'Report Operation',
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

    def test_report_mo_overview_data(self):
        """Test report data includes the employee cost."""
        self.production.action_confirm()
        self.production = self.production.with_user(self.test_user)

        self.assertTrue(self.production.workorder_ids, "Workorders should be created")
        workorder = self.production.workorder_ids[0]
        workorder.duration = 90.0

        self.production._compute_cost_per_hour()

        report = self.env['report.mrp.report_mo_overview'].with_user(self.test_user)
        report_data = report._get_report_data(self.production.id)

        self.assertIn('cost_per_employ', report_data)
        self.assertEqual(report_data['cost_per_employ'], 60.0)

        # Check that extras unit_mo_cost contains the cost
        self.assertIn('unit_mo_cost', report_data['extras'])

# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Sruthi c(odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0(OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('standard', 'post_install', '-at_install')
class TestFleetDashboard(FleetRentalCommon):
    """Tests for the fleet.dashboard model."""

    def test_get_datas_keys(self):
        data = self.env['fleet.dashboard'].get_datas()
        for key in ('total_vehicles', 'total_contracts',
                    'total_contract_working', 'total_contract_return',
                    'total_contract_cancel', 'operational',
                    'under_maintenance', 'all_customers', 'all_invoices',
                    'pending_invoices'):
            self.assertIn(key, data)

    def test_get_datas_counts(self):
        dashboard = self.env['fleet.dashboard']
        before = dashboard.get_datas()
        working = self._create_contract()
        working.state = 'in_progress'
        returned = self._create_contract()
        returned.state = 'return'
        cancelled = self._create_contract()
        cancelled.action_cancel()
        self.vehicle.status = 'undermaintenance'
        working.write({'is_extra_charge': True, 'total_extra_hours': 2})
        working.action_create_extra_invoice()
        after = dashboard.get_datas()
        self.assertEqual(after['total_contracts'],
                         before['total_contracts'] + 3)
        self.assertEqual(after['total_contract_working'],
                         before['total_contract_working'] + 1)
        self.assertEqual(after['total_contract_return'],
                         before['total_contract_return'] + 1)
        self.assertEqual(after['total_contract_cancel'],
                         before['total_contract_cancel'] + 1)
        self.assertEqual(after['under_maintenance'],
                         before['under_maintenance'] + 1)
        self.assertEqual(after['all_invoices'], before['all_invoices'] + 1)
        self.assertEqual(after['pending_invoices'],
                         before['pending_invoices'] + 1)

    def test_get_monthly_contract_invoices(self):
        dashboard = self.env['fleet.dashboard']
        before = dashboard.get_monthly_contract_invoices()
        self.assertEqual(len(before['labels']), 12)
        self.assertEqual(len(before['data']), 12)
        contract = self._create_contract(
            is_extra_charge=True, total_extra_hours=1)
        contract.action_create_extra_invoice()
        after = dashboard.get_monthly_contract_invoices()
        month = self._today().month - 1
        self.assertEqual(after['data'][month], before['data'][month] + 1)

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
from datetime import timedelta

from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('standard', 'post_install', '-at_install')
class TestRentalPaymentPlan(FleetRentalCommon):
    """Tests for the rental.payment.plan model."""

    def _create_plan(self, contract, payment_date=None):
        return self.env['rental.payment.plan'].create({
            'contract_id': contract.id,
            'invoice_item_id': contract.invoice_item_id.id,
            'payment_date': payment_date or self._today(),
            'payment_amount': 100.0,
        })

    def test_payment_state_without_invoice(self):
        contract = self._create_contract()
        plan = self._create_plan(contract)
        self.assertEqual(plan.payment_state, 'not_paid')
        self.assertFalse(plan.is_invoiced)

    def test_action_create_invoice(self):
        contract = self._create_contract()
        plan = self._create_plan(contract)
        invoice = plan.action_create_invoice()
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.vehicle_rental_id, contract)
        self.assertEqual(invoice.amount_untaxed, 100.0)
        self.assertEqual(plan.invoice_id, invoice)
        self.assertTrue(plan.is_invoiced)
        self.assertEqual(plan.payment_state, invoice.payment_state)

    def test_schedule_auto_invoice_checker(self):
        contract = self._create_contract()
        due = self._create_plan(contract)
        later = self._create_plan(
            contract, self._today() + timedelta(days=10))
        self.env['rental.payment.plan']._schedule_auto_invoice_checker()
        self.assertTrue(due.invoice_id)
        self.assertFalse(later.invoice_id)

    def test_plan_removed_with_contract(self):
        contract = self._create_contract()
        plan = self._create_plan(contract)
        contract.unlink()
        self.assertFalse(plan.exists())

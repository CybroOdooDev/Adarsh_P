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
from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('standard', 'post_install', '-at_install')
class TestFleetRentalContract(FleetRentalCommon):
    """Tests for the fleet.rental.contract model."""

    def test_create_sets_sequence_and_computes_period(self):
        contract = self._create_contract()
        self.assertTrue(contract.name)
        self.assertEqual(contract.state, 'new')
        self.assertEqual(contract.total_days, 3)
        self.assertEqual(contract.total_hours, 48.0)
        # default rent type is hours: 48 * 10
        self.assertEqual(contract.total_rental_charge, 480.0)

    def test_create_multi_and_missing_period(self):
        contracts = self.env['fleet.rental.contract'].create([
            self._contract_vals(),
            self._contract_vals(),
        ])
        self.assertEqual(len(contracts), 2)
        self.assertNotEqual(contracts[0].name, contracts[1].name)

    def test_compute_period_without_dates(self):
        record = self.env['fleet.rental.contract'].new({})
        record._compute_rental_period()
        self.assertEqual(record.total_days, 0)
        self.assertEqual(record.total_hours, 0)

    def test_total_rental_charge_by_rent_type(self):
        days = self._create_contract(rent_type='days')
        self.assertEqual(days.total_rental_charge, 300.0)
        kms = self._create_contract(rent_type='kilometers', total_km=100)
        self.assertEqual(kms.total_rental_charge, 200.0)

    def test_total_rental_charge_with_driver(self):
        including = self._create_contract(
            rent_type='days', driver_required=True,
            charge_type='including', driver_charge=20.0)
        self.assertEqual(including.total_rental_charge, 320.0)
        excluding = self._create_contract(
            rent_type='days', driver_required=True,
            charge_type='excluding', driver_charge=20.0)
        self.assertEqual(excluding.total_rental_charge, 300.0)

    def test_total_extra_charge_by_rent_type(self):
        hours = self._create_contract(
            rent_type='hours', is_extra_charge=True, total_extra_hours=2)
        self.assertEqual(hours.total_extra_charge, 10.0)
        days = self._create_contract(
            rent_type='days', is_extra_charge=True, total_extra_days=3)
        self.assertEqual(days.total_extra_charge, 150.0)
        kms = self._create_contract(
            rent_type='kilometers', is_extra_charge=True,
            total_extra_km=10.0, total_km=1)
        self.assertEqual(kms.total_extra_charge, 10.0)

    def test_onchange_states(self):
        contract = self._create_contract()
        contract.pickup_country_id = False
        contract.dropoff_country_id = False
        contract._onchange_pickup_state()
        contract._onchange_dropoff_state()
        self.assertEqual(contract.pickup_country_id, self.state.country_id)
        self.assertEqual(contract.dropoff_country_id, self.state.country_id)

    def test_group_expand_states(self):
        contract = self._create_contract()
        self.assertEqual(
            contract._group_expand_states(),
            ['new', 'in_progress', 'return', 'cancel'])

    def test_rental_period_constraints(self):
        contract = self._create_contract()
        with self.assertRaises(ValidationError):
            contract.write({'total_hours': 1000.0})
        with self.assertRaises(ValidationError):
            contract.write({'total_hours': 0.0})
        contract.rent_type = 'days'
        with self.assertRaises(ValidationError):
            contract.write({'total_days': 1000})
        with self.assertRaises(ValidationError):
            contract.write({'total_days': 0})

    def test_zero_length_rental_is_rejected(self):
        same = datetime(2026, 1, 1, 8, 0, 0)
        with self.assertRaises(ValidationError):
            self._create_contract(pickup_date=same, dropoff_date=same)

    def test_installment_full(self):
        contract = self._create_contract(rent_type='days')
        contract.action_installment()
        plans = contract.rental_payment_plan_ids
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans.payment_amount, contract.total_rental_charge)
        # generating again replaces the previous plan
        contract.action_installment()
        self.assertEqual(len(contract.rental_payment_plan_ids), 1)

    def test_installment_validations(self):
        km_contract = self._create_contract(rent_type='kilometers')
        with self.assertRaises(ValidationError):
            km_contract.action_installment()
        km_contract.total_km = 10
        km_contract.payment_type = 'daily'
        with self.assertRaises(ValidationError):
            km_contract.action_installment()

        hours_contract = self._create_contract(payment_type='daily')
        with self.assertRaises(ValidationError):
            hours_contract.action_installment()

        short_week = self._create_contract(
            rent_type='days', payment_type='weekly')
        with self.assertRaises(ValidationError):
            short_week.action_installment()
        short_month = self._create_contract(
            rent_type='days', payment_type='monthly')
        with self.assertRaises(ValidationError):
            short_month.action_installment()

    def test_installment_daily(self):
        contract = self._create_contract(
            rent_type='days', payment_type='daily',
            pickup_date=datetime(2026, 1, 1), dropoff_date=datetime(2026, 1, 4))
        contract.action_installment()
        plans = contract.rental_payment_plan_ids
        self.assertEqual(len(plans), 4)
        self.assertAlmostEqual(
            sum(plans.mapped('payment_amount')), contract.total_rental_charge)

    def test_installment_weekly(self):
        contract = self._create_contract(
            rent_type='days', payment_type='weekly',
            pickup_date=datetime(2026, 1, 1),
            dropoff_date=datetime(2026, 1, 15))
        contract.action_installment()
        plans = contract.rental_payment_plan_ids
        self.assertEqual(len(plans), 3)
        self.assertAlmostEqual(
            sum(plans.mapped('payment_amount')), contract.total_rental_charge)

    def test_installment_monthly(self):
        contract = self._create_contract(
            rent_type='days', payment_type='monthly',
            pickup_date=datetime(2026, 1, 1),
            dropoff_date=datetime(2026, 3, 15))
        contract.action_installment()
        plans = contract.rental_payment_plan_ids
        self.assertTrue(plans)
        self.assertAlmostEqual(
            sum(plans.mapped('payment_amount')), contract.total_rental_charge)

    def test_action_create_extra_invoice(self):
        contract = self._create_contract(
            is_extra_charge=True, total_extra_hours=2)
        contract.action_create_extra_invoice()
        invoice = self.env['account.move'].search(
            [('vehicle_rental_id', '=', contract.id)])
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.amount_untaxed, 10.0)
        self.assertEqual(contract.vehicle_to_invoice_count, 1)

    def test_action_extra_invoice_charge(self):
        contract = self._create_contract()
        with self.assertRaises(ValidationError):
            contract.action_extra_invoice_charge()
        self.env['extra.service'].create({
            'contract_id': contract.id,
            'product_id': self.product_a.id,
            'quantity': 2.0,
            'description': 'Child seat',
        })
        contract.action_extra_invoice_charge()
        self.assertTrue(contract.is_extra_invoice_created)
        invoice = self.env['account.move'].search(
            [('vehicle_rental_id', '=', contract.id)])
        self.assertEqual(len(invoice), 1)
        self.assertEqual(invoice.state, 'posted')

    def test_action_account_tab(self):
        contract = self._create_contract()
        action = contract.action_account_tab()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertIn(('vehicle_rental_id', '=', contract.id),
                      action['domain'])

    def test_action_damage_invoice(self):
        contract = self._create_contract()
        action = contract.action_damage_invoice()
        self.assertEqual(action['res_model'], 'damage.invoice')
        self.assertEqual(action['context']['default_contract_id'],
                         contract.id)

    def test_action_cancel(self):
        contract = self._create_contract()
        contract.action_cancel()
        self.assertEqual(contract.state, 'cancel')

    def test_action_cancel_charges(self):
        contract = self._create_contract()
        with self.assertRaises(ValidationError):
            contract.action_cancel_charges()
        policy = self.env['cancellation.policy'].create({
            'name': 'Strict',
            'terms_conditions': 'No refund after pick-up.',
        })
        contract.write({
            'cancellation_policy_id': policy.id,
            'cancellation_charge': 50.0,
        })
        self.assertEqual(contract.cancellation_terms,
                         'No refund after pick-up.')
        action = contract.action_cancel_charges()
        self.assertTrue(contract.is_cancelled_invoiced)
        self.assertEqual(action['res_model'], 'account.move')
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(invoice.vehicle_rental_id, contract)
        self.assertEqual(invoice.amount_untaxed, 50.0)

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
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('standard', 'post_install', '-at_install')
class TestDamageInvoice(FleetRentalCommon):
    """Tests for the damage.invoice wizard."""

    def _create_damage_wizard(self, **kwargs):
        """Helper to build a damage.invoice record in context."""
        contract = self._create_contract()
        vals = {
            'contract_id': contract.id,
            'is_damage': True,
            'damage_amount': 500.0,
            'description': 'Scratched bumper',
        }
        vals.update(kwargs)
        return self.env['damage.invoice'].create(vals)

    def test_action_create_damage_invoice_success(self):
        """Full success path: invoice created, posted, contract fields updated."""
        wizard = self._create_damage_wizard()
        contract = wizard.contract_id
        action = wizard.action_create_damage_invoice()

        # Returned action should open the new invoice
        self.assertEqual(action['res_model'], 'account.move')
        self.assertEqual(action['view_mode'], 'form')
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertTrue(invoice.exists())
        self.assertEqual(invoice.state, 'posted')
        self.assertEqual(invoice.partner_id, contract.customer_id)
        self.assertEqual(invoice.vehicle_rental_id, contract)
        self.assertAlmostEqual(invoice.amount_untaxed, 500.0)

    def test_action_create_damage_invoice_updates_contract(self):
        """Contract fields is_damaged_invoiced, damage_description,
        and damage_amount must be stamped after the wizard runs."""
        wizard = self._create_damage_wizard(
            damage_amount=750.0, description='Cracked windshield')
        contract = wizard.contract_id
        self.assertFalse(contract.is_damaged_invoiced)
        wizard.action_create_damage_invoice()
        self.assertTrue(contract.is_damaged_invoiced)
        self.assertEqual(contract.damage_description, 'Cracked windshield')
        self.assertAlmostEqual(contract.damage_amount, 750.0)

    def test_action_create_damage_invoice_no_description(self):
        """Damage invoice can be created even when description is empty."""
        wizard = self._create_damage_wizard(description=False)
        action = wizard.action_create_damage_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        self.assertEqual(invoice.state, 'posted')

    def test_action_create_damage_invoice_no_contract_raises(self):
        """Must raise ValidationError when no contract is linked."""
        wizard = self.env['damage.invoice'].create({
            'is_damage': True,
            'damage_amount': 100.0,
        })
        with self.assertRaises(ValidationError):
            wizard.action_create_damage_invoice()

    def test_action_create_damage_invoice_zero_amount_raises(self):
        """Must raise ValidationError when damage_amount is 0."""
        wizard = self._create_damage_wizard(damage_amount=0.0)
        with self.assertRaises(ValidationError):
            wizard.action_create_damage_invoice()

    def test_damage_invoice_line_uses_correct_product(self):
        """Invoice line must reference the damage-charge product from data."""
        wizard = self._create_damage_wizard()
        action = wizard.action_create_damage_invoice()
        invoice = self.env['account.move'].browse(action['res_id'])
        damage_product = self.env.ref(
            'advanced_fleet_rental.product_product_vehicle_damage_charge')
        line_products = invoice.invoice_line_ids.mapped('product_id')
        self.assertIn(damage_product, line_products)

    def test_contract_action_damage_invoice_opens_wizard(self):
        """FleetRentalContract.action_damage_invoice returns the wizard
        window action with the correct defaults."""
        contract = self._create_contract()
        action = contract.action_damage_invoice()
        self.assertEqual(action['res_model'], 'damage.invoice')
        self.assertEqual(action['view_mode'], 'form')
        self.assertEqual(action['target'], 'new')
        self.assertEqual(
            action['context']['default_contract_id'], contract.id)

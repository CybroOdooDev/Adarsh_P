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
import base64

from odoo.tests import tagged

from .common import FleetRentalCommon


@tagged('standard', 'post_install', '-at_install')
class TestMiscModels(FleetRentalCommon):
    """Tests for the small supporting models."""

    def test_extra_service_amount(self):
        contract = self._create_contract()
        service = self.env['extra.service'].create({
            'contract_id': contract.id,
            'product_id': self.product_a.id,
            'quantity': 3.0,
        })
        self.assertEqual(service.unit_price, self.product_a.lst_price)
        self.assertAlmostEqual(
            service.amount, 3.0 * self.product_a.lst_price)
        service.quantity = 5.0
        self.assertAlmostEqual(
            service.amount, 5.0 * self.product_a.lst_price)

    def test_insurance_policy(self):
        contract = self._create_contract()
        policy = self.env['insurance.policy'].create({
            'policy_number': 'POL-001',
            'name': 'Full cover',
            'policy_amount': 1000.0,
            'contract_id': contract.id,
        })
        self.assertEqual(contract.insurance_ids, policy)

    def test_multi_image_removed_with_contract(self):
        contract = self._create_contract()
        image = self.env['multi.image'].create({
            'contract_id': contract.id,
            'image': base64.b64encode(b'image-data').decode('ascii'),
        })
        self.assertEqual(contract.image_ids, image)
        contract.unlink()
        self.assertFalse(image.exists())

    def test_cancellation_policy(self):
        policy = self.env['cancellation.policy'].create({
            'name': 'Flexible',
            'terms_conditions': 'Free cancellation.',
        })
        self.assertEqual(policy.name, 'Flexible')

    def test_vehicle_defaults(self):
        self.assertEqual(self.vehicle.status, 'operational')
        self.assertEqual(self.vehicle.rent_day, 100.0)

    def test_account_move_link(self):
        contract = self._create_contract(
            is_extra_charge=True, total_extra_hours=1)
        contract.action_create_extra_invoice()
        invoice = self.env['account.move'].search(
            [('vehicle_rental_id', '=', contract.id)])
        self.assertEqual(invoice.vehicle_rental_id, contract)

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

from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class FleetRentalCommon(AccountTestInvoicingCommon):
    """Shared fixtures for the advanced_fleet_rental test-suite."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref('fleet.fleet_group_manager')
        seq = cls.env.ref('advanced_fleet_rental.vehicle_sequence_id', raise_if_not_found=False)
        if seq:
            seq.sudo().write({'company_id': False})
        cls.brand = cls.env['fleet.vehicle.model.brand'].sudo().create(
            {'name': 'Test Brand'})
        cls.vehicle_model = cls.env['fleet.vehicle.model'].sudo().create({
            'name': 'Test Model',
            'brand_id': cls.brand.id,
        })
        cls.vehicle = cls.env['fleet.vehicle'].sudo().create({
            'model_id': cls.vehicle_model.id,
            'license_plate': 'TEST-001',
            'rent_hour': 10.0,
            'rent_day': 100.0,
            'rent_kilometer': 2.0,
            'charge_hour': 5.0,
            'charge_day': 50.0,
            'charge_kilometer': 1.0,
        })
        cls.country = cls.env.ref('base.us')
        cls.state = cls.env['res.country.state'].search(
            [('country_id', '=', cls.country.id)], limit=1)
        cls.customer = cls.partner_a

    @classmethod
    def _contract_vals(cls, **kwargs):
        vals = {
            'customer_id': cls.customer.id,
            'vehicle_id': cls.vehicle.id,
            'pickup_date': datetime(2026, 1, 1, 8, 0, 0),
            'dropoff_date': datetime(2026, 1, 3, 8, 0, 0),
            'pickup_location': 'Pick Location',
            'dropoff_location': 'Drop Location',
            'pickup_street': 'Pick Street',
            'dropoff_street': 'Drop Street',
            'pickup_city': 'Pick City',
            'dropoff_city': 'Drop City',
            'pickup_state_id': cls.state.id,
            'dropoff_state_id': cls.state.id,
            'pickup_zip': '12345',
            'dropoff_zip': '54321',
            'pickup_country_id': cls.country.id,
            'dropoff_country_id': cls.country.id,
            'responsible_id': cls.env.user.id,
        }
        vals.update(kwargs)
        return vals

    @classmethod
    def _create_contract(cls, **kwargs):
        return cls.env['fleet.rental.contract'].create(
            cls._contract_vals(**kwargs))

    @staticmethod
    def _today():
        return fields.Date.today()

# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models


class PharmaShipmentTemperature(models.Model):
    """A temperature reading inside the vehicle during the journey.

    Readings can be typed in, or imported from the logger's CSV export with
    the standard Import feature of the list.
    """
    _name = 'pharma.shipment.temperature'
    _description = 'Shipment Temperature Reading'
    _order = 'reading_time, id'

    shipment_id = fields.Many2one('pharma.shipment', string='Shipment',
                                  required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='shipment_id.company_id', store=True)
    reading_time = fields.Datetime(string='Time', required=True,
                                   default=fields.Datetime.now)
    temperature = fields.Float(string='Temperature (°C)', required=True,
                               digits=(4, 1))
    source = fields.Selection([
        ('manual', 'Manual'),
        ('logger', 'Data Logger'),
    ], string='Source', required=True, default='manual')
    location = fields.Char(string='Location')
    is_excursion = fields.Boolean(
        string='Excursion', compute='_compute_is_excursion', store=True,
        help='Reading outside the storage range of the shipment.')

    @api.depends('temperature', 'shipment_id.temp_min', 'shipment_id.temp_max',
                 'shipment_id.temperature_controlled')
    def _compute_is_excursion(self):
        for reading in self:
            shipment = reading.shipment_id
            reading.is_excursion = bool(
                shipment.temperature_controlled
                and (reading.temperature < shipment.temp_min
                     or reading.temperature > shipment.temp_max))

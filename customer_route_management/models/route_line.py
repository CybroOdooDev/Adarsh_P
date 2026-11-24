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
from odoo import fields, models


class RouteLine(models.Model):
    """Area of a delivery route, with the customers delivered there."""
    _name = 'route.line'
    _description = 'Route Line'
    _rec_name = 'route'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10, help="Order of the area in the route.")
    route = fields.Char(help="Name of the area of the route.")
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
        help="Company the route line belongs to.")
    delivery_route_link_id = fields.Many2one(
        'delivery.route', string='Delivery Route', index=True,
        help="Delivery route the area belongs to.")
    cust_list_ids = fields.One2many(
        'res.partner', 'location_id', string='Customers',
        help="Customers delivered in this area of the route.")

    def _get_customers(self):
        """Customers of the area, in their delivery order."""
        self.ensure_one()
        return self.cust_list_ids.sorted(lambda partner: (partner.sequence, partner.id))

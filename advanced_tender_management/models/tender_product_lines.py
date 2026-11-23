# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)

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
#    If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import fields, models


class TenderProductLines(models.Model):
    """Product, section or note line of a tender."""
    _name = "tender.product.lines"
    _description = 'Tender Product Lines'
    _order = 'sequence, id'

    name = fields.Char(string='Description', required=True,
                       help='Description of the product line.')
    tender_id = fields.Many2one('tender.management',
                                help='Tender the line belongs to.')
    product_id = fields.Many2one('product.product',
                                 help='Product requested in the tender.')
    product_code = fields.Char(string='Code', related='product_id.default_code',
                               help='Internal reference of the product.')
    product_qty = fields.Integer(string='Qty', default=1,
                                 help='Requested quantity.')
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
                                     related='product_id.uom_id',
                                     help='Unit of measure of the product.')
    display_type = fields.Selection(
        selection=[
            ('line_section', "Section"),
            ('line_note', "Note"),
        ],
        default=False, help='Technical field for sections and notes.')
    sequence = fields.Integer(default=10, help='Order of the line in the tender.')

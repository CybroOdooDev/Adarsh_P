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

class ContractLine(models.Model):
    _name = 'contract.line'
    _description = 'Waste Management Contract for Partner'

    waste_categ_id = fields.Many2one(
        'product.category',
        compute='_compute_waste_categ_id',
        string='Waste Category',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        domain="[('categ_id', '=', waste_categ_id)]",
    )
    contract_id = fields.Many2one('partner.contract', string='Contract', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    price = fields.Monetary(string='Price', required=True)

    @api.depends()
    def _compute_waste_categ_id(self):
        """Resolve the Waste category from its external ID for use in domain filtering."""
        categ = self.env.ref(
            'waste_management_partner.data_product_category_waste',
            raise_if_not_found=False,
        )
        for rec in self:
            rec.waste_categ_id = categ


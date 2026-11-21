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
from odoo.exceptions import ValidationError


class PharmaShipmentLine(models.Model):
    """One product (batch, package) carried in a shipment, copied from a
    move line of the delivery order. The received and damaged quantities
    are the customer's count at proof of delivery."""
    _name = 'pharma.shipment.line'
    _description = 'Shipment Line'
    _order = 'shipment_id, package_id, product_id, id'

    shipment_id = fields.Many2one('pharma.shipment', string='Shipment',
                                  required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one(related='shipment_id.company_id', store=True)
    product_id = fields.Many2one('product.product', string='Product',
                                 required=True, ondelete='restrict')
    move_id = fields.Many2one('stock.move', string='Stock Move', readonly=True,
                              ondelete='set null')
    lot_id = fields.Many2one('stock.lot', string='Batch', ondelete='restrict')
    lot_status = fields.Selection(related='lot_id.lot_status',
                                  string='QA Status')
    manufacture_date = fields.Date(related='lot_id.manufacture_date',
                                   string='Mfg. Date')
    expiration_date = fields.Date(string='Expiry Date')
    hsn_code = fields.Char(compute='_compute_hsn_code', string='HSN Code')
    price_unit = fields.Float(string='Unit Value', digits='Product Price',
                              help='Price of the sales order line, or the sales '
                                   'price of the product. Printed on the delivery challan.')
    currency_id = fields.Many2one(related='company_id.currency_id')
    tax_ids = fields.Many2many(
        'account.tax', 'pharma_shipment_line_tax_rel', 'line_id', 'tax_id',
        string='Taxes', help='Taxes of the sales order line, or the customer '
                             'taxes of the product.')
    value = fields.Monetary(compute='_compute_amounts', string='Taxable Value',
                            currency_field='currency_id')
    tax_amount = fields.Monetary(compute='_compute_amounts', string='Tax',
                                 currency_field='currency_id')
    total_amount = fields.Monetary(compute='_compute_amounts', string='Total',
                                   currency_field='currency_id')
    quantity = fields.Float(string='Shipped', digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='Unit', required=True)
    package_id = fields.Many2one('stock.package', string='Package',
                                 ondelete='restrict')
    package_type_id = fields.Many2one(related='package_id.package_type_id',
                                      string='Package Type')

    # Proof of delivery
    received_qty = fields.Float(
        string='Received', digits='Product Unit',
        compute='_compute_received_qty', store=True, readonly=False,
        help='Quantity accepted by the customer in good condition. '
             'Proposed as the shipped quantity.')
    damaged_qty = fields.Float(string='Damaged', digits='Product Unit',
                               help='Quantity delivered damaged.')
    shortage_qty = fields.Float(string='Short', digits='Product Unit',
                                compute='_compute_shortage_qty', store=True,
                                help='Shipped quantity that did not arrive.')
    receipt_note = fields.Char(string='Receipt Remarks')

    @api.depends('product_id')
    def _compute_hsn_code(self):
        for line in self:
            product = line.product_id
            line.hsn_code = (
                product.product_tmpl_id.hsn_code
                or ('l10n_in_hsn_code' in product._fields and product.l10n_in_hsn_code)
                or ('hs_code' in product._fields and product.hs_code)
                or False)

    def _tax_result(self):
        self.ensure_one()
        return self.tax_ids.compute_all(
            self.price_unit, currency=self.currency_id, quantity=self.quantity,
            product=self.product_id, partner=self.shipment_id.partner_id)

    @api.depends('quantity', 'price_unit', 'tax_ids')
    def _compute_amounts(self):
        for line in self:
            if not line.tax_ids:
                line.value = line.total_amount = line.currency_id.round(
                    line.quantity * line.price_unit) if line.currency_id else \
                    line.quantity * line.price_unit
                line.tax_amount = 0.0
                continue
            res = line._tax_result()
            line.value = res['total_excluded']
            line.total_amount = res['total_included']
            line.tax_amount = res['total_included'] - res['total_excluded']

    @api.depends('quantity')
    def _compute_received_qty(self):
        for line in self:
            line.received_qty = line.quantity

    @api.depends('quantity', 'received_qty', 'damaged_qty')
    def _compute_shortage_qty(self):
        for line in self:
            line.shortage_qty = max(
                line.quantity - line.received_qty - line.damaged_qty, 0.0)

    @api.constrains('quantity', 'received_qty', 'damaged_qty')
    def _check_received_qty(self):
        for line in self:
            if line.received_qty < 0 or line.damaged_qty < 0:
                raise ValidationError(self.env._(
                    'Received and damaged quantities cannot be negative.'))
            if line.received_qty + line.damaged_qty > line.quantity:
                raise ValidationError(self.env._(
                    'Received plus damaged quantity of %s is more than was shipped.',
                    line.product_id.display_name))

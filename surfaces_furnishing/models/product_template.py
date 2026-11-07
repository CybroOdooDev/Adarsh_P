# -*- coding: utf-8 -*-
from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    has_warranty = fields.Boolean(
        string='Has Warranty',
        default=False,
        help='Toggle ON if this product or material includes warranty or defects liability coverage.'
    )
    warranty_duration_months = fields.Integer(
        string='Warranty Duration (Months)',
        default=12,
        help='Duration of warranty coverage in months.'
    )
    warranty_type = fields.Selection([
        ('replacement', 'Full Replacement'),
        ('repair', 'Repair & Service'),
        ('parts', 'Parts Only'),
        ('manufacturer', 'Manufacturer Warranty'),
    ], string='Warranty Coverage Type', default='repair')
    warranty_terms = fields.Text(
        string='Warranty Terms & Scope',
        help='Specific warranty conditions, exclusions, or vendor guarantees for this item.'
    )

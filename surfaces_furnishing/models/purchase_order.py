# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    project_id = fields.Many2one(
        'furnishing.project',
        string='Furnishing Project',
        tracking=True,
        index=True
    )
    is_subcontractor = fields.Boolean(
        string='Subcontractor Trade Order',
        help='Check if this order is for outsourced labor (e.g. curtain stitching, floor laying, automation).'
    )
    subcontractor_trade = fields.Char(string='Trade Scope')

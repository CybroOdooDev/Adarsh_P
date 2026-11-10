# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    project_id = fields.Many2one(
        'project.project',
        string='Project',
        domain=[('is_template', '=', False)],
        tracking=True,
        index=True
    )

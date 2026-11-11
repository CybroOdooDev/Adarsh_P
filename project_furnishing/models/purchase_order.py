# -*- coding: utf-8 -*-
from odoo import models, fields


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        related='project_id.is_furnishing_project',
        store=True,
        index=True
    )

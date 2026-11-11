# -*- coding: utf-8 -*-
from odoo import models, fields


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    is_furnishing_project = fields.Boolean(
        string='Furnishing Project',
        related='project_id.is_furnishing_project',
        store=True,
        index=True
    )

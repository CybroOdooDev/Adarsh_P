# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    module_hr_timesheet = fields.Boolean(
        string="Timesheets",
        help="Track time spent on furnishing projects, tasks, and site surveys."
    )
    group_product_pricelist = fields.Boolean(
        string="Pricelists",
        implied_group="product.group_product_pricelist",
        help="Set multiple prices per product, customer discounts, and pricelist rules."
    )
    group_furnishing_manufacturing = fields.Boolean(
        string="Manufacturing",
        implied_group="project_furnishing.group_furnishing_manufacturing",
        help="Show Production menu with Bills of Materials (BOM) and Manufacturing Orders in Furnishing Projects."
    )

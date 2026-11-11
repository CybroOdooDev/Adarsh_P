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
        string="Manufacturing & Production",
        implied_group="project_furnishing.group_furnishing_manufacturing",
        help="Enable the Production menu (Manufacturing Orders, BOM, Quality Checks) in Furnishing Projects."
    )
    furnishing_default_warranty_months = fields.Integer(
        related='company_id.furnishing_default_warranty_months',
        readonly=False,
        string='Default Warranty Duration (Months)',
        help='Default Defects Liability Period (DLP) / warranty duration in months for new furnishing projects.'
    )
    furnishing_qc_location_id = fields.Many2one(
        related='company_id.furnishing_qc_location_id',
        readonly=False,
        string='Quality Inspection Location',
        help='Finished furniture will land in this quarantine location upon MO completion, and auto-transfer to main stock when QC passes.'
    )

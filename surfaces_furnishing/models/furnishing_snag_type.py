# -*- coding: utf-8 -*-
from odoo import models, fields


class FurnishingSnagType(models.Model):
    _name = 'furnishing.snag.type'
    _description = 'Snag and Defect Category'
    _order = 'name'

    name = fields.Char(string='Defect Type', required=True, translate=True)
    category = fields.Selection([
        ('joinery', 'Joinery & Woodwork'),
        ('soft_furnishing', 'Curtains & Soft Furnishings'),
        ('flooring', 'Flooring & Carpets'),
        ('lighting', 'Lighting & Electrical'),
        ('wallcovering', 'Wallcoverings & Paint'),
        ('other', 'Other Defect')
    ], string='Trade Category', default='joinery', required=True)
    default_trade = fields.Char(
        string='Responsible Trade / Subcontractor',
        help='Default trade or contractor responsible for fixing this defect.'
    )
    sla_hours = fields.Integer(
        string='Target Resolution SLA (Hours)',
        default=48,
        help='Target hours to inspect and rectify this defect.'
    )
    description = fields.Text(string='Description')

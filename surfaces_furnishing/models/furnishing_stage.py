# -*- coding: utf-8 -*-
from odoo import models, fields


class FurnishingStage(models.Model):
    _name = 'furnishing.stage'
    _description = 'Furnishing Project Stage'
    _order = 'sequence, id'

    name = fields.Char(string='Stage Name', required=True, translate=True)
    sequence = fields.Integer(string='Sequence', default=10)
    fold = fields.Boolean(
        string='Folded in Kanban',
        help='This stage is folded in the kanban view when there are no records.'
    )
    stage_type = fields.Selection([
        ('inquiry', 'Inquiry & Scope'),
        ('survey', 'Site Survey'),
        ('design', '3D Design & Specs'),
        ('quotation', 'Quotation & Estimation'),
        ('sourcing', 'Material Approval & Sourcing'),
        ('installation', 'Site Installation'),
        ('handover', 'Handover & Snag Clearance'),
        ('completed', 'Completed / Warranty Active'),
        ('cancelled', 'Cancelled')
    ], string='Stage Category', default='inquiry', required=True)
    description = fields.Text(string='Description')

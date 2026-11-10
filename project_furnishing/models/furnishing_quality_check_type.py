# -*- coding: utf-8 -*-
from odoo import fields, models


class FurnishingQualityCheckType(models.Model):
    _name = 'furnishing.quality.check.type'
    _description = 'Furnishing Quality Check Type / Test Point'
    _order = 'sequence, name'

    name = fields.Char(
        string='Check / Test Name',
        required=True,
        translate=True,
        help='Name of the quality checkpoint, e.g. Dimensional Accuracy, Surface Finish, Wobble Test.'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    category = fields.Selection([
        ('dimensions', 'Dimensional & Tolerances'),
        ('surface', 'Surface Finish, Polish & Veneer'),
        ('joinery', 'Joinery & Stability (Wobble/Rigidity)'),
        ('hardware', 'Hardware, Hinges & Movement Reveals'),
        ('materials', 'Mixed Materials (Glass, Stone, Metal, Upholstery)'),
        ('safety', 'Moisture & Fire Safety'),
        ('packaging', 'Packaging, Site Protection & Room Tagging'),
        ('other', 'Other Inspection Points'),
    ], string='Category', default='dimensions', required=True)

    stage = fields.Selection([
        ('all', 'All Stages / General'),
        ('raw_material', 'Raw Material (Timber, Veneer, Boards, Hardware)'),
        ('in_process', 'In-Process (Joinery, Carcass, Framework)'),
        ('finishing', 'Finishing & Coating (Polish, Lacquer, Veneer Lamination)'),
        ('assembly', 'Fitting & Hardware Assembly (Hinges, Runners, Glass)'),
        ('pre_dispatch', 'Pre-Dispatch / Factory Sign-Off'),
    ], string='Applicable Stage', default='pre_dispatch', required=True,
       help='Stage where this check is normally performed.')

    standard_instructions = fields.Text(
        string='Standard Inspection Norms / Instructions',
        help='Tolerance specs, acceptable criteria, or guidance for inspectors.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )

# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FurnishingQualityCheckTemplate(models.Model):
    _name = 'furnishing.quality.check.template'
    _description = 'Furnishing Quality Check Template'
    _order = 'sequence, name'

    name = fields.Char(
        string='Template Name',
        required=True,
        translate=True,
        help='Name of the quality checklist template (e.g. Standard Joinery QC, Pre-Dispatch QC).'
    )
    active = fields.Boolean(
        string='Active',
        default=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    stage = fields.Selection([
        ('all', 'All Stages / General'),
        ('raw_material', 'Raw Material (Timber, Veneer, Boards, Hardware)'),
        ('in_process', 'In-Process (Joinery, Carcass, Framework)'),
        ('finishing', 'Finishing & Coating (Polish, Lacquer, Veneer Lamination)'),
        ('assembly', 'Fitting & Hardware Assembly (Hinges, Runners, Glass)'),
        ('pre_dispatch', 'Pre-Dispatch / Factory Sign-Off'),
    ], string='Applicable Stage', default='all', required=True,
       help='Stage where this checklist template is typically applied.')
    description = fields.Text(
        string='Description',
        help='Scope, guidelines, or instructions for this checklist template.'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    line_ids = fields.One2many(
        'furnishing.quality.check.template.line',
        'template_id',
        string='Checklist Checkpoints',
        copy=True
    )
    checkpoint_count = fields.Integer(
        string='Total Checkpoints',
        compute='_compute_checkpoint_count',
        store=True
    )

    @api.depends('line_ids')
    def _compute_checkpoint_count(self):
        for record in self:
            record.checkpoint_count = len(record.line_ids)


class FurnishingQualityCheckTemplateLine(models.Model):
    _name = 'furnishing.quality.check.template.line'
    _description = 'Furnishing Quality Check Template Line'
    _order = 'sequence, id'

    template_id = fields.Many2one(
        'furnishing.quality.check.template',
        string='Template',
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    check_type_id = fields.Many2one(
        'furnishing.quality.check.type',
        string='Checkpoint / Test',
        required=True
    )
    category = fields.Selection(
        related='check_type_id.category',
        string='Category',
        readonly=True,
        store=True
    )
    instructions = fields.Text(
        string='Standard Norms & Instructions',
        related='check_type_id.standard_instructions',
        readonly=True
    )

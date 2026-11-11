# -*- coding: utf-8 -*-
from odoo import api, models, fields


class ProjectMeasurementType(models.Model):
    _name = 'project.measurement.type'
    _description = 'Measurement Type'
    _order = 'sequence, name'

    name = fields.Char(string='Measurement Type', required=True, translate=True)
    code = fields.Char(string='Code', size=20)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
    measure_by = fields.Selection([
        ('area_lw', 'Area (Length x Width)'),
        ('area_lh', 'Area (Length x Height)'),
        ('linear', 'Linear (Length)'),
        ('count', 'Pieces (Count)'),
    ], string='Measured By', default='area_lw', required=True,
        help='How the quantity of a surveyed item of this type is calculated. '
             'Dimensions are entered in meters. The quantity is always multiplied by the item count.')
    quantity_unit = fields.Char(string='Unit', compute='_compute_quantity_unit')

    @api.depends('measure_by')
    def _compute_quantity_unit(self):
        units = {'area_lw': 'm\u00b2', 'area_lh': 'm\u00b2', 'linear': 'm', 'count': 'pcs'}
        for rec in self:
            rec.quantity_unit = units.get(rec.measure_by, '')

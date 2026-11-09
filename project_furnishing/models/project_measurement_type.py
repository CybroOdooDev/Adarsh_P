# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectMeasurementType(models.Model):
    _name = 'project.measurement.type'
    _description = 'Measurement Type'
    _order = 'sequence, name'

    name = fields.Char(string='Measurement Type', required=True, translate=True)
    code = fields.Char(string='Code', size=20)
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)

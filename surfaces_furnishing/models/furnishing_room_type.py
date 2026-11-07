# -*- coding: utf-8 -*-
from odoo import models, fields


class FurnishingRoomType(models.Model):
    _name = 'furnishing.room.type'
    _description = 'Room and Zone Preset'
    _order = 'name'

    name = fields.Char(string='Room / Zone Name', required=True, translate=True)
    code = fields.Char(string='Code', size=10)
    category = fields.Selection([
        ('residential', 'Residential'),
        ('commercial', 'Commercial / Office'),
        ('hospitality', 'Hospitality'),
        ('outdoor', 'Outdoor / Landscape')
    ], string='Space Category', default='residential', required=True)
    default_waste_percentage = fields.Float(
        string='Default Waste %',
        default=10.0,
        help='Default cutting and wastage percentage for this zone (e.g. 10% for flooring/fabric).'
    )
    description = fields.Text(string='Description')

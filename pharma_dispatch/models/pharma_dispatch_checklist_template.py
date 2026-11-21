# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
from odoo import api, fields, models
from odoo.exceptions import ValidationError

SECTIONS = [
    ('vehicle', 'Vehicle Condition'),
    ('temperature', 'Temperature'),
    ('other', 'Other'),
]
CHECK_TYPES = [
    ('yes_no', 'Yes / No'),
    ('numeric', 'Reading'),
    ('text', 'Text'),
]
SEVERITIES = [
    ('critical', 'Critical'),
    ('major', 'Major'),
    ('minor', 'Minor'),
]
APPLIES_TO = [
    ('all', 'All Shipments'),
    ('cold_chain', 'Temperature Controlled Only'),
    ('ambient', 'Ambient Only'),
]
LIMIT_SOURCES = [
    ('shipment', 'Shipment Temperature Range'),
    ('fixed', 'Fixed Limits'),
]


class PharmaDispatchChecklistTemplate(models.Model):
    """Pre-loading checklist: the checks the dispatch officer makes on the
    vehicle before goods are loaded."""
    _name = 'pharma.dispatch.checklist.template'
    _description = 'Dispatch Checklist Template'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company',
                                 help='Leave empty to use it in every company.')
    line_ids = fields.One2many('pharma.dispatch.checklist.template.line',
                               'template_id', string='Checks', copy=True)
    temperature_controlled = fields.Boolean(
        string='Temperature Controlled',
        help='Shipments created with this template are temperature controlled '
             'with the range below.')
    temp_min = fields.Float(string='Min (°C)', digits=(4, 1), default=2.0)
    temp_max = fields.Float(string='Max (°C)', digits=(4, 1), default=8.0)
    high_security = fields.Boolean(
        string='High Security',
        help='Shipments created with this template need a transporter whose '
             'contract covers high-security consignments.')

    @api.constrains('temperature_controlled', 'temp_min', 'temp_max')
    def _check_temp_range(self):
        for template in self:
            if template.temperature_controlled and template.temp_min >= template.temp_max:
                raise ValidationError(self.env._(
                    'The minimum temperature of %s must be below the maximum.',
                    template.name))


class PharmaDispatchChecklistTemplateLine(models.Model):
    _name = 'pharma.dispatch.checklist.template.line'
    _description = 'Dispatch Checklist Template Check'
    _order = 'template_id, sequence, id'

    template_id = fields.Many2one('pharma.dispatch.checklist.template',
                                  required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    section = fields.Selection(SECTIONS, required=True, default='vehicle')
    name = fields.Char(string='Check', required=True, translate=True)
    instructions = fields.Text(translate=True)
    check_type = fields.Selection(CHECK_TYPES, string='Type', required=True,
                                  default='yes_no')
    severity = fields.Selection(
        SEVERITIES, required=True, default='major',
        help='Critical: a failure rejects the vehicle. '
             'Major: a failure needs a manager override to load. '
             'Minor: a failure is recorded but does not stop loading.')
    applies_to = fields.Selection(APPLIES_TO, string='Applies To',
                                  required=True, default='all')
    limit_source = fields.Selection(
        LIMIT_SOURCES, string='Limits', default='shipment',
        help='Readings pass when they are within these limits.')
    min_value = fields.Float(string='Min', digits=(6, 1))
    max_value = fields.Float(string='Max', digits=(6, 1))
    unit = fields.Char(default='°C')
    photo_required = fields.Boolean(string='Photo Required')
    log_temperature = fields.Boolean(
        string='Add to Temperature Log',
        help='Copy the reading to the shipment temperature log when the '
             'checklist passes (pre-loading readings of the cargo space).')

    @api.constrains('check_type', 'limit_source', 'min_value', 'max_value')
    def _check_limits(self):
        for line in self:
            if (line.check_type == 'numeric' and line.limit_source == 'fixed'
                    and line.min_value > line.max_value):
                raise ValidationError(self.env._(
                    'The minimum of "%s" is above its maximum.', line.name))

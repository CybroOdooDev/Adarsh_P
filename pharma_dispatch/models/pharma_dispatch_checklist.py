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
from odoo.exceptions import UserError
from odoo.tools import float_compare

from .pharma_dispatch_checklist_template import CHECK_TYPES, SECTIONS, SEVERITIES


class PharmaDispatchChecklist(models.Model):
    """Pre-loading check of one vehicle for one shipment.

    A failed critical check rejects the vehicle: the shipment needs another
    vehicle and a new checklist. A failed major check can be overridden by
    an inventory manager with a reason. Minor failures are only recorded.
    """
    _name = 'pharma.dispatch.checklist'
    _description = 'Dispatch Checklist'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(required=True, copy=False, readonly=True, default='New')
    shipment_id = fields.Many2one('pharma.shipment', string='Shipment',
                                  required=True, readonly=True, index=True,
                                  ondelete='cascade')
    company_id = fields.Many2one(related='shipment_id.company_id', store=True)
    template_id = fields.Many2one('pharma.dispatch.checklist.template',
                                  string='Template', readonly=True)
    vehicle_number = fields.Char(string='Vehicle Number', required=True,
                                 tracking=True)
    temperature_controlled = fields.Boolean(readonly=True)
    temp_min = fields.Float(string='Min (°C)', digits=(4, 1), readonly=True)
    temp_max = fields.Float(string='Max (°C)', digits=(4, 1), readonly=True)
    state = fields.Selection([
        ('in_progress', 'In Progress'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
        ('rejected', 'Vehicle Rejected'),
    ], default='in_progress', required=True, readonly=True, tracking=True,
        copy=False)
    line_ids = fields.One2many('pharma.dispatch.checklist.line', 'checklist_id',
                               string='Checks')
    checked_by = fields.Many2one('res.users', readonly=True, copy=False)
    checked_on = fields.Datetime(readonly=True, copy=False)
    failed_critical_count = fields.Integer(compute='_compute_failures')
    failed_major_count = fields.Integer(compute='_compute_failures')
    failed_minor_count = fields.Integer(compute='_compute_failures')
    overridden = fields.Boolean(readonly=True, copy=False, tracking=True)
    override_reason = fields.Text(copy=False)
    overridden_by = fields.Many2one('res.users', readonly=True, copy=False)

    @api.depends('line_ids.result', 'line_ids.severity')
    def _compute_failures(self):
        for checklist in self:
            failed = checklist.line_ids.filtered(lambda l: l.result == 'fail')
            checklist.failed_critical_count = len(
                failed.filtered(lambda l: l.severity == 'critical'))
            checklist.failed_major_count = len(
                failed.filtered(lambda l: l.severity == 'major'))
            checklist.failed_minor_count = len(
                failed.filtered(lambda l: l.severity == 'minor'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pharma.dispatch.checklist') or 'New'
        return super().create(vals_list)

    @api.model
    def _prepare_lines(self, template, shipment):
        cold = shipment.temperature_controlled
        lines = []
        for tline in template.line_ids:
            if (tline.applies_to == 'cold_chain' and not cold) or                     (tline.applies_to == 'ambient' and cold):
                continue
            if tline.check_type == 'numeric' and tline.limit_source == 'shipment':
                if not cold:
                    continue  # no range to check against
                min_value, max_value = shipment.temp_min, shipment.temp_max
            else:
                min_value, max_value = tline.min_value, tline.max_value
            lines.append(fields.Command.create({
                'sequence': tline.sequence,
                'section': tline.section,
                'name': tline.name,
                'instructions': tline.instructions,
                'check_type': tline.check_type,
                'severity': tline.severity,
                'min_value': min_value,
                'max_value': max_value,
                'unit': tline.unit,
                'photo_required': tline.photo_required,
                'log_temperature': tline.log_temperature,
            }))
        return lines

    def action_complete(self):
        """Close the checklist: every check answered, then pass or fail."""
        for checklist in self:
            if checklist.state != 'in_progress':
                raise UserError(self.env._('%s is already completed.', checklist.name))
            pending = checklist.line_ids.filtered(lambda l: l.result == 'pending')
            if pending:
                raise UserError(self.env._(
                    'Answer every check of %(name)s first:\n%(checks)s',
                    name=checklist.name,
                    checks='\n'.join(pending.mapped('name'))))
            missing_photo = checklist.line_ids.filtered(
                lambda l: l.photo_required and not l.photo)
            if missing_photo:
                raise UserError(self.env._(
                    'Add the photo required for:\n%s',
                    '\n'.join(missing_photo.mapped('name'))))
            if checklist.failed_critical_count:
                state = 'rejected'
            elif checklist.failed_major_count:
                state = 'failed'
            else:
                state = 'passed'
            checklist.write({'state': state, 'checked_by': self.env.user.id,
                             'checked_on': fields.Datetime.now()})
            if state == 'passed':
                checklist._log_temperatures()
            elif state == 'rejected':
                checklist.shipment_id.message_post(body=self.env._(
                    'Vehicle %(vehicle)s rejected by checklist %(name)s. '
                    'Arrange another vehicle and start a new checklist.',
                    vehicle=checklist.vehicle_number, name=checklist.name))

    def action_override(self):
        """Accept a vehicle with failed major checks (no critical failure)."""
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise UserError(self.env._('Only inventory managers can override a failed checklist.'))
        for checklist in self:
            if checklist.state != 'failed':
                raise UserError(self.env._(
                    'Only checklists failed on major checks can be overridden.'))
            if not checklist.override_reason:
                raise UserError(self.env._('Enter the reason for the override.'))
            checklist.write({'state': 'passed', 'overridden': True,
                             'overridden_by': self.env.user.id})
            checklist._log_temperatures()

    def _log_temperatures(self):
        self.ensure_one()
        readings = self.line_ids.filtered(
            lambda l: l.log_temperature and l.check_type == 'numeric')
        if not readings or not self.shipment_id.temperature_controlled:
            return
        self.env['pharma.shipment.temperature'].create([{
            'shipment_id': self.shipment_id.id,
            'reading_time': self.checked_on,
            'temperature': line.value_numeric,
            'source': 'manual',
            'location': self.env._('Pre-loading: %s', line.name),
        } for line in readings])


class PharmaDispatchChecklistLine(models.Model):
    _name = 'pharma.dispatch.checklist.line'
    _description = 'Dispatch Checklist Check'
    _order = 'checklist_id, sequence, id'

    checklist_id = fields.Many2one('pharma.dispatch.checklist', required=True,
                                   index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    section = fields.Selection(SECTIONS, required=True, readonly=True)
    name = fields.Char(string='Check', required=True, readonly=True)
    instructions = fields.Text(readonly=True)
    check_type = fields.Selection(CHECK_TYPES, string='Type', required=True,
                                  readonly=True)
    severity = fields.Selection(SEVERITIES, required=True, readonly=True)
    min_value = fields.Float(string='Min', digits=(6, 1), readonly=True)
    max_value = fields.Float(string='Max', digits=(6, 1), readonly=True)
    unit = fields.Char(readonly=True)
    photo_required = fields.Boolean(readonly=True)
    log_temperature = fields.Boolean(readonly=True)

    answer = fields.Selection([('yes', 'Yes'), ('no', 'No')], string='Answer')
    value_numeric = fields.Float(string='Reading', digits=(6, 1))
    value_entered = fields.Boolean(
        help='Set once a reading is typed, so 0.0 counts as an answer.')
    value_text = fields.Char(string='Value')
    photo = fields.Image(max_width=1920, max_height=1920, attachment=True)
    remarks = fields.Char()
    result = fields.Selection([
        ('pending', 'Pending'),
        ('pass', 'Pass'),
        ('fail', 'Fail'),
    ], compute='_compute_result', store=True)

    @api.onchange('value_numeric')
    def _onchange_value_numeric(self):
        self.value_entered = True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'value_numeric' in vals:
                vals.setdefault('value_entered', True)
        return super().create(vals_list)

    def write(self, vals):
        if 'value_numeric' in vals and 'value_entered' not in vals:
            vals['value_entered'] = True
        return super().write(vals)

    @api.depends('check_type', 'answer', 'value_numeric', 'value_entered',
                 'value_text', 'min_value', 'max_value')
    def _compute_result(self):
        for line in self:
            if line.check_type == 'yes_no':
                line.result = {'yes': 'pass', 'no': 'fail'}.get(line.answer, 'pending')
            elif line.check_type == 'numeric':
                if not line.value_entered:
                    line.result = 'pending'
                elif (float_compare(line.value_numeric, line.min_value, 1) < 0
                      or float_compare(line.value_numeric, line.max_value, 1) > 0):
                    line.result = 'fail'
                else:
                    line.result = 'pass'
            else:
                line.result = 'pass' if (line.value_text or '').strip() else 'pending'

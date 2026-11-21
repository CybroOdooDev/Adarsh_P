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
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

# Points a GDP quality agreement with a carrier must cover before the
# contract can be activated.
QUALITY_POINTS = {
    'qa_temperature_control': 'Temperature control and monitoring during transit',
    'qa_trained_drivers': 'Qualified drivers trained in GDP and product handling',
    'qa_vehicle_cleaning': 'Vehicle cleaning and pest control',
    'qa_no_subcontracting': 'No subcontracting without written approval',
    'qa_incident_reporting': 'Reporting of incidents, delays and excursions',
    'qa_right_to_audit': 'Right to audit the transporter',
}


class PharmaTransportContract(models.Model):
    """Contract and GDP quality agreement with a transport contractor.

    A transporter can only be used on a shipment while it has an active
    contract covering the dispatch date and the kind of consignment.
    """
    _name = 'pharma.transport.contract'
    _description = 'Transport Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default='New', tracking=True)
    transporter_id = fields.Many2one(
        'res.partner', string='Transporter', required=True, index=True,
        tracking=True, domain="[('is_company', '=', True)]",
        ondelete='restrict')
    partner_reference = fields.Char(
        string="Transporter's Reference",
        help='Contract number used by the transporter.')
    company_id = fields.Many2one('res.company', required=True,
                                 default=lambda self: self.env.company)
    responsible_id = fields.Many2one(
        'res.users', string='Responsible', tracking=True,
        default=lambda self: self.env.user,
        help='Receives the renewal reminder.')
    date_start = fields.Date(string='Valid From', required=True, tracking=True,
                             default=fields.Date.context_today)
    date_end = fields.Date(string='Valid Until', required=True, tracking=True)
    reminder_days = fields.Integer(
        string='Remind Before (days)', default=30,
        help='A renewal activity is scheduled this many days before expiry.')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('terminated', 'Terminated'),
    ], string='Status', default='draft', required=True, readonly=True,
        copy=False, tracking=True)

    # Scope
    service_ambient = fields.Boolean(string='Ambient', default=True, tracking=True,
                                     help='Shipments that are not temperature controlled.')
    service_cold_chain = fields.Boolean(string='Cold Chain', tracking=True,
                                        help='Temperature-controlled shipments.')
    service_high_security = fields.Boolean(
        string='High Security', tracking=True,
        help='Controlled substances and high-value consignments.')
    coverage = fields.Text(string='Routes / Regions Covered')

    # Quality agreement
    qa_temperature_control = fields.Boolean(string=QUALITY_POINTS['qa_temperature_control'])
    qa_trained_drivers = fields.Boolean(string=QUALITY_POINTS['qa_trained_drivers'])
    qa_vehicle_cleaning = fields.Boolean(string=QUALITY_POINTS['qa_vehicle_cleaning'])
    qa_no_subcontracting = fields.Boolean(string=QUALITY_POINTS['qa_no_subcontracting'])
    qa_incident_reporting = fields.Boolean(string=QUALITY_POINTS['qa_incident_reporting'])
    incident_reporting_hours = fields.Integer(
        string='Report Within (hours)', default=24,
        help='Time the transporter has to report an incident or excursion.')
    qa_right_to_audit = fields.Boolean(string=QUALITY_POINTS['qa_right_to_audit'])
    document_ids = fields.Many2many(
        'ir.attachment', 'pharma_transport_contract_attachment_rel',
        'contract_id', 'attachment_id', string='Signed Contract',
        help='Signed contract and quality agreement.')
    termination_reason = fields.Text(readonly=True, copy=False)
    note = fields.Html(string='Notes')

    shipment_count = fields.Integer(compute='_compute_shipment_count')
    days_to_expiry = fields.Integer(compute='_compute_days_to_expiry')

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for contract in self:
            if contract.date_end < contract.date_start:
                raise ValidationError(self.env._(
                    '%s ends before it starts.', contract.name))

    def _compute_shipment_count(self):
        groups = self.env['pharma.shipment']._read_group(
            [('transport_contract_id', 'in', self.ids)],
            ['transport_contract_id'], ['__count'])
        counts = {contract.id: count for contract, count in groups}
        for contract in self:
            contract.shipment_count = counts.get(contract.id, 0)

    @api.depends('date_end')
    def _compute_days_to_expiry(self):
        today = fields.Date.context_today(self)
        for contract in self:
            contract.days_to_expiry = (contract.date_end - today).days \
                if contract.date_end else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'pharma.transport.contract') or 'New'
        return super().create(vals_list)

    # Actions -----------------------------------------------------------------

    def action_activate(self):
        today = fields.Date.context_today(self)
        for contract in self:
            if contract.state != 'draft':
                raise UserError(self.env._('Only draft contracts can be activated.'))
            if contract.date_end < today:
                raise UserError(self.env._('%s has already ended.', contract.name))
            if not (contract.service_ambient or contract.service_cold_chain
                    or contract.service_high_security):
                raise UserError(self.env._('Select at least one service the contract covers.'))
            missing = [label for fname, label in QUALITY_POINTS.items() if not contract[fname]]
            if missing:
                raise UserError(self.env._(
                    'The quality agreement of %(name)s does not yet cover:\n%(points)s',
                    name=contract.name, points='\n'.join('- ' + m for m in missing)))
            if not contract.document_ids:
                raise UserError(self.env._('Attach the signed contract first.'))
            overlap = self.search([
                ('id', '!=', contract.id),
                ('transporter_id', '=', contract.transporter_id.id),
                ('company_id', '=', contract.company_id.id),
                ('state', '=', 'active'),
                ('date_start', '<=', contract.date_end),
                ('date_end', '>=', contract.date_start),
            ], limit=1)
            if overlap:
                raise UserError(self.env._(
                    '%(transporter)s already has an active contract (%(other)s) for '
                    'these dates. Terminate it or adjust the dates.',
                    transporter=contract.transporter_id.name, other=overlap.name))
        self.write({'state': 'active'})

    def action_terminate(self):
        if self.filtered(lambda c: c.state != 'active'):
            raise UserError(self.env._('Only active contracts can be terminated.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._('Terminate Contract'),
            'res_model': 'pharma.transport.contract.terminate',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_contract_ids': self.ids},
        }

    def action_reset_to_draft(self):
        self.filtered(lambda c: c.state in ('expired', 'terminated')).write({
            'state': 'draft', 'termination_reason': False})

    def action_view_shipments(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pharma_dispatch.pharma_shipment_action')
        action['domain'] = [('transport_contract_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    # Use on shipments ------------------------------------------------------

    def _covers(self, shipment):
        """Whether this contract covers the kind of consignment."""
        self.ensure_one()
        if shipment.high_security and not self.service_high_security:
            return False
        if shipment.temperature_controlled:
            return self.service_cold_chain
        return self.service_ambient or self.service_high_security

    @api.model
    def _find_active(self, transporter, company, day):
        return self.search([
            ('transporter_id', '=', transporter.commercial_partner_id.id),
            ('company_id', '=', company.id),
            ('state', '=', 'active'),
            ('date_start', '<=', day),
            ('date_end', '>=', day),
        ], order='date_end desc', limit=1)

    # Scheduled job -----------------------------------------------------------

    @api.model
    def _cron_crew_qualification(self):
        """Remind the contract owner when a driver's licence, GDP training or
        background check runs out within 30 days."""
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=30)
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        summary = self.env._('Driver qualification expiring')
        people = self.env['res.partner'].search([
            ('transport_role', '!=', False),
            '|', '|',
            '&', ('driving_licence_valid_until', '!=', False), ('driving_licence_valid_until', '<=', soon),
            '&', ('gdp_training_valid_until', '!=', False), ('gdp_training_valid_until', '<=', soon),
            '&', ('background_check_valid_until', '!=', False), ('background_check_valid_until', '<=', soon),
        ])
        for person in people:
            if person.activity_ids.filtered(
                    lambda a: a.activity_type_id == activity_type and a.summary == summary):
                continue
            contract = self._find_active(person.commercial_partner_id, self.env.company, today)
            dates = [d for d in (person.driving_licence_valid_until, person.gdp_training_valid_until,
                                 person.background_check_valid_until) if d and d <= soon]
            person.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=min(dates), summary=summary,
                note=self.env._('Ask %(transporter)s for renewed documents of %(person)s.',
                                transporter=person.commercial_partner_id.name, person=person.name),
                user_id=(contract.responsible_id or self.env.user).id)

    @api.model
    def _cron_contract_validity(self):
        """Expire ended contracts and remind the responsible person before
        a contract runs out."""
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('date_end', '<', today)]).write(
            {'state': 'expired'})
        self._cron_crew_qualification()
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        for contract in self.search([('state', '=', 'active')]):
            if contract.date_end - timedelta(days=contract.reminder_days) > today:
                continue
            if contract.activity_ids.filtered(lambda a: a.activity_type_id == activity_type):
                continue
            contract.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=contract.date_end,
                summary=self.env._('Renew transport contract'),
                note=self.env._('%(name)s with %(transporter)s expires on %(date)s.',
                                name=contract.name,
                                transporter=contract.transporter_id.name,
                                date=contract.date_end),
                user_id=(contract.responsible_id or self.env.user).id)

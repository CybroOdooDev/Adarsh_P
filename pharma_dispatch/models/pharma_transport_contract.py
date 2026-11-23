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


class PharmaTransportContract(models.Model):
    """Contract with a transport contractor.

    A transporter can only be used on a shipment while it has an active
    contract covering the dispatch date and the kind of consignment.
    """
    _name = 'pharma.transport.contract'
    _description = 'Transport Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_end desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                       readonly=True, default='New', tracking=True)
    active = fields.Boolean(default=True,
                            help='Expired contracts are archived.')
    transporter_id = fields.Many2one(
        'res.partner', string='Transporter', required=True, index=True,
        tracking=True, domain="[('parent_id', '=', False)]",
        help='Transport contractor: a top-level contact, not a person under a company.',
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

    document_ids = fields.Many2many(
        'ir.attachment', 'pharma_transport_contract_attachment_rel',
        'contract_id', 'attachment_id', string='Signed Contract',
        help='Signed contract with the transporter.')
    termination_reason = fields.Text(readonly=True, copy=False)
    note = fields.Html(string='Notes')

    shipment_count = fields.Integer(compute='_compute_shipment_count')
    days_to_expiry = fields.Integer(compute='_compute_days_to_expiry')

    # Renewal
    renewed_from_id = fields.Many2one(
        'pharma.transport.contract', string='Renewal Of', readonly=True,
        copy=False, index=True, ondelete='set null',
        help='Contract this one renews.')
    renewal_ids = fields.One2many(
        'pharma.transport.contract', 'renewed_from_id', string='Renewals',
        context={'active_test': False})
    renewal_id = fields.Many2one(
        'pharma.transport.contract', string='Renewed By',
        compute='_compute_renewal_id',
        help='Contract that renews this one.')

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

    @api.depends('renewal_ids')
    def _compute_renewal_id(self):
        for contract in self:
            contract.renewal_id = contract.renewal_ids.filtered(
                lambda c: c.state != 'terminated').sorted('id')[-1:]

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
        self.renewed_from_id._close_renewal_reminders()

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

    def _prepare_renewal_vals(self):
        """Values of the draft contract renewing this one: the next term of
        the same length and the same transporter and scope. The signed
        contract of the new term is still to be attached."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        date_start = max(self.date_end + timedelta(days=1), today)
        return {
            'transporter_id': self.transporter_id.id,
            'company_id': self.company_id.id,
            'responsible_id': self.responsible_id.id,
            'date_start': date_start,
            'date_end': date_start + (self.date_end - self.date_start),
            'reminder_days': self.reminder_days,
            'service_ambient': self.service_ambient,
            'service_cold_chain': self.service_cold_chain,
            'service_high_security': self.service_high_security,
            'coverage': self.coverage,
            'renewed_from_id': self.id,
        }

    def action_renew(self):
        """Create the draft contract for the next term and open it."""
        self.ensure_one()
        if self.state not in ('active', 'expired', 'terminated'):
            raise UserError(self.env._('Only active, expired or terminated contracts can be renewed.'))
        if self.renewal_id:
            raise UserError(self.env._(
                '%(name)s is already renewed by %(renewal)s.',
                name=self.name, renewal=self.renewal_id.name))
        renewal = self.create(self._prepare_renewal_vals())
        self.message_post(body=self.env._('Renewal %s created.', renewal.name))
        renewal.message_post(body=self.env._('Renewal of %s.', self.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': renewal.id,
            'view_mode': 'form',
        }

    def _close_renewal_reminders(self):
        """Mark the renewal reminders of these contracts as done."""
        summary = self.env._('Renew transport contract')
        self.activity_ids.filtered(lambda a: a.summary == summary).action_feedback(
            feedback=self.env._('Contract renewed.'))

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
        """Remind the contract owner when a driver's licence or background
        check runs out within 30 days."""
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=30)
        activity_type = self.env.ref('mail.mail_activity_data_todo')
        summary = self.env._('Driver qualification expiring')
        people = self.env['res.partner'].search([
            ('transport_role', '!=', False),
            '|',
            '&', ('driving_licence_valid_until', '!=', False), ('driving_licence_valid_until', '<=', soon),
            '&', ('background_check_valid_until', '!=', False), ('background_check_valid_until', '<=', soon),
        ])
        for person in people:
            if person.activity_ids.filtered(
                    lambda a: a.activity_type_id == activity_type and a.summary == summary):
                continue
            contract = self._find_active(person.commercial_partner_id, self.env.company, today)
            dates = [d for d in (person.driving_licence_valid_until,
                                 person.background_check_valid_until) if d and d <= soon]
            person.activity_schedule(
                'mail.mail_activity_data_todo', date_deadline=min(dates), summary=summary,
                note=self.env._('Ask %(transporter)s for renewed documents of %(person)s.',
                                transporter=person.commercial_partner_id.name, person=person.name),
                user_id=(contract.responsible_id or self.env.user).id)

    @api.model
    def _cron_contract_validity(self):
        """Expire and archive ended contracts, and remind the responsible
        person before a contract that is not renewed yet runs out."""
        today = fields.Date.context_today(self)
        self.search([('state', '=', 'active'), ('date_end', '<', today)]).write(
            {'state': 'expired', 'active': False})
        self._cron_crew_qualification()
        summary = self.env._('Renew transport contract')
        for contract in self.search([('state', '=', 'active')]):
            if contract.date_end - timedelta(days=contract.reminder_days) > today:
                continue
            if contract.renewal_id or contract.activity_ids.filtered(
                    lambda a: a.summary == summary):
                continue
            contract.activity_schedule(
                'mail.mail_activity_data_todo',
                date_deadline=contract.date_end,
                summary=summary,
                note=self.env._('%(name)s with %(transporter)s expires on %(date)s.',
                                name=contract.name,
                                transporter=contract.transporter_id.name,
                                date=contract.date_end),
                user_id=(contract.responsible_id or self.env.user).id)

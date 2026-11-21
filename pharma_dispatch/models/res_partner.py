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


class ResPartner(models.Model):
    _inherit = 'res.partner'

    pharma_dl_20b = fields.Char(
        string='Drug Licence (20B / 20)',
        help='Wholesale (or retail) drug licence number for drugs other than '
             'those in Schedules C, C(1) and X. Printed on delivery challans.')
    pharma_dl_21b = fields.Char(
        string='Drug Licence (21B / 21)',
        help='Wholesale (or retail) drug licence number for drugs in '
             'Schedules C and C(1), e.g. vaccines and sera.')
    pharma_dl_valid_until = fields.Date(string='Drug Licence Valid Until')
    transport_contract_ids = fields.One2many(
        'pharma.transport.contract', 'transporter_id', string='Transport Contracts')
    transport_contract_count = fields.Integer(compute='_compute_transport_contract_count')

    # Transport personnel qualification (drivers and escorts of a transporter)
    transport_role = fields.Selection([
        ('driver', 'Driver'),
        ('escort', 'Escort / Co-driver'),
    ], string='Transport Role', tracking=True,
        help='Set for the people a transporter assigns to your shipments.')
    driving_licence_number = fields.Char(string='Driving Licence No.', tracking=True)
    driving_licence_class = fields.Char(
        string='Licence Class', help='Vehicle classes the licence covers, e.g. LMV, HGMV, transport.')
    driving_licence_valid_until = fields.Date(string='Licence Valid Until', tracking=True)
    gdp_training_date = fields.Date(string='GDP Training Date', tracking=True)
    gdp_training_valid_until = fields.Date(
        string='GDP Training Valid Until', tracking=True,
        help='Good Distribution Practice training: product handling, temperature '
             'control, security and incident reporting.')
    cold_chain_trained = fields.Boolean(
        string='Cold Chain Trained', tracking=True,
        help='Trained to handle temperature-controlled consignments '
             '(reefer operation, door-open discipline, logger handling).')
    background_check_date = fields.Date(string='Background Check Date', tracking=True)
    background_check_valid_until = fields.Date(
        string='Background Check Valid Until', tracking=True,
        help='Police or background verification. Required for high-security consignments.')
    transport_document_ids = fields.Many2many(
        'ir.attachment', 'res_partner_transport_doc_rel', 'partner_id', 'attachment_id',
        string='Qualification Documents',
        help='Copies of the licence, training certificates and verification.')
    transport_qualification_state = fields.Selection([
        ('qualified', 'Qualified'),
        ('expiring', 'Expiring Soon'),
        ('not_qualified', 'Not Qualified'),
    ], compute='_compute_transport_qualification', string='Qualification')
    transport_qualification_issues = fields.Text(
        compute='_compute_transport_qualification', string='Qualification Issues')

    QUALIFICATION_WARNING_DAYS = 30

    @api.depends('transport_role', 'driving_licence_number', 'driving_licence_valid_until',
                 'gdp_training_valid_until')
    def _compute_transport_qualification(self):
        today = fields.Date.context_today(self)
        soon = today + timedelta(days=self.QUALIFICATION_WARNING_DAYS)
        for partner in self:
            if not partner.transport_role:
                partner.transport_qualification_state = False
                partner.transport_qualification_issues = False
                continue
            issues = partner._pharma_crew_issues(today)
            partner.transport_qualification_issues = '\n'.join(issues) or False
            if issues:
                partner.transport_qualification_state = 'not_qualified'
            elif partner._pharma_crew_issues(soon):
                partner.transport_qualification_state = 'expiring'
            else:
                partner.transport_qualification_state = 'qualified'

    def _pharma_crew_issues(self, until, cold_chain=False, high_security=False):
        """Reasons this person cannot crew a consignment that runs until the
        given date (empty list when qualified)."""
        self.ensure_one()
        _ = self.env._
        issues = []
        if not self.transport_role:
            return [_('not registered as a driver or escort')]
        if self.transport_role == 'driver':
            if not self.driving_licence_number:
                issues.append(_('no driving licence recorded'))
            elif not self.driving_licence_valid_until or self.driving_licence_valid_until < until:
                issues.append(_('driving licence expired or expiring before delivery'))
        if not self.gdp_training_valid_until or self.gdp_training_valid_until < until:
            issues.append(_('GDP training missing or expired'))
        if cold_chain and not self.cold_chain_trained:
            issues.append(_('not cold-chain trained'))
        if high_security and (not self.background_check_valid_until
                              or self.background_check_valid_until < until):
            issues.append(_('background check missing or expired'))
        return issues

    def _compute_transport_contract_count(self):
        for partner in self:
            partner.transport_contract_count = len(partner.transport_contract_ids)

    def action_view_transport_contracts(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'pharma_dispatch.pharma_transport_contract_action')
        action['domain'] = [('transporter_id', '=', self.id)]
        action['context'] = {'default_transporter_id': self.id}
        return action

    def _pharma_gst_state_code(self):
        """Two-digit GST state code: the state's TIN when the Indian
        localisation is installed, otherwise the first two digits of the GSTIN."""
        self.ensure_one()
        state = self.state_id
        if state and 'l10n_in_tin' in state._fields and state.l10n_in_tin:
            return state.l10n_in_tin
        vat = (self.vat or '').strip()
        return vat[:2] if len(vat) == 15 and vat[:2].isdigit() else ''

# -*- coding: utf-8 -*-
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

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

class PharmaIPQCResult(models.Model):
    """In-Process Quality Control result recorded at a specific BMR step."""
    _name = 'pharma.ipqc.result'
    _description = 'IPQC In-Process Quality Check'
    _inherit = ['mail.thread']
    _rec_name = 'parameter'
    _order = 'bmr_id, id'

    bmr_id = fields.Many2one(
        comodel_name='pharma.bmr',
        string='BMR',
        required=True,
        ondelete='cascade',
        index=True,
            help='Specifies the BMR for this record.',
    )

    step_id = fields.Many2one(
        comodel_name='pharma.bmr.step',
        string='BMR Step',
        domain="[('bmr_id', '=', bmr_id), ('operator_signed_on', '!=', False)]",
        ondelete='set null',
            help='Specifies the BMR Step for this record.',
    )

    parameter = fields.Char(
        string='Parameter',
        required=True,
        help='What is being checked, e.g. tablet hardness, weight.',
    )

    expected_min = fields.Float(
        string='Expected Min',
        help='Acceptable minimum for this in-process check.',
    )

    expected_max = fields.Float(
        string='Expected Max',
        help='Acceptable maximum for this in-process check.',
    )

    actual_value = fields.Float(
        string='Actual Value',
        help='Value recorded by the analyst.',
    )

    result = fields.Selection(
        selection=[
            ('pass', 'Pass'),
            ('fail', 'Fail'),
        ],
        string='Result',
        copy=False,
        compute='_compute_result',
        store=True,
        tracking=True,
            help='Specifies the Result for this record.',
    )

    @api.depends('actual_value', 'expected_min', 'expected_max')
    def _compute_result(self):
        for rec in self:
            if rec.actual_value:
                if rec.expected_min <= rec.actual_value <= rec.expected_max:
                    rec.result = 'pass'
                else:
                    rec.result = 'fail'
            else:
                rec.result = False

    signed_by = fields.Many2one(
        comodel_name='res.users',
        string='Signed By',
        copy=False,
        readonly=True,
            help='Specifies the Signed By for this record.',
    )

    signed_on = fields.Datetime(
        string='Signed On',
        copy=False,
        readonly=True,
            help='Specifies the Signed On for this record.',
    )

    deviation_id = fields.Many2one(
        comodel_name='pharma.deviation',
        string='Linked Deviation',
        copy=False,
        readonly=True,
        help='Deviation auto-created when this IPQC check fails.',
    )

    def write(self, vals):
        """
        Override write to:
        1. Auto-create a deviation immediately when result is set to 'fail'.
           Uses super().write() internally to avoid a recursive re-entry loop
           (the original bug: calling self.write({'deviation_id': ...}) re-entered
           this method, so the deviation appeared to be created only on the
           second save).
        2. Auto-hold the linked BMR step when result = 'fail'.
        3. Auto-release the step hold when result = 'pass' (if it was IPQC-held).
        """
        res = super().write(vals)
        if 'result' in vals:
            for rec in self:
                if vals['result'] == 'fail':
                    # Create deviation immediately if not already linked
                    if not rec.deviation_id:
                        rec._auto_create_deviation()
                    # Auto-hold the linked step so execution is blocked
                    if rec.step_id and rec.step_id.status == 'pending':
                        rec.step_id._ipqc_hold()
                elif vals['result'] == 'pass':
                    # Release the IPQC-triggered hold on the step if all
                    # IPQC checks for that step are now passing
                    if rec.step_id and rec.step_id.status == 'hold':
                        step_ipqcs = rec.bmr_id.ipqc_ids.filtered(
                            lambda r: r.step_id == rec.step_id
                        )
                        if not step_ipqcs.filtered(lambda r: r.result == 'fail'):
                            rec.step_id._ipqc_release()
        return res

    def _auto_create_deviation(self):
        """
        Auto-create a pharma.deviation when an IPQC result is marked Fail.

        Uses super().write() directly to set deviation_id so we don't re-enter
        this class's write() override (which caused the 'created on 2nd save'
        bug). CAPA creation is deferred to QA investigation.
        """
        bmr = self.bmr_id
        dev = self.env['pharma.deviation'].create({
            'batch_id': bmr.production_id.id,
            'description': _(
                'IPQC Failure — Parameter: %(param)s\n'
                'Expected: %(expected)s\n'
                'Actual: %(actual)s\n'
                'Batch: %(batch)s',
                param=self.parameter,
                expected="%s - %s" % (self.expected_min, self.expected_max),
                actual=self.actual_value or '—',
                batch=bmr.batch_no,
            ),
            'immediate_action': _('IPQC check failed. Batch placed under investigation.'),
            'stage': 'manufacturing',
            'classification': 'major',
            'raised_by': self.env.user.id,
            'raised_on': fields.Datetime.now(),
        })
        # Bypass the write() override to avoid recursive re-entry
        super(PharmaIPQCResult, self).write({'deviation_id': dev.id})

        bmr.message_post(
            body=_(
                'IPQC FAIL on "%(param)s". Deviation %(dev)s auto-raised. '
                'Linked step placed on Hold.',
                param=self.parameter,
                dev=dev.name,
            )
        )

    def action_sign(self):
        """Analyst signs the IPQC result — records who and when."""
        for rec in self:
            if rec.signed_on:
                raise UserError(_('This IPQC check is already signed.'))
            if not rec.result:
                raise UserError(_('Set the result (Pass/Fail) before signing.'))
            rec.write({
                'signed_by': self.env.user.id,
                'signed_on': fields.Datetime.now(),
            })
            if rec.result == 'fail':
                if not rec.deviation_id:
                    rec._auto_create_deviation()
                if rec.step_id and rec.step_id.status == 'pending':
                    rec.step_id._ipqc_hold()
